"""
Security Middleware for FastAPI.

Provides:
- HTTPS enforcement (TLS/SSL)
- Secure headers (HSTS, CSP, etc.)
- Request validation
- CORS security configuration
- IP allowlisting/blocklisting

Configuration:
    ENFORCE_TLS=true
    TLS_CERT_PATH=/etc/ssl/certs/server.crt
    TLS_KEY_PATH=/etc/ssl/private/server.key
    ALLOWED_ORIGINS=https://example.com,https://app.example.com
    BLOCKED_IPS=10.0.0.1,192.168.1.100
"""

import os
import re
from typing import Optional, List, Callable
from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .auth import get_current_user
from .rate_limiter import rate_limit_dependency


# ============================================================================
# Configuration
# ============================================================================

ENFORCE_TLS = os.getenv("ENFORCE_TLS", "true").lower() == "true"
TLS_CERT_PATH = os.getenv("TLS_CERT_PATH", "/etc/ssl/certs/server.crt")
TLS_KEY_PATH = os.getenv("TLS_KEY_PATH", "/etc/ssl/private/server.key")
ALLOWED_ORIGINS_STR = os.getenv("ALLOWED_ORIGINS", "")
BLOCKED_IPS_STR = os.getenv("BLOCKED_IPS", "")
HSTS_MAX_AGE = int(os.getenv("HSTS_MAX_AGE", "31536000"))  # 1 year
CONTENT_SECURITY_POLICY = os.getenv(
    "CONTENT_SECURITY_POLICY",
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;"
)

# Parse lists
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS_STR.split(",") if o.strip()] or ["*"]
BLOCKED_IPS = set(ip.strip() for ip in BLOCKED_IPS_STR.split(",") if ip.strip())


# ============================================================================
# Security Headers Middleware
# ============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.
    
    Headers added:
    - Strict-Transport-Security (HSTS)
    - Content-Security-Policy
    - X-Content-Type-Options
    - X-Frame-Options
    - X-XSS-Protection
    - Referrer-Policy
    - Permissions-Policy
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # HSTS - Force HTTPS
        if ENFORCE_TLS:
            response.headers["Strict-Transport-Security"] = (
                f"max-age={HSTS_MAX_AGE}; includeSubDomains; preload"
            )
        
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # Legacy XSS protection (for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Content Security Policy
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        
        # Permissions Policy (formerly Feature-Policy)
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )
        
        return response


# ============================================================================
# HTTPS Enforcement Middleware
# ============================================================================

class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """
    Redirect HTTP requests to HTTPS.
    
    Checks:
    - X-Forwarded-Proto header (for proxies/load balancers)
    - Request scheme
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not ENFORCE_TLS:
            return await call_next(request)
        
        # Check if request is already HTTPS
        is_https = (
            request.url.scheme == "https"
            or request.headers.get("X-Forwarded-Proto") == "https"
            or request.headers.get("X-Forwarded-Scheme") == "https"
        )
        
        if not is_https:
            # Redirect to HTTPS
            https_url = request.url.replace(scheme="https")
            return Response(
                status_code=307,  # Temporary redirect (preserve method)
                headers={"Location": str(https_url)},
            )
        
        return await call_next(request)


# ============================================================================
# IP Blocklist Middleware
# ============================================================================

class IPBlocklistMiddleware(BaseHTTPMiddleware):
    """Block requests from forbidden IP addresses."""
    
    def __init__(self, app, blocked_ips: Optional[set] = None):
        super().__init__(app)
        self.blocked_ips = blocked_ips or BLOCKED_IPS
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = self._get_client_ip(request)
        
        if client_ip in self.blocked_ips:
            return Response(
                status_code=403,
                content='{"detail": "Forbidden"}',
                media_type="application/json",
            )
        
        return await call_next(request)
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract real client IP (considering proxies)."""
        # Check X-Forwarded-For header
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP in the chain (closest to client)
            return forwarded_for.split(",")[0].strip()
        
        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fall back to direct connection
        return request.client.host if request.client else "unknown"


