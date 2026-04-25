"""
PII Redaction Module.

Detects and masks sensitive data before it reaches:
- LLM prompts
- Log files
- API responses
- Audit trails

Patterns detected:
- Credit card numbers (PCI DSS)
- Social Security Numbers
- Email addresses
- Phone numbers
- IP addresses
- API keys (sk_*, pk_*, etc.)
- Passwords and secrets

Configuration:
    PII_REDACTION_MODE=aggressive|standard|permissive
    PII_LOG_REDACTION_EVENTS=true|false
"""

import os
import re
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum

from .audit import audit_log, AuditEventType, AuditSeverity


# ============================================================================
# Configuration
# ============================================================================

PII_REDACTION_MODE = os.getenv("PII_REDACTION_MODE", "standard")
PII_LOG_REDACTION_EVENTS = os.getenv("PII_LOG_REDACTION_EVENTS", "true").lower() == "true"


class RedactionMode(str, Enum):
    """Redaction aggressiveness levels."""
    AGGRESSIVE = "aggressive"  # Mask everything potentially sensitive
    STANDARD = "standard"      # Mask known PII patterns
    PERMISSIVE = "permissive"  # Minimal redaction


# ============================================================================
# PII Pattern Definitions
# ============================================================================

@dataclass
class PIIPattern:
    """Definition of a PII pattern to detect and mask."""
    name: str
    pattern: re.Pattern
    mask_fn: callable  # Function to apply masking
    severity: str = "high"  # high, medium, low
    description: str = ""


def mask_email(match: re.Match) -> str:
    """Mask email: user@domain.com -> u***@domain.com"""
    email = match.group(0)
    if "@" not in email:
        return "[EMAIL_REDACTED]"
    
    local, domain = email.rsplit("@", 1)
    if len(local) <= 2:
        masked_local = "*" * len(local)
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    
    return f"{masked_local}@{domain}"


def mask_phone(match: re.Match) -> str:
    """Mask phone: +1-555-123-4567 -> ***-***-4567"""
    digits = re.sub(r'\D', '', match.group(0))
    if len(digits) >= 4:
        return "***-***-" + digits[-4:]
    return "[PHONE_REDACTED]"


def mask_ssn(match: re.Match) -> str:
    """Mask SSN completely."""
    return "[SSN_REDACTED]"


def mask_credit_card(match: re.Match) -> str:
    """Mask credit card: show only last 4 digits."""
    digits = re.sub(r'\D', '', match.group(0))
    if len(digits) >= 4:
        return "****-****-****-" + digits[-4:]
    return "[CARD_REDACTED]"


def mask_api_key(match: re.Match) -> str:
    """Remove API key entirely."""
    return "[API_KEY_REDACTED]"


def mask_ip_address(match: re.Match) -> str:
    """Mask IP: 192.168.1.100 -> 192.168.x.x"""
    ip = match.group(0)
    if "." in ip:
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.x.x"
    elif ":" in ip:
        # IPv6 - mask heavily
        return "[IPv6_REDACTED]"
    return "[IP_REDACTED]"


def mask_password_value(match: re.Match) -> str:
    """Remove password/credential values."""
    return f'{match.group(1)}="[CREDENTIAL_REDACTED]"'


