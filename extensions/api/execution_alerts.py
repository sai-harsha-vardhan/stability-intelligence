"""
Execution alerting for Paperclip routines.

Polls the Paperclip routines API and returns structured alerts for any active
routine that is failing, has a stuck run issue, or has stopped firing.

Three alert kinds:
    execution_failed — lastRun.status is "failed" (engine-level failure before
                       an issue was even created, or explicit failure reason).
    issue_stale      — A run issue exists but its Paperclip status has not
                       reached "done" within 2× the routine's schedule interval.
    not_firing       — The routine's schedule trigger has not fired within
                       2× its expected interval.

Usage::

    import os
    from extensions.api.execution_alerts import get_routine_alerts, format_alert_report

    alerts = get_routine_alerts(api_key=os.environ["PAPERCLIP_API_TOKEN"])
    print(format_alert_report(alerts))
"""

import logging
from datetime import datetime, timezone, timedelta

import requests

from extensions.api.config import (
    COMPANY_ID,
    PAPERCLIP_API_BASE,
    PAPERCLIP_API_TOKEN,
    REQUEST_TIMEOUT,
)
from extensions.api.models import PaperclipAPIError

logger = logging.getLogger(__name__)

ROUTINES_LIMIT: int = 100
DEFAULT_INTERVAL_SECONDS: float = 86400.0

LEVEL_CRITICAL = "critical"
LEVEL_WARNING = "warning"

KIND_EXECUTION_FAILED = "execution_failed"
KIND_ISSUE_STALE = "issue_stale"
KIND_NOT_FIRING = "not_firing"

_DONE_STATUSES = frozenset({"done", "cancelled"})
_FAILED_RUN_STATUSES = frozenset({"failed"})


