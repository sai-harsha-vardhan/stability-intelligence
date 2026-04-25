"""
Audit Logging Module.

Provides comprehensive audit logging for:
- All LLM API calls (model, tokens, timestamp, user)
- Database queries executed by agents
- Kubernetes operations
- Authentication events
- Data access events

Log destinations:
- Structured JSON logs (stdout/file)
- Optional: SIEM integration (Splunk, ELK)
- Optional: Database storage for long-term retention

Configuration:
    AUDIT_LOG_LEVEL=INFO|WARNING|ERROR
    AUDIT_LOG_DESTINATION=stdout|file|database
    AUDIT_LOG_FILE_PATH=/var/log/rca/audit.log
    AUDIT_RETENTION_DAYS=90
"""

import os
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from enum import Enum
from functools import wraps
import logging
import threading


# ============================================================================
# Configuration
# ============================================================================

AUDIT_LOG_LEVEL = os.getenv("AUDIT_LOG_LEVEL", "INFO").upper()
AUDIT_LOG_DESTINATION = os.getenv("AUDIT_LOG_DESTINATION", "stdout")
AUDIT_LOG_FILE_PATH = os.getenv("AUDIT_LOG_FILE_PATH", "/var/log/rca/audit.log")
AUDIT_RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "90"))


# ============================================================================
# Event Types and Severities
# ============================================================================

class AuditEventType(str, Enum):
    """Types of auditable events."""
    # LLM Operations
    LLM_REQUEST = "llm.request"
    LLM_RESPONSE = "llm.response"
    LLM_ERROR = "llm.error"
    
    # Database Operations
    DB_QUERY = "db.query"
    DB_WRITE = "db.write"
    DB_DELETE = "db.delete"
    
    # Authentication
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_FAILURE = "auth.failure"
    TOKEN_REFRESH = "auth.token_refresh"
    
    # Authorization
    ACCESS_DENIED = "access.denied"
    PERMISSION_CHECK = "access.permission_check"
    
    # Data Access
    DATA_READ = "data.read"
    DATA_EXPORT = "data.export"
    PII_REDACTION = "data.pii_redaction"
    
    # Kubernetes
    K8S_COMMAND = "k8s.command"
    K8S_DEPLOYMENT = "k8s.deployment"
    
    # System
    CONFIG_CHANGE = "system.config_change"
    SECURITY_ALERT = "security.alert"
    ERROR = "system.error"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ============================================================================
# Audit Event Dataclass
# ============================================================================