# Compile patterns
PII_PATTERNS: List[PIIPattern] = [
    # Credit cards (Visa, MasterCard, Amex, Discover)
    PIIPattern(
        name="credit_card",
        pattern=re.compile(
            r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12})\b',
            re.IGNORECASE
        ),
        mask_fn=mask_credit_card,
        severity="critical",
        description="Payment card number (PCI DSS)",
    ),
    
    # Social Security Numbers
    PIIPattern(
        name="ssn",
        pattern=re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        mask_fn=mask_ssn,
        severity="high",
        description="US Social Security Number",
    ),
    
    # Email addresses
    PIIPattern(
        name="email",
        pattern=re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            re.IGNORECASE
        ),
        mask_fn=mask_email,
        severity="medium",
        description="Email address",
    ),
    
    # Phone numbers (various formats)
    PIIPattern(
        name="phone",
        pattern=re.compile(
            r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
            re.IGNORECASE
        ),
        mask_fn=mask_phone,
        severity="medium",
        description="Phone number",
    ),
    
    # API keys (common prefixes)
    PIIPattern(
        name="api_key_sk",
        pattern=re.compile(r'sk-[a-zA-Z0-9]{20,}', re.IGNORECASE),
        mask_fn=mask_api_key,
        severity="critical",
        description="API Secret Key (OpenAI format)",
    ),
    PIIPattern(
        name="api_key_pk",
        pattern=re.compile(r'pk-[a-zA-Z0-9]{20,}', re.IGNORECASE),
        mask_fn=mask_api_key,
        severity="critical",
        description="API Public Key",
    ),
    PIIPattern(
        name="api_key_generic",
        pattern=re.compile(
            r'\b(?:api[_-]?key|api[_-]?secret|auth[_-]?token|bearer|access[_-]?token)["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{20,}["\']?',
            re.IGNORECASE
        ),
        mask_fn=mask_api_key,
        severity="high",
        description="Generic API key pattern",
    ),
    
    # GitHub tokens
    PIIPattern(
        name="github_token",
        pattern=re.compile(r'gh[pousr]_[A-Za-z0-9_]{36,}', re.IGNORECASE),
        mask_fn=mask_api_key,
        severity="critical",
        description="GitHub personal access token",
    ),
    
    # IP addresses (v4 and v6)
    PIIPattern(
        name="ipv4",
        pattern=re.compile(
            r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
        ),
        mask_fn=mask_ip_address,
        severity="low",
        description="IPv4 address",
    ),
    
    # Database connection strings with passwords
    PIIPattern(
        name="db_connection",
        pattern=re.compile(
            r'(postgresql://|mysql://|mongodb://)([^:]+):([^@]+)@',
            re.IGNORECASE
        ),
        mask_fn=lambda m: f"{m.group(1)}{m.group(2)}:[PASSWORD_REDACTED]@",
        severity="critical",
        description="Database connection string with credentials",
    ),
    
    # Password fields in config
    PIIPattern(
        name="password_field",
        pattern=re.compile(
            r'(password|passwd|pwd|secret)["\']?\s*[:=]\s*["\'][^"\']+["\']',
            re.IGNORECASE
        ),
        mask_fn=mask_password_value,
        severity="high",
        description="Password configuration field",
    ),
]

# Aggressive mode adds extra patterns
AGGRESSIVE_PATTERNS = PII_PATTERNS + [
    PIIPattern(
        name="uuid",
        pattern=re.compile(
            r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
            re.IGNORECASE
        ),
        mask_fn=lambda m: "[UUID_REDACTED]",
        severity="low",
        description="UUID (potential identifier)",
    ),
]


# ============================================================================
# Redaction Engine
# ============================================================================