def _parse_utc(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string to a UTC-aware datetime.

    Handles both ``Z`` suffix and ``+00:00`` offset. Returns ``None`` if
    ``ts`` is ``None`` or cannot be parsed.

    Args:
        ts: ISO-8601 timestamp string, e.g. ``"2026-04-15T16:00:01.528Z"``.

    Returns:
        datetime | None: UTC-aware datetime, or ``None`` on failure.
    """
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        logger.warning("Could not parse timestamp: %r", ts)
        return None


def _get_schedule_interval_seconds(routine: dict) -> float | None:
    """Infer the schedule interval from a routine's trigger timestamps.

    Uses ``nextRunAt - lastFiredAt`` from the first enabled schedule trigger.
    Returns ``None`` if the interval cannot be computed (e.g. no schedule
    trigger, or missing timestamps).

    Args:
        routine: Raw routine dict from the Paperclip API.

    Returns:
        float | None: Interval in seconds, or ``None`` if unknown.
    """
    for trigger in routine.get("triggers") or []:
        if trigger.get("kind") != "schedule":
            continue
        if not trigger.get("enabled", True):
            continue
        next_run = _parse_utc(trigger.get("nextRunAt"))
        last_fired = _parse_utc(trigger.get("lastFiredAt"))
        if next_run and last_fired and next_run > last_fired:
            return (next_run - last_fired).total_seconds()
    return None


def _check_routine(
    routine: dict,
    now: datetime,
    stale_multiplier: float,
    min_stale_seconds: int,
) -> list[dict]:
    """Evaluate a single routine and return any alerts for it.

    Args:
        routine: Raw routine dict from the Paperclip API.
        now: Current UTC time (injected for testability).
        stale_multiplier: Multiplier on the schedule interval for staleness.
        min_stale_seconds: Minimum staleness threshold in seconds.

    Returns:
        list[dict]: Zero or more alert dicts for this routine.
    """
    alerts: list[dict] = []

    rid = routine.get("id", "unknown")
    title = routine.get("title", "Untitled Routine")
    status = routine.get("status", "")
    last_triggered_at = routine.get("lastTriggeredAt")
    last_run = routine.get("lastRun") or {}
    last_run_status = last_run.get("status")

    if status != "active":
        return []

    def _alert(level: str, kind: str, detail: str) -> dict:
        return {
            "routine_id": rid,
            "routine_title": title,
            "level": level,
            "kind": kind,
            "detail": detail,
            "last_triggered_at": last_triggered_at,
            "last_run_status": last_run_status,
        }

    interval_secs = _get_schedule_interval_seconds(routine)
    stale_threshold = max(
        (interval_secs or DEFAULT_INTERVAL_SECONDS) * stale_multiplier,
        float(min_stale_seconds),
    )

    if last_run_status in _FAILED_RUN_STATUSES:
        reason = last_run.get("failureReason") or "unknown reason"
        alerts.append(_alert(
            LEVEL_CRITICAL,
            KIND_EXECUTION_FAILED,
            f"Last run failed: {reason}",
        ))

    elif last_run_status == "issue_created":
        linked_issue = last_run.get("linkedIssue") or {}
        issue_status = linked_issue.get("status", "")
        if issue_status not in _DONE_STATUSES:
            triggered_at = _parse_utc(last_run.get("triggeredAt"))
            if triggered_at:
                age_secs = (now - triggered_at).total_seconds()
                if age_secs > stale_threshold:
                    identifier = linked_issue.get("identifier", rid)
                    age_hrs = age_secs / 3600
                    threshold_hrs = stale_threshold / 3600
                    alerts.append(_alert(
                        LEVEL_WARNING,
                        KIND_ISSUE_STALE,
                        (
                            f"Run issue {identifier} has been '{issue_status}' for "
                            f"{age_hrs:.1f}h (threshold: {threshold_hrs:.1f}h)"
                        ),
                    ))

    if not alerts and interval_secs is not None:
        last_triggered = _parse_utc(last_triggered_at)
        if last_triggered:
            overdue_secs = (now - last_triggered).total_seconds()
            overdue_threshold = interval_secs * stale_multiplier
            if overdue_secs > overdue_threshold:
                overdue_hrs = overdue_secs / 3600
                threshold_hrs = overdue_threshold / 3600
                alerts.append(_alert(
                    LEVEL_WARNING,
                    KIND_NOT_FIRING,
                    (
                        f"Routine last fired {overdue_hrs:.1f}h ago "
                        f"(expected every {interval_secs / 60:.0f}m, "
                        f"threshold: {threshold_hrs:.1f}h)"
                    ),
                ))

    return alerts


def _fetch_all_routines(api_key: str | None = None) -> list[dict]:
    """Fetch all routines for the company from the Paperclip API.

    Args:
        api_key: Bearer token for authentication. Falls back to
            ``PAPERCLIP_API_TOKEN`` from config if not provided.

    Returns:
        list[dict]: Raw routine dicts from the API.

    Raises:
        PaperclipAPIError: On network failure, timeout (after one retry),
            HTTP error, or non-JSON response.
    """
    token = api_key or PAPERCLIP_API_TOKEN
    url = f"{PAPERCLIP_API_BASE}/api/companies/{COMPANY_ID}/routines"
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def _do_request() -> requests.Response:
        return requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

    try:
        response = _do_request()
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as exc:
        logger.warning("Routines API request timed out, retrying once: %s", exc)
        try:
            response = _do_request()
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as exc2:
            raise PaperclipAPIError(
                f"Routines API request timed out after retry: {exc2}"
            ) from exc2
    except requests.exceptions.RequestException as exc:
        raise PaperclipAPIError(f"Routines API request failed: {exc}") from exc

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raise PaperclipAPIError(f"Routines API returned HTTP error: {exc}") from exc

    try:
        routines: list[dict] = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise PaperclipAPIError("Routines API returned non-JSON response") from exc

    if len(routines) >= ROUTINES_LIMIT:
        logger.warning(
            "Routines API returned exactly %d routines — results may be truncated.",
            ROUTINES_LIMIT,
        )

    return routines


def get_routine_alerts(
    api_key: str | None = None,
    stale_multiplier: float = 2.0,
    min_stale_seconds: int = 3600,
) -> list[dict]:
    """Fetch all active routines and return structured alerts for any problems.

    Detects three conditions on each active routine:

    * **execution_failed** (critical) — The last run failed at the engine level
      before an issue was created (e.g. a DB constraint, scheduler crash, or
      explicit failure mark).
    * **issue_stale** (warning) — A run issue was created but has not reached
      ``done`` within ``stale_multiplier`` × the routine's schedule interval.
    * **not_firing** (warning) — The routine's schedule trigger has not fired
      within ``stale_multiplier`` × its expected interval.

    Archived and paused routines are silently skipped.

    Args:
        api_key: Bearer token for the Paperclip API. Defaults to the
            ``PAPERCLIP_API_TOKEN`` environment variable.
        stale_multiplier: How many schedule intervals must pass before an
            issue or a missing trigger is considered stale. Default ``2.0``.
        min_stale_seconds: Hard minimum staleness threshold in seconds,
            regardless of the computed interval. Default ``3600`` (1 hour).

    Returns:
        list[dict]: Alert dicts with keys:

            * ``routine_id`` (str) — Paperclip routine UUID
            * ``routine_title`` (str) — Human-readable routine name
            * ``level`` (str) — ``"critical"`` or ``"warning"``
            * ``kind`` (str) — ``"execution_failed"``, ``"issue_stale"``, or
              ``"not_firing"``
            * ``detail`` (str) — Human-readable problem description
            * ``last_triggered_at`` (str | None) — ISO timestamp of last fire
            * ``last_run_status`` (str | None) — Last run status string

        Returns an empty list if all active routines are healthy.

    Raises:
        PaperclipAPIError: If the routines API call fails entirely.

    Example::

        alerts = get_routine_alerts(api_key="pcp_board_abc123")
        for a in alerts:
            print(f"[{a['level'].upper()}] {a['routine_title']}: {a['detail']}")
    """
    routines = _fetch_all_routines(api_key=api_key)
    now = datetime.now(tz=timezone.utc)
    alerts: list[dict] = []
    for routine in routines:
        alerts.extend(_check_routine(routine, now, stale_multiplier, min_stale_seconds))
    return alerts


def format_alert_report(alerts: list[dict]) -> str:
    """Format a list of routine alerts into a human-readable Markdown report.

    Returns a clean healthy message if ``alerts`` is empty, otherwise returns
    a Markdown-formatted report grouping critical alerts before warnings.

    Args:
        alerts: List of alert dicts as returned by :func:`get_routine_alerts`.

    Returns:
        str: Markdown-formatted report string.

    Example::

        print(format_alert_report([]))
        # ✅ All routines healthy.

        print(format_alert_report(alerts))
        # ## Routine Execution Alerts — 2026-04-15T16:30:00Z
        # ...
    """
    if not alerts:
        return "✅ All routines healthy."

    now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [f"## Routine Execution Alerts — {now_str}", ""]

    criticals = [a for a in alerts if a["level"] == LEVEL_CRITICAL]
    warnings = [a for a in alerts if a["level"] == LEVEL_WARNING]

    if criticals:
        lines.append(f"### 🔴 Critical ({len(criticals)})")
        for a in criticals:
            lines.append(f"- **{a['routine_title']}** — {a['detail']}")
            if a.get("last_triggered_at"):
                lines.append(f"  - Last triggered: `{a['last_triggered_at']}`")
        lines.append("")

    if warnings:
        lines.append(f"### 🟡 Warning ({len(warnings)})")
        for a in warnings:
            lines.append(f"- **{a['routine_title']}** — {a['detail']}")
            if a.get("last_triggered_at"):
                lines.append(f"  - Last triggered: `{a['last_triggered_at']}`")
        lines.append("")

    return "\n".join(lines)
