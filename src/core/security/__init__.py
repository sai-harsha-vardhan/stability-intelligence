"""
RCA-Intelligent-System Security Module.

Production-grade security infrastructure including:
- JWT authentication with RBAC
- Secrets management (HashiCorp Vault / AWS Secrets Manager)
- Audit logging system
- PII redaction
- Rate limiting
- TLS/SSL enforcement

Usage:
    from src.core.security import (
        authenticate_user,
        require_role,
        audit_log,
        redact_sensitive_data,
        rate_limit,
        SecretsManager,
    )
"""

__version__ = "1.0.0"
__all__ = [
    "authenticate_user",
    "create_access_token",
    "require_role",
    "audit_log",
    "AuditEvent",
    "redact_sensitive_data",
    "PIIRedactor",
    "rate_limit",
    "RateLimiter",
    "SecretsManager",
    "get_secrets_manager",
]

from .auth import authenticate_user, create_access_token, require_role
from .audit import audit_log, AuditEvent
from .redactor import redact_sensitive_data, PIIRedactor
from .rate_limiter import rate_limit, RateLimiter
from .secrets import SecretsManager, get_secrets_manager
