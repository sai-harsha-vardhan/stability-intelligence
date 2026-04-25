"""
JWT Authentication and RBAC Module.

Provides:
- JWT token generation and validation
- Role-based access control (RBAC)
- FastAPI dependency for protected endpoints

Configuration:
    JWT_SECRET_KEY=<generated-secret>
    JWT_ALGORITHM=HS256
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

Roles (hierarchical):
    admin > analyst > viewer > system
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from enum import Enum
from functools import wraps

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field


try:
    from jose import JWTError, jwt
except ImportError:
    raise RuntimeError("python-jose required for JWT. Install: pip install python-jose[cryptography]")


# ============================================================================
# Configuration
# ============================================================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.urandom(32).hex())
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))


# ============================================================================
# Role Definitions
# ============================================================================

class Role(str, Enum):
    """User roles with hierarchy."""
    SYSTEM = "system"      # Internal services
    ADMIN = "admin"        # Full access
    ANALYST = "analyst"    # Read + write analysis
    VIEWER = "viewer"      # Read-only


# Role permissions matrix
ROLE_PERMISSIONS = {
    Role.SYSTEM: {"*"},  # All permissions
    Role.ADMIN: {
        "read:*", "write:*", "delete:*", "admin:*",
        "read:incidents", "read:patterns", "read:action_items",
        "write:action_items", "write:strategies",
        "read:users", "write:users",
    },
    Role.ANALYST: {
        "read:*",
        "read:incidents", "read:patterns", "read:action_items", "read:strategies",
        "write:action_items", "write:strategies",
    },
    Role.VIEWER: {
        "read:*",
        "read:incidents", "read:patterns", "read:action_items", "read:strategies",
    },
}


def has_permission(role: Role, permission: str) -> bool:
    """Check if role has specific permission (supports wildcards)."""
    if role not in ROLE_PERMISSIONS:
        return False
    
    permissions = ROLE_PERMISSIONS[role]
    
    # Exact match
    if permission in permissions:
        return True
    
    # Wildcard match
    parts = permission.split(":")
    for perm in permissions:
        if perm == "*":
            return True
        perm_parts = perm.split(":")
        if len(perm_parts) == len(parts):
            match = all(p == "*" or p == parts[i] for i, p in enumerate(perm_parts))
            if match:
                return True
    
    return False


# ============================================================================
# Pydantic Models
# ============================================================================

class TokenData(BaseModel):
    """JWT payload structure."""
    sub: str = Field(..., description="Subject (user ID)")
    jti: str = Field(default_factory=lambda: str(uuid.uuid4()), description="JWT ID (unique)")
    iat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    exp: datetime
    role: Role
    permissions: List[str] = Field(default_factory=list)
    iss: str = Field(default="rca-intelligent-system")


class User(BaseModel):
    """Authenticated user model."""
    id: str
    username: str
    email: str
    role: Role
    permissions: List[str] = Field(default_factory=list)
    is_active: bool = True


class TokenResponse(BaseModel):
    """Token pair response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


# ============================================================================
# Token Operations
# ============================================================================

security_scheme = HTTPBearer(auto_error=False)


