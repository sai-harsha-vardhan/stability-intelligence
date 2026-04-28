"""
Configuration for the Paperclip Dashboard Filtering API.

Environment variables:
    PAPERCLIP_API_BASE (optional): Base URL of the Paperclip server.
        Defaults to ``http://localhost:3100``.
    PAPERCLIP_COMPANY_ID (required): The Paperclip company ID to query against.
    PAPERCLIP_API_TOKEN (optional): Bearer token for API authentication.
"""

import os

# ---------------------------------------------------------------------------
# API endpoint constants
# ---------------------------------------------------------------------------

PAPERCLIP_API_BASE: str = os.environ.get("PAPERCLIP_API_BASE", "http://localhost:3100")
PAPERCLIP_API_ENDPOINT: str = f"{PAPERCLIP_API_BASE}/api/companies"

# ---------------------------------------------------------------------------
# Company ID — required; read from environment variable
# ---------------------------------------------------------------------------

_company_id_raw = os.environ.get("PAPERCLIP_COMPANY_ID", "").strip()
if not _company_id_raw:
    raise ValueError(
        "PAPERCLIP_COMPANY_ID environment variable is required. "
        "Set it to your Paperclip company ID before importing this module."
    )
COMPANY_ID: str = _company_id_raw

# ---------------------------------------------------------------------------
# Optional auth token
# ---------------------------------------------------------------------------

PAPERCLIP_API_TOKEN: str = os.environ.get("PAPERCLIP_API_TOKEN", "").strip()

# ---------------------------------------------------------------------------
# Well-known issue UUIDs (set via environment or configure.sh)
# ---------------------------------------------------------------------------

DIGEST_ISSUE_ID: str = os.environ.get("DIGEST_ISSUE_ID", "{DIGEST_ISSUE_ID}")
MERGE_QUEUE_ISSUE_ID: str = os.environ.get("MERGE_QUEUE_ISSUE_ID", "{MERGE_QUEUE_ISSUE_ID}")

# ---------------------------------------------------------------------------
# Filter and request constants
# ---------------------------------------------------------------------------

VALID_WAVES: tuple[str, ...] = ("wave-1", "wave-2", "wave-3", "wave-4")

# Timeout as (connect_timeout, read_timeout) in seconds
REQUEST_TIMEOUT: tuple[int, int] = (5, 30)

# Maximum number of issues to fetch per request (v1 limitation — no pagination)
ISSUES_LIMIT: int = 500

# ---------------------------------------------------------------------------
# CORS Configuration — security requirement DE-002
# ---------------------------------------------------------------------------

# Comma-separated list of allowed origins. Defaults to localhost for safety.
# Example: "https://dashboard.example.com,https://admin.example.com"
ALLOWED_ORIGINS_RAW: str = os.environ.get("ALLOWED_ORIGINS", "").strip()
if ALLOWED_ORIGINS_RAW:
    ALLOWED_ORIGINS: list[str] = [origin.strip() for origin in ALLOWED_ORIGINS_RAW.split(",")]
else:
    # Default to localhost only for security
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]