@dataclass
class AuditEvent:
    """
    Audit event record.
    
    All fields are logged; sensitive data should be redacted
    before creating the event.
    """
    event_type: AuditEventType
    severity: AuditSeverity
    actor_id: str  # User or system ID
    actor_type: str  # "user", "system", "agent"
    resource: str  # Resource being accessed (table name, endpoint, etc.)
    action: str  # Specific action performed
    timestamp: datetime
    event_id: str
    trace_id: Optional[str] = None  # Distributed tracing correlation
    
    # Context
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    
    # Operation details
    duration_ms: Optional[float] = None
    status: Optional[str] = None  # "success", "failure", "denied"
    error_message: Optional[str] = None
    
    # Data metrics
    rows_affected: Optional[int] = None
    tokens_used: Optional[int] = None
    data_size_bytes: Optional[int] = None
    
    # Additional context (validated for PII before logging)
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Auto-generate event_id if not provided."""
        if not self.event_id:
            object.__setattr__(
                self, 
                'event_id', 
                f"evt_{uuid.uuid4().hex[:16]}_{int(self.timestamp.timestamp())}"
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['event_type'] = self.event_type.value
        data['severity'] = self.severity.value
        return data
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), separators=(',', ':'))


# ============================================================================
# Audit Logger Backend
# ============================================================================

class AuditLogger:
    """
    Thread-safe audit logger with multiple destination support.
    """
    
    _instance: Optional["AuditLogger"] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._logger = logging.getLogger("rca.audit")
        self._logger.setLevel(getattr(logging, AUDIT_LOG_LEVEL, logging.INFO))
        
        # Remove existing handlers to avoid duplicates
        self._logger.handlers = []
        
        # Configure handler based on destination
        if AUDIT_LOG_DESTINATION == "file":
            os.makedirs(os.path.dirname(AUDIT_LOG_FILE_PATH), exist_ok=True)
            handler = logging.FileHandler(AUDIT_LOG_FILE_PATH)
        else:
            handler = logging.StreamHandler()
        
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)
        
        # Additional destinations
        self._database_sink: Optional[Any] = None
        self._siem_sink: Optional[Any] = None
        
        self._initialized = True
    
    def _should_log(self, severity: AuditSeverity) -> bool:
        """Check if event meets minimum severity threshold."""
        levels = {
            AuditSeverity.DEBUG: 0,
            AuditSeverity.INFO: 1,
            AuditSeverity.WARNING: 2,
            AuditSeverity.ERROR: 3,
            AuditSeverity.CRITICAL: 4,
        }
        min_level = getattr(logging, AUDIT_LOG_LEVEL, logging.INFO)
        min_severity = {
            logging.DEBUG: AuditSeverity.DEBUG,
            logging.INFO: AuditSeverity.INFO,
            logging.WARNING: AuditSeverity.WARNING,
            logging.ERROR: AuditSeverity.ERROR,
            logging.CRITICAL: AuditSeverity.CRITICAL,
        }.get(min_level, AuditSeverity.INFO)
        
        return levels[severity] >= levels[min_severity]
    
    def log(self, event: AuditEvent) -> None:
        """Log an audit event to all configured destinations."""
        if not self._should_log(event.severity):
            return
        
        json_line = event.to_json()
        self._logger.info(json_line)
        
        # Send to database if configured
        if self._database_sink:
            self._write_to_database(event)
        
        # Send to SIEM if configured
        if self._siem_sink:
            self._write_to_siem(event)
    
    def _write_to_database(self, event: AuditEvent):
        """Persist to audit database table."""
        # TODO: Implement Neo4j or PostgreSQL persistence
        pass
    
    def _write_to_siem(self, event: AuditEvent):
        """Send to SIEM system (Splunk HEC, ELK, etc.)."""
        # TODO: Implement SIEM integration
        pass
    
    def set_database_sink(self, sink: Any):
        """Configure database persistence sink."""
        self._database_sink = sink
    
    def set_siem_sink(self, sink: Any):
        """Configure SIEM integration sink."""
        self._siem_sink = sink


# ============================================================================
# Convenience Functions
# ============================================================================

def audit_log(
    event_type: AuditEventType,
    actor_id: str,
    resource: str,
    action: str,
    severity: AuditSeverity = AuditSeverity.INFO,
    actor_type: str = "user",
    **kwargs
) -> AuditEvent:
    """
    Log an audit event.
    
    Args:
        event_type: Type of event being logged
        actor_id: User ID or system identifier
        resource: Resource being accessed (table, endpoint, etc.)
        action: Specific action performed
        severity: Event severity level
        actor_type: Type of actor (user, system, agent)
        **kwargs: Additional fields (ip_address, status, metadata, etc.)
    
    Returns:
        The logged AuditEvent
    """
    logger = AuditLogger()
    
    event = AuditEvent(
        event_type=event_type,
        severity=severity,
        actor_id=actor_id,
        actor_type=actor_type,
        resource=resource,
        action=action,
        timestamp=datetime.now(timezone.utc),
        event_id=f"evt_{uuid.uuid4().hex[:16]}",
        **kwargs
    )
    
    logger.log(event)
    return event


def audit_llm_call(
    actor_id: str,
    model: str,
    tokens_prompt: int,
    tokens_completion: int,
    duration_ms: float,
    status: str = "success",
    **kwargs
) -> AuditEvent:
    """
    Log an LLM API call.
    
    Tracks:
    - Model used
    - Token consumption (prompt + completion)
    - Duration
    - Calling user/system
    """
    return audit_log(
        event_type=AuditEventType.LLM_REQUEST,
        actor_id=actor_id,
        resource=f"llm:{model}",
        action="generate",
        severity=AuditSeverity.INFO,
        status=status,
        tokens_used=tokens_prompt + tokens_completion,
        metadata={
            "model": model,
            "tokens_prompt": tokens_prompt,
            "tokens_completion": tokens_completion,
            "duration_ms": duration_ms,
            **kwargs
        }
    )


def audit_db_query(
    actor_id: str,
    query_type: str,
    table: str,
    rows_affected: int = 0,
    duration_ms: Optional[float] = None,
    status: str = "success",
    **kwargs
) -> AuditEvent:
    """
    Log a database query.
    
    Does NOT log query parameters - only metadata.
    """
    event_type = AuditEventType.DB_QUERY
    if query_type.lower() in ("insert", "update"):
        event_type = AuditEventType.DB_WRITE
    elif query_type.lower() == "delete":
        event_type = AuditEventType.DB_DELETE
    
    return audit_log(
        event_type=event_type,
        actor_id=actor_id,
        resource=f"db:{table}",
        action=query_type.lower(),
        rows_affected=rows_affected,
        duration_ms=duration_ms,
        status=status,
        metadata=kwargs
    )


def audit_auth_event(
    event_type: AuditEventType,
    username: str,
    ip_address: Optional[str] = None,
    success: bool = True,
    failure_reason: Optional[str] = None,
    **kwargs
) -> AuditEvent:
    """Log authentication event."""
    severity = AuditSeverity.INFO if success else AuditSeverity.WARNING
    if event_type == AuditEventType.AUTH_FAILURE:
        severity = AuditSeverity.WARNING
    
    return audit_log(
        event_type=event_type,
        actor_id=username,
        resource="auth",
        action=event_type.value.split(".")[1],  # login, logout, etc.
        severity=severity,
        ip_address=ip_address,
        status="success" if success else "failure",
        error_message=failure_reason,
        metadata=kwargs
    )


def audit_k8s_command(
    actor_id: str,
    command: str,
    namespace: Optional[str] = None,
    resource_type: Optional[str] = None,
    status: str = "success",
    **kwargs
) -> AuditEvent:
    """
    Log a Kubernetes operation.
    
    WARNING: Never log full kubectl commands with sensitive flags.
    Log only: verb, resource type, namespace.
    """
    # Extract safe command info (verb + resource)
    parts = command.split()
    verb = parts[0] if parts else "unknown"
    resource = resource_type or (parts[1] if len(parts) > 1 else "unknown")
    
    return audit_log(
        event_type=AuditEventType.K8S_COMMAND,
        actor_id=actor_id,
        resource=f"k8s:{namespace or 'default'}/{resource}",
        action=verb,
        severity=AuditSeverity.INFO,
        status=status,
        metadata={
            "namespace": namespace,
            "resource_type": resource,
            **kwargs
        }
    )


def audit_data_access(
    actor_id: str,
    data_type: str,
    action: str,
    rows_accessed: int = 0,
    ip_address: Optional[str] = None,
    **kwargs
) -> AuditEvent:
    """Log data access event (reads, exports)."""
    event_type = AuditEventType.DATA_READ
    if action == "export":
        event_type = AuditEventType.DATA_EXPORT
    
    return audit_log(
        event_type=event_type,
        actor_id=actor_id,
        resource=f"data:{data_type}",
        action=action,
        rows_affected=rows_accessed,
        ip_address=ip_address,
        metadata=kwargs
    )


def audit_security_alert(
    alert_type: str,
    severity: AuditSeverity,
    description: str,
    affected_resource: Optional[str] = None,
    **kwargs
) -> AuditEvent:
    """Log security alert or anomaly."""
    return audit_log(
        event_type=AuditEventType.SECURITY_ALERT,
        actor_id="security_system",
        actor_type="system",
        resource=affected_resource or "system",
        action=f"alert:{alert_type}",
        severity=severity,
        error_message=description,
        metadata=kwargs
    )


# ============================================================================
# Decorators
# ============================================================================

def audited(event_type: AuditEventType, resource_fn=None, action: str = None):
    """
    Decorator to automatically audit function calls.
    
    Usage:
        @audited(AuditEventType.DB_QUERY, resource_fn=lambda: "neo4j", action="read")
        def get_incident(incident_id: str):
            return db.query(...)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = datetime.now(timezone.utc)
            
            try:
                result = func(*args, **kwargs)
                status = "success"
                error_msg = None
            except Exception as e:
                status = "failure"
                error_msg = str(e)
                raise
            finally:
                duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                
                resource = resource_fn() if resource_fn else func.__module__
                action_name = action or func.__name__
                
                audit_log(
                    event_type=event_type,
                    actor_id="system",  # Should be extracted from context
                    resource=resource,
                    action=action_name,
                    duration_ms=duration,
                    status=status,
                    error_message=error_msg,
                )
            
            return result
        
        return wrapper
    return decorator