def create_access_token(user: User, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token for user."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    expire = datetime.now(timezone.utc) + expires_delta
    
    # Calculate permissions based on role
    permissions = list(ROLE_PERMISSIONS.get(user.role, set()))
    
    token_data = TokenData(
        sub=user.id,
        exp=expire,
        role=user.role,
        permissions=permissions,
    )
    
    to_encode = token_data.model_dump()
    # Convert datetime to timestamp for JWT
    to_encode["exp"] = int(expire.timestamp())
    to_encode["iat"] = int(datetime.now(timezone.utc).timestamp())
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(user: User) -> str:
    """Create long-lived refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    
    payload = {
        "sub": user.id,
        "jti": str(uuid.uuid4()),
        "exp": int(expire.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "type": "refresh",
        "iss": "rca-intelligent-system",
    }
    
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> User:
    """FastAPI dependency to get current authenticated user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if credentials is None:
        raise credentials_exception
    
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise credentials_exception
    
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    role_str = payload.get("role", "viewer")
    try:
        role = Role(role_str)
    except ValueError:
        role = Role.VIEWER
    
    # TODO: Load user from database/cache
    # For now, reconstruct from token
    user = User(
        id=user_id,
        username=payload.get("username", user_id),
        email=payload.get("email", ""),
        role=role,
        permissions=payload.get("permissions", []),
        is_active=True,
    )
    
    return user


async def get_optional_user(
    request: Request,
) -> Optional[User]:
    """Get user if authenticated, None otherwise (for optional auth)."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    
    token = auth_header[7:]  # Remove "Bearer " prefix
    payload = decode_token(token)
    if payload is None:
        return None
    
    return User(
        id=payload.get("sub", ""),
        username=payload.get("username", ""),
        email=payload.get("email", ""),
        role=Role(payload.get("role", "viewer")),
        permissions=payload.get("permissions", []),
    )


# ============================================================================
# Role-Based Access Control
# ============================================================================

def require_role(required_role: Role):
    """
    FastAPI dependency factory for role-based access control.
    
    Usage:
        @app.get("/admin-only")
        async def admin_endpoint(user: User = Depends(require_role(Role.ADMIN))):
            return {"message": "Admin access granted"}
    """
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        # Define role hierarchy
        role_hierarchy = [Role.VIEWER, Role.ANALYST, Role.ADMIN, Role.SYSTEM]
        
        user_level = role_hierarchy.index(current_user.role)
        required_level = role_hierarchy.index(required_role)
        
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {required_role.value}",
            )
        
        return current_user
    
    return role_checker


def require_permission(permission: str):
    """
    FastAPI dependency factory for permission-based access control.
    
    Usage:
        @app.post("/action-items")
        async def create_action_item(
            user: User = Depends(require_permission("write:action_items"))
        ):
            pass
    """
    async def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )
        
        return current_user
    
    return permission_checker


# ============================================================================
# Authentication Helpers
# ============================================================================

# Simple in-memory user store (replace with database)
# Format: username -> (hashed_password, role)
_USERS: Dict[str, tuple] = {}


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    try:
        import bcrypt
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password.encode(), salt)
        return hashed.decode()
    except ImportError:
        raise RuntimeError("bcrypt required for password hashing. Install: pip install bcrypt")


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash."""
    try:
        import bcrypt
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ImportError:
        raise RuntimeError("bcrypt required for password verification")


def authenticate_user(username: str, password: str) -> Optional[User]:
    """
    Authenticate user credentials.
    
    In production, this should query your identity provider (IdP)
    or user database.
    """
    # Check in-memory store
    if username in _USERS:
        hashed_pw, role_str = _USERS[username]
        if verify_password(password, hashed_pw):
            role = Role(role_str) if role_str in [r.value for r in Role] else Role.VIEWER
            return User(
                id=str(uuid.uuid4()),
                username=username,
                email=f"{username}@example.com",
                role=role,
            )
    
    return None


def register_user(username: str, password: str, role: Role = Role.VIEWER) -> User:
    """Register a new user (for testing/admin setup)."""
    if username in _USERS:
        raise ValueError(f"User {username} already exists")
    
    hashed_pw = hash_password(password)
    _USERS[username] = (hashed_pw, role.value)
    
    return User(
        id=str(uuid.uuid4()),
        username=username,
        email=f"{username}@example.com",
        role=role,
    )


# Register default admin for initial setup
def _ensure_default_admin():
    """Ensure at least one admin user exists."""
    admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD")
    if admin_password and "admin" not in _USERS:
        register_user("admin", admin_password, Role.ADMIN)


# Initialize on module load
_ensure_default_admin()