class PIIRedactor:
    """
    PII detection and redaction engine.
    
    Usage:
        redactor = PIIRedactor(mode=RedactionMode.STANDARD)
        clean_text = redactor.redact(text_with_pii)
    """
    
    def __init__(self, mode: Optional[RedactionMode] = None):
        self.mode = mode or RedactionMode(PII_REDACTION_MODE)
        self.patterns = self._get_patterns_for_mode()
        self.stats = {"total_redactions": 0, "by_pattern": {}}
    
    def _get_patterns_for_mode(self) -> List[PIIPattern]:
        """Select patterns based on redaction mode."""
        if self.mode == RedactionMode.AGGRESSIVE:
            return AGGRESSIVE_PATTERNS
        elif self.mode == RedactionMode.PERMISSIVE:
            # Only critical patterns
            return [p for p in PII_PATTERNS if p.severity == "critical"]
        else:  # STANDARD
            return PII_PATTERNS
    
    def redact(self, text: str, context: Optional[str] = None) -> str:
        """
        Redact PII from text.
        
        Args:
            text: Input text that may contain PII
            context: Description of where this text came from (for logging)
        
        Returns:
            Text with PII replaced by masked versions
        """
        if not text:
            return text
        
        original = text
        redaction_count = 0
        redacted_patterns = []
        
        for pattern in self.patterns:
            def replace_fn(match):
                nonlocal redaction_count
                redaction_count += 1
                if pattern.name not in redacted_patterns:
                    redacted_patterns.append(pattern.name)
                return pattern.mask_fn(match)
            
            text = pattern.pattern.sub(replace_fn, text)
        
        # Log redaction event if configured and redactions occurred
        if PII_LOG_REDACTION_EVENTS and redaction_count > 0:
            self._log_redaction_event(redaction_count, redacted_patterns, context)
        
        # Update stats
        self.stats["total_redactions"] += redaction_count
        for pattern_name in redacted_patterns:
            self.stats["by_pattern"][pattern_name] = self.stats["by_pattern"].get(pattern_name, 0) + 1
        
        return text
    
    def redact_dict(self, data: Dict[str, Any], recursive: bool = True) -> Dict[str, Any]:
        """
        Redact PII from dictionary values.
        
        Args:
            data: Dictionary that may contain PII in values
            recursive: If True, recurse into nested dicts and lists
        
        Returns:
            New dictionary with redacted values
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.redact(value, context=f"dict_key:{key}")
            elif recursive and isinstance(value, dict):
                result[key] = self.redact_dict(value, recursive)
            elif recursive and isinstance(value, list):
                result[key] = self.redact_list(value)
            else:
                result[key] = value
        return result
    
    def redact_list(self, items: List[Any]) -> List[Any]:
        """Redact PII from list items."""
        result = []
        for item in items:
            if isinstance(item, str):
                result.append(self.redact(item, context="list_item"))
            elif isinstance(item, dict):
                result.append(self.redact_dict(item))
            elif isinstance(item, list):
                result.append(self.redact_list(item))
            else:
                result.append(item)
        return result
    
    def scan(self, text: str) -> List[Dict[str, Any]]:
        """
        Scan text for PII patterns without redacting.
        
        Returns list of detected patterns with positions.
        """
        findings = []
        for pattern in self.patterns:
            for match in pattern.pattern.finditer(text):
                findings.append({
                    "pattern": pattern.name,
                    "severity": pattern.severity,
                    "start": match.start(),
                    "end": match.end(),
                    "matched_text": match.group(0),
                    "description": pattern.description,
                })
        return findings
    
    def _log_redaction_event(self, count: int, patterns: List[str], context: Optional[str]):
        """Log redaction event for audit trail."""
        audit_log(
            event_type=AuditEventType.PII_REDACTION,
            actor_id="redaction_engine",
            actor_type="system",
            resource=context or "text_processing",
            action="redact",
            severity=AuditSeverity.INFO,
            metadata={
                "redaction_count": count,
                "patterns_detected": patterns,
                "mode": self.mode.value,
            }
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get redaction statistics."""
        return {
            "mode": self.mode.value,
            **self.stats,
            "patterns_active": len(self.patterns),
        }


# ============================================================================
# Global Instance
# ============================================================================

# Singleton redactor instance
_redactor_instance: Optional[PIIRedactor] = None


def get_redactor() -> PIIRedactor:
    """Get the global PIIRedactor instance."""
    global _redactor_instance
    if _redactor_instance is None:
        _redactor_instance = PIIRedactor()
    return _redactor_instance


def redact_sensitive_data(text: str, context: Optional[str] = None) -> str:
    """
    Convenience function to redact PII from text.
    
    Uses the global redactor instance with configured mode.
    """
    redactor = get_redactor()
    return redactor.redact(text, context)


def scan_for_pii(text: str) -> List[Dict[str, Any]]:
    """Scan text for PII patterns (non-destructive)."""
    redactor = get_redactor()
    return redactor.scan(text)


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Redact PII from dictionary values."""
    redactor = get_redactor()
    return redactor.redact_dict(data)


# ============================================================================
# Common Redaction Scenarios
# ============================================================================

def redact_for_llm_prompt(prompt: str) -> str:
    """
    Redact PII specifically for LLM prompts.
    
    Uses aggressive mode to ensure no sensitive data reaches external LLMs.
    """
    redactor = PIIRedactor(mode=RedactionMode.AGGRESSIVE)
    return redactor.redact(prompt, context="llm_prompt")


def redact_for_logs(log_message: str) -> str:
    """
    Redact PII for log messages.
    
    Uses standard mode to balance security with debugging needs.
    """
    redactor = PIIRedactor(mode=RedactionMode.STANDARD)
    return redactor.redact(log_message, context="log_entry")
