"""
Paperclip Governance Extensions — HTTP server.

Wraps all three extension modules as REST endpoints and serves a
self-contained dashboard UI at the root path.

Usage::

    PAPERCLIP_COMPANY_ID=<cid> uvicorn extensions.server.app:app \\
        --host 0.0.0.0 --port 3103 --reload

Endpoints
---------
GET  /                              Dashboard HTML
GET  /health                        Service health
GET  /api/issues/filter             Filter issues (wave / status / label / parent)
GET  /api/issues/tree               Parent-child issue hierarchy
GET  /api/routines/alerts           Execution health alerts (JSON)
GET  /api/routines/alerts/report    Markdown alert report
POST /api/status/validate           Validate a single status transition
GET  /api/status/violations         Live status audit (JSON)
GET  /api/status/violations/report  Markdown violation report
GET  /api/board                     Board status: actions, escalations, digest
"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from extensions.api.config import ALLOWED_ORIGINS
from extensions.api.dashboard_filters import get_issues_combined, get_issues_needing_board
from extensions.api.execution_alerts import format_alert_report, get_routine_alerts
from extensions.api.issue_tree import build_tree, count_nodes, get_issue_tree
from extensions.api.models import PaperclipAPIError
from extensions.api.query_params import (
    IssueFilterParams,
    RoutineAlertParams,
    StatusTransitionRequest,
)
from extensions.api.status_validator import (
    format_violation_report,
    get_status_violations,
    validate_transition,
)
from extensions.security.rate_limiter import RateLimitMiddleware

_STATIC = Path(__file__).parent / "static"

app = FastAPI(
    title="Paperclip Governance Extensions",
    version="1.0.0",
    description=(
        "Dashboard filtering, execution alerting, and status validation "
        "for the Paperclip governance board."
    ),
)

# Add rate limiting middleware (must be before CORS)
app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    """Return service liveness and current UTC timestamp."""
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/", response_class=HTMLResponse, tags=["meta"])
def dashboard() -> str:
    """Serve the self-contained dashboard HTML."""
    return (_STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/issues/filter", tags=["issues"])
def filter_issues(
    wave: str | None = Query(None, description="Wave label, e.g. wave-1"),
    status: str | None = Query(None, description="Exact status string"),
    label: str | None = Query(None, description="Any label to match"),
    parent: str | None = Query(None, description="Parent issue ID"),
) -> dict:
    """Return issues matching the given filters (AND logic).

    Omit a parameter to skip that filter.  With no parameters, returns
    all non-done issues (wave filter behaviour) — use ``status`` alone
    to retrieve done issues.
    """
    # Validate query parameters using Pydantic model
    params = IssueFilterParams(wave=wave, status=status, label=label, parent=parent)

    filters = {
        k: v
        for k, v in dict(wave=params.wave, status=params.status, label=params.label, parent=params.parent).items()
        if v is not None
    }
    try:
        issues = get_issues_combined(filters)
    except (PaperclipAPIError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"filters": filters, "count": len(issues), "issues": issues}


@app.get("/api/issues/tree", tags=["issues"])
def issue_tree() -> dict:
    """Return all issues as a parent–child forest.

    Each node in the response contains all original issue fields plus a
    ``children`` list of nested child nodes.  Issues whose ``parentId``
    is absent or not in the result set appear at the top level (roots).
    """
    try:
        tree = get_issue_tree()
    except PaperclipAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"total": count_nodes(tree), "roots": len(tree), "tree": tree}


@app.get("/api/routines/alerts", tags=["routines"])
def routine_alerts(
    stale_multiplier: float = Query(2.0, description="How many intervals before stale"),
    min_stale_seconds: int = Query(3600, description="Minimum stale threshold in seconds"),
) -> dict:
    """Return all active routine execution health alerts."""
    # Validate query parameters using Pydantic model
    params = RoutineAlertParams(stale_multiplier=stale_multiplier, min_stale_seconds=min_stale_seconds)

    try:
        alerts = get_routine_alerts(
            stale_multiplier=params.stale_multiplier,
            min_stale_seconds=params.min_stale_seconds,
        )
    except PaperclipAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"count": len(alerts), "alerts": alerts}


@app.get("/api/routines/alerts/report", tags=["routines"])
def routine_alerts_report() -> dict:
    """Return the Markdown-formatted alert report plus the raw alert list."""
    try:
        alerts = get_routine_alerts()
    except PaperclipAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"count": len(alerts), "report": format_alert_report(alerts), "alerts": alerts}


@app.post("/api/status/validate", tags=["status"])
def validate_status_transition(body: StatusTransitionRequest) -> dict:
    """Check whether a status transition is permitted by the state machine.

    Returns a result dict with ``valid`` (bool) and ``reason`` (str).
    This is a pure check — no issue is modified.
    """
    return validate_transition(body.from_status, body.to_status)


@app.get("/api/status/violations", tags=["status"])
def status_violations() -> dict:
    """Scan all live issues and return any with status inconsistencies."""
    try:
        violations = get_status_violations()
    except PaperclipAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"count": len(violations), "violations": violations}


@app.get("/api/status/violations/report", tags=["status"])
def status_violations_report() -> dict:
    """Return the Markdown-formatted violation report plus the raw list."""
    try:
        violations = get_status_violations()
    except PaperclipAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {
        "count": len(violations),
        "report": format_violation_report(violations),
        "violations": violations,
    }


@app.get("/api/board", tags=["board"])
def board_api() -> dict:
    """Return board-relevant issues: action required, escalations, digest."""
    try:
        board_data = get_issues_needing_board()
    except PaperclipAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return board_data