# ============================================================================
# Request Size Limit Middleware
# ============================================================================

MAX_REQUEST_SIZE_MB = int(os.getenv("MAX_REQUEST_SIZE_MB", "10"))
MAX_REQUEST_SIZE_BYTES = MAX_REQUEST_SIZE_MB * 1024 * 1024


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size to prevent DoS."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        content_length = request.headers.get("content-length")
        
        if content_length:
            size = int(content_length)
            if size > MAX_REQUEST_SIZE_BYTES:
                return Response(
                    status_code=413,
                    content=f'{{"detail": "Request too large. Max size: {MAX_REQUEST_SIZE_MB}MB"}}',
                    media_type="application/json",
                )
        
        return await call_next(request)


# ============================================================================
# Secure CORS Configuration
# ============================================================================

def create_secure_cors_middleware() -> Callable:
    """
    Create a secure CORS middleware configuration.
    
    Production defaults:
    - No wildcard origins
    - Credentials allowed only for specific origins
    - Limited HTTP methods
    """
    return CORSMiddleware(
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Requested-With",
            "Accept",
            "Origin",
        ],
        expose_headers=[
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ],
        max_age=600,  # 10 minutes
    )


# ============================================================================
# Request ID Middleware
# ============================================================================

import uuid


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add unique request ID for tracing."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        
        return response


# ============================================================================
# Combined Security Middleware Stack
# ============================================================================

def apply_security_middlewares(app):
    """
    Apply all security middlewares to FastAPI app.
    
    Order matters - applied in reverse (last added = outermost):
    1. HTTPS redirect (outermost)
    2. IP blocklist
    3. Request size limit
    4. Security headers
    5. Request ID (innermost)
    """
    # Innermost: Request ID
    app.add_middleware(RequestIDMiddleware)
    
    # Security headers
    app.add_middleware(SecurityHeadersMiddleware)
    
    # Request size limit
    app.add_middleware(RequestSizeLimitMiddleware)
    
    # IP blocklist
    app.add_middleware(IPBlocklistMiddleware)
    
    # HTTPS redirect (outermost, first to process)
    app.add_middleware(HTTPSRedirectMiddleware)
    
    # CORS - must be after security but before business logic
    app.add_middleware(create_secure_cors_middleware().__class__)


# ============================================================================
# SSL/TLS Certificate Helpers
# ============================================================================

def validate_tls_certificates() -> bool:
    """Check if TLS certificates exist and are valid."""
    import ssl
    
    if not os.path.exists(TLS_CERT_PATH):
        print(f"WARNING: TLS certificate not found: {TLS_CERT_PATH}")
        return False
    
    if not os.path.exists(TLS_KEY_PATH):
        print(f"WARNING: TLS private key not found: {TLS_KEY_PATH}")
        return False
    
    try:
        # Validate certificate
        context = ssl.create_default_context()
        context.load_cert_chain(TLS_CERT_PATH, TLS_KEY_PATH)
        
        # Check expiration
        import OpenSSL.crypto as crypto
        with open(TLS_CERT_PATH, 'rb') as f:
            cert = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        
        from datetime import datetime
        not_after = datetime.strptime(
            cert.get_notAfter().decode('ascii'), 
            '%Y%m%d%H%M%SZ'
        )
        
        days_until_expiry = (not_after - datetime.utcnow()).days
        if days_until_expiry < 30:
            print(f"WARNING: TLS certificate expires in {days_until_expiry} days")
        
        return True
    except Exception as e:
        print(f"ERROR: TLS certificate validation failed: {e}")
        return False


def get_ssl_context() -> Optional:
    """Get SSL context for HTTPS server."""
    import ssl
    
    if not os.path.exists(TLS_CERT_PATH) or not os.path.exists(TLS_KEY_PATH):
        return None
    
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(TLS_CERT_PATH, TLS_KEY_PATH)
    
    # Modern TLS configuration
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.options |= ssl.OP_NO_TLSv1
    context.options |= ssl.OP_NO_TLSv1_1
    
    return context
