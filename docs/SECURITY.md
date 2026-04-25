# Security Architecture

This document describes the security infrastructure for RCA-Intelligent-System, implemented as part of [RCA-20](RCA-20).

## Overview

The security module (`src/core/security/`) provides:

1. **Authentication & Authorization**: JWT-based with RBAC
2. **Secrets Management**: HashiCorp Vault / AWS Secrets Manager
3. **Audit Logging**: Comprehensive event logging
4. **PII Redaction**: Automatic detection and masking
5. **Rate Limiting**: Per-user and per-token budgeting
6. **TLS/SSL**: HTTPS enforcement and secure headers
7. **Vulnerability Scanning**: Automated CI/CD security checks

## Quick Start

### Environment Configuration

Copy and customize `.env`:

```bash
cp .env.example .env
```

Required security environment variables:

```bash
# JWT Configuration
JWT_SECRET_KEY=your-super-secret-key-min-32-chars-long
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30

# Secrets Backend
SECRETS_BACKEND=vault  # or aws, env
VAULT_ADDR=https://vault.yourcompany.com
VAULT_ROLE_ID=your-role-id
VAULT_SECRET_ID=your-secret-id

# Rate Limiting
RATE_LIMIT_STORAGE=memory  # or redis
REDIS_URL=redis://localhost:6379/0
DEFAULT_RATE_LIMIT_PER_MINUTE=60
TOKEN_BUDGET_PER_HOUR=10000

# PII Redaction
PII_REDACTION_MODE=standard  # aggressive, standard, permissive
PII_LOG_REDACTION_EVENTS=true

# TLS/SSL
ENFORCE_TLS=true
TLS_CERT_PATH=/etc/ssl/certs/server.crt
TLS_KEY_PATH=/etc/ssl/private/server.key
ALLOWED_ORIGINS=https://app.example.com

# Audit Logging
AUDIT_LOG_LEVEL=INFO
AUDIT_LOG_DESTINATION=stdout
AUDIT_RETENTION_DAYS=90
```

## Components

### 1. Authentication & Authorization

```python
from src.core.security import (
    authenticate_user,
    create_access_token,
    require_role,
    Role,
)

# Login
user = authenticate_user(username, password)
token = create_access_token(user)

# Protect endpoint
@app.get("/admin")
async def admin_only(user: User = Depends(require_role(Role.ADMIN))):
    pass
```

**Roles** (hierarchical):
- `system`: Internal services (all permissions)
- `admin`: Full access
- `analyst`: Read + write analysis data
- `viewer`: Read-only

### 2. Secrets Management

```python
from src.core.security import get_secrets_manager

secrets = get_secrets_manager()
api_key = secrets.get("openai.api_key")
db_password = secrets.get_required("database.password")
```

**Backends**:
- `vault`: HashiCorp Vault (production)
- `aws`: AWS Secrets Manager (production)
- `env`: Environment variables (development only)

### 3. Audit Logging

```python
from src.core.security.audit import (
    audit_log,
    audit_db_query,
    audit_llm_call,
    AuditEventType,
)

# Log custom event
audit_log(
    event_type=AuditEventType.DATA_EXPORT,
    actor_id=user.id,
    resource="incidents",
    action="csv_export",
    severity=AuditSeverity.INFO,
)

# Auto-log database query
audit_db_query(
    actor_id=user.id,
    query_type="SELECT",
    table="incidents",
    rows_affected=100,
)
```

### 4. PII Redaction

```python
from src.core.security.redactor import (
    redact_sensitive_data,
    redact_for_llm_prompt,
    PIIRedactor,
    RedactionMode,
)

# Redact text
safe_text = redact_sensitive_data(text_containing_pii)

# Aggressive mode for LLM prompts
safe_prompt = redact_for_llm_prompt(raw_prompt)

# Custom redactor
redactor = PIIRedactor(mode=RedactionMode.AGGRESSIVE)
redacted = redactor.redact(text)
```

**Patterns detected**:
- Credit card numbers
- Social Security Numbers
- Email addresses
- Phone numbers
- API keys (sk_*, pk_*, ghp_*)
- IP addresses
- Database credentials

### 5. Rate Limiting

```python
from src.core.security.rate_limiter import rate_limit
from src.core.security.rate_limiter import rate_limit_dependency

# Decorator
@rate_limit(limit=60, cost=1)
def expensive_function():
    pass

# FastAPI dependency
@app.get("/api/items")
async def list_items(_: None = Depends(rate_limit_dependency)):
    pass
```

### 6. Security Middleware

```python
from src.core.security.middleware import apply_security_middlewares

app = FastAPI()
apply_security_middlewares(app)
```

**Applied middlewares**:
- HTTPS redirect
- Security headers (HSTS, CSP, etc.)
- IP blocklist
- Request size limits
- CORS configuration

## Secured API

The secured dashboard API (`dashboard/api/secure_main.py`) includes:

- JWT authentication on all endpoints
- RBAC authorization checks
- Rate limiting per endpoint
- Audit logging of all data access
- PII redaction in responses
- Secure CORS headers

**Usage**:

```bash
# Start with TLS
uvicorn dashboard.api.secure_main:app \
    --host 0.0.0.0 \
    --port 8443 \
    --ssl-keyfile=/path/to/key.pem \
    --ssl-certfile=/path/to/cert.pem

# Or proxy through nginx/apache with TLS termination
```

## Vulnerability Scanning

Automated security scans run on every PR via GitHub Actions:

1. **Trivy**: Container image vulnerability scanning
2. **Snyk**: Dependency vulnerability and license compliance
3. **Bandit**: Static analysis for Python security issues
4. **TruffleHog**: Secret detection in code
5. **pip-audit**: Python package vulnerability scanning

View results in GitHub Security tab and PR checks.

## Security Checklist

Before deploying to production:

- [ ] JWT_SECRET_KEY is strong (32+ chars, random)
- [ ] SECRETS_BACKEND is vault or aws (not env)
- [ ] ENFORCE_TLS is true
- [ ] TLS certificates are valid and not expiring soon
- [ ] ALLOWED_ORIGINS is restricted (not *)
- [ ] Default admin password is changed
- [ ] Audit logging is enabled
- [ ] Rate limits are configured appropriately
- [ ] PII redaction mode is set to standard or aggressive
- [ ] Security scanning passes in CI/CD
- [ ] .env file is in .gitignore
- [ ] No secrets committed to repository

## Incident Response

If a security breach is suspected:

1. **Immediate**: Revoke all JWT tokens (change JWT_SECRET_KEY)
2. **Assessment**: Check audit logs for unauthorized access
3. **Rotation**: Rotate all API keys and credentials
4. **Notification**: Follow company incident response procedures
5. **Review**: Conduct security audit of affected systems

## Compliance Notes

This security implementation supports:

- **SOC 2 Type II**: Audit trails, access controls
- **GDPR**: PII redaction, data minimization
- **PCI DSS**: Credit card detection (data must not enter system)

## Support

For security issues:

1. Do NOT open public GitHub issues
2. Contact: security@yourcompany.com
3. Reference: RCA-20 Security Hardening
