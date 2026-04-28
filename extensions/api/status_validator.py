"""
Status transition validator for Paperclip issues.

Encodes the governance state machine defined in GOVERNANCE_LABELS.md
as a declarative transition table and exposes three public functions:

    validate_transition(from_status, to_status)
        Pure function — no API call. Tells you immediately whether a move is
        allowed and why not if it isn't. Call this before every PATCH.

    validate_transitions_bulk(pairs)
        Same as above for a list of (from, to) pairs.

    get_status_violations(api_key)
        Live audit — fetches all issues from the API and returns any that are
        in an inconsistent state (unknown status, or merge-ready without a
        github/has-pr label).

State machine (consolidated to 10 statuses on 2026-04-16):

    backlog       → todo, cancelled, wave-deferred
    todo          → in_progress, backlog, cancelled, wave-deferred
    in_progress   → in_review, in-testing, blocked, backlog, cancelled,
                    merge-ready, wave-deferred
    in-testing    → in_review, in_progress, done, blocked, cancelled
    in_review     → done, blocked, in_progress, merge-ready, in-testing
    merge-ready   → done, in_progress, cancelled
    done          → (terminal)
    blocked       → todo, in_progress, cancelled
    wave-deferred → backlog, todo, cancelled
    cancelled     → (terminal)

Absorbed statuses (removed 2026-04-16):
    needs-author-action      → use in_review
    waiting-for-pr-merge     → use merge-ready
    blocked-on-board         → use blocked
    blocked-on-design-adr    → use blocked
    blocked-on-infra         → use blocked
    blocked-on-external      → use blocked
    waiting-for-rebase       → use in_review or in_progress
    waiting-for-stabilization → use in_review or in_progress
    waiting-for-wave-promotion → use wave-deferred
"""

import logging

import requests

from extensions.api.config import (
    COMPANY_ID,
    PAPERCLIP_API_ENDPOINT,
    PAPERCLIP_API_TOKEN,
    ISSUES_LIMIT,
    REQUEST_TIMEOUT,
)
from extensions.api.models import PaperclipAPIError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State machine definition
# ---------------------------------------------------------------------------

#: All recognised status strings. Anything outside this set is unknown.
#: Consolidated to 10 statuses on 2026-04-16 (removed 9 fine-grained variants).
VALID_STATUSES: frozenset[str] = frozenset({
    "backlog",
    "todo",
    "in_progress",
    "in-testing",             # QA / test pipeline actively running
    "in_review",
    "merge-ready",            # PR approved + all checks green; queued to merge
    "done",
    "blocked",
    "wave-deferred",          # Parked until next wave promotion gate opens
    "cancelled",
})

#: Terminal statuses — no outbound transitions allowed.
TERMINAL_STATUSES: frozenset[str] = frozenset({"done", "cancelled"})

#: Statuses that definitionally require an open GitHub PR branch.
PR_REQUIRED_STATUSES: frozenset[str] = frozenset({
    "merge-ready",    # implies an approved, open PR ready to land
})

#: Valid transitions: from_status → set of allowed to_statuses.
#: Consolidated state machine (2026-04-16).
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "backlog": frozenset({
        "todo", "cancelled", "wave-deferred",
    }),
    "todo": frozenset({
        "in_progress", "backlog", "cancelled", "wave-deferred",
    }),
    "in_progress": frozenset({
        "in_review", "in-testing", "blocked", "backlog", "cancelled",
        "merge-ready", "wave-deferred",
    }),
    "in-testing": frozenset({
        "in_review", "in_progress", "done", "blocked", "cancelled",
    }),
    "in_review": frozenset({
        "done", "blocked", "in_progress", "merge-ready", "in-testing",
    }),
    "merge-ready": frozenset({
        "done", "in_progress", "cancelled",
    }),
    "done": frozenset(),      # terminal
    "blocked": frozenset({
        "todo", "in_progress", "cancelled",
    }),
    "wave-deferred": frozenset({
        "backlog", "todo", "cancelled",
    }),
    "cancelled": frozenset(),  # terminal
}

# ---------------------------------------------------------------------------
# Core validator (pure — no I/O)
# ---------------------------------------------------------------------------

def validate_transition(from_status: str, to_status: str) -> dict:
    """Check whether a status transition is allowed by the state machine.

    Pure function — makes no API calls. Safe to call before every
    ``PATCH /api/issues/:id`` that changes ``status``.

    Args:
        from_status: The issue's current status string.
        to_status: The desired new status string.

    Returns:
        dict with keys:

            * ``valid`` (bool) — ``True`` if the transition is permitted.
            * ``from_status`` (str) — echo of the input.
            * ``to_status`` (str) — echo of the input.
            * ``reason`` (str) — explanation; empty string when ``valid``
              is ``True``.

    Example::

        result = validate_transition("in_progress", "done")
        # {"valid": False, "reason": "in_progress → done is not allowed. ..."}

        result = validate_transition("in_progress", "in_review")
        # {"valid": True, "reason": "", ...}
    """
    def _result(valid: bool, reason: str = "") -> dict:
        return {
            "valid": valid,
            "from_status": from_status,
            "to_status": to_status,
            "reason": reason,
        }

    # No-op transition is always valid (status unchanged)
    if from_status == to_status:
        return _result(True)

    # Unknown from_status
    if from_status not in VALID_STATUSES:
        return _result(
            False,
            f"'{from_status}' is not a recognised status. "
            f"Known statuses: {', '.join(sorted(VALID_STATUSES))}.",
        )

    # Unknown to_status
    if to_status not in VALID_STATUSES:
        return _result(
            False,
            f"'{to_status}' is not a recognised target status. "
            f"Known statuses: {', '.join(sorted(VALID_STATUSES))}.",
        )

    # Terminal source
    if from_status in TERMINAL_STATUSES:
        return _result(
            False,
            f"'{from_status}' is a terminal status — no transitions out are "
            f"allowed. To reopen, create a new issue instead.",
        )

    # Check transition table
    allowed = VALID_TRANSITIONS.get(from_status, frozenset())
    if to_status in allowed:
        return _result(True)

    allowed_str = ", ".join(sorted(allowed)) if allowed else "(none — terminal)"
    return _result(
        False,
        f"'{from_status}' → '{to_status}' is not allowed by the governance "
        f"state machine. Valid transitions from '{from_status}': {allowed_str}.",
    )


def validate_transitions_bulk(
    pairs: list[tuple[str, str]],
) -> list[dict]:
    """Validate a list of (from_status, to_status) pairs in one call.

    Useful for batch pre-flight checks before a series of issue updates.

    Args:
        pairs: List of ``(from_status, to_status)`` tuples.

    Returns:
        list[dict]: One validation result dict per pair, in input order.
            Each dict has the same shape as :func:`validate_transition`.

    Example::

        results = validate_transitions_bulk([
            ("in_progress", "in_review"),   # valid
            ("done", "todo"),               # invalid — terminal
        ])
    """
    return [validate_transition(f, t) for f, t in pairs]


# ---------------------------------------------------------------------------
# Live audit scanner
# ---------------------------------------------------------------------------

def _fetch_issues_for_audit(api_key: str | None = None) -> list[dict]:
    """Fetch all issues for violation scanning.

    Args:
        api_key: Bearer token. Falls back to ``PAPERCLIP_API_TOKEN``.

    Returns:
        list[dict]: Raw issue dicts.

    Raises:
        PaperclipAPIError: On API failure.
    """
    token = api_key or PAPERCLIP_API_TOKEN
    url = f"{PAPERCLIP_API_ENDPOINT}/{COMPANY_ID}/issues?limit={ISSUES_LIMIT}"
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def _do_request() -> requests.Response:
        return requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

    try:
        response = _do_request()
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as exc:
        logger.warning("Issues API timed out, retrying once: %s", exc)
        try:
            response = _do_request()
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as exc2:
            raise PaperclipAPIError(
                f"Issues API timed out after retry: {exc2}"
            ) from exc2
    except requests.exceptions.RequestException as exc:
        raise PaperclipAPIError(f"Issues API request failed: {exc}") from exc

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raise PaperclipAPIError(f"Issues API returned HTTP error: {exc}") from exc

    try:
        issues: list[dict] = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise PaperclipAPIError("Issues API returned non-JSON response") from exc

    if len(issues) >= ISSUES_LIMIT:
        logger.warning(
            "Issues API returned exactly %d issues — results may be truncated.",
            ISSUES_LIMIT,
        )

    return issues


def get_status_violations(api_key: str | None = None) -> list[dict]:
    """Scan all live issues and return any with status inconsistencies.

    Checks two conditions:

    * **unknown_status** — the issue's status is not in :data:`VALID_STATUSES`.
      This usually means a typo or a status set by an agent that wasn't
      in the approved set.
    * **missing_pr_label** — the issue has a PR-implying status
      (``in_review``, ``waiting-for-pr-merge``, ``waiting-for-rebase``) but
      does not carry the ``github/has-pr`` label. These statuses are only
      reachable after a PR is opened, so the label should always be present.

    Cancelled and done issues are excluded from the ``missing_pr_label``
    check (the label may have been removed during cleanup).

    Args:
        api_key: Bearer token for the Paperclip API. Defaults to
            ``PAPERCLIP_API_TOKEN`` env var.

    Returns:
        list[dict]: Violation dicts with keys:

            * ``issue_id`` (str)
            * ``identifier`` (str) — e.g. ``"PROJ-42"``
            * ``title`` (str)
            * ``status`` (str)
            * ``kind`` (str) — ``"unknown_status"`` or ``"missing_pr_label"``
            * ``detail`` (str) — human-readable explanation

        Returns empty list if everything is consistent.

    Raises:
        PaperclipAPIError: If the API call fails.

    Example::

        violations = get_status_violations(api_key="pcp_board_abc")
        for v in violations:
            print(f"[{v['kind']}] {v['identifier']}: {v['detail']}")
    """
    issues = _fetch_issues_for_audit(api_key=api_key)
    violations: list[dict] = []

    for issue in issues:
        issue_id = issue.get("id", "unknown")
        identifier = issue.get("identifier", issue_id)
        title = issue.get("title", "")
        status = issue.get("status", "")
        labels = issue.get("labels") or []

        def _violation(kind: str, detail: str) -> dict:
            return {
                "issue_id": issue_id,
                "identifier": identifier,
                "title": title,
                "status": status,
                "kind": kind,
                "detail": detail,
            }

        # Check 1: unknown status
        if status not in VALID_STATUSES:
            violations.append(_violation(
                "unknown_status",
                f"Status '{status}' is not in the approved state machine. "
                f"Known statuses: {', '.join(sorted(VALID_STATUSES))}.",
            ))
            continue  # skip further checks for this issue

        # Check 2: PR-implying status without github/has-pr label
        if (
            status in PR_REQUIRED_STATUSES
            and status not in TERMINAL_STATUSES
            and "github/has-pr" not in labels
        ):
            violations.append(_violation(
                "missing_pr_label",
                f"Status '{status}' implies an open GitHub PR, but the "
                f"'github/has-pr' label is missing. Add the label or "
                f"revert the status.",
            ))

    return violations


def format_violation_report(violations: list[dict]) -> str:
    """Format a list of status violations into a human-readable Markdown report.

    Returns a clean healthy message if ``violations`` is empty.

    Args:
        violations: List of violation dicts from :func:`get_status_violations`.

    Returns:
        str: Markdown-formatted report.

    Example::

        print(format_violation_report([]))
        # ✅ No status violations found.
    """
    if not violations:
        return "✅ No status violations found."

    by_kind: dict[str, list[dict]] = {}
    for v in violations:
        by_kind.setdefault(v["kind"], []).append(v)

    lines = [f"## Status Violation Report — {len(violations)} issue(s)", ""]

    kind_labels = {
        "unknown_status": "🔴 Unknown Status",
        "missing_pr_label": "🟡 Missing PR Label",
    }

    for kind in ("unknown_status", "missing_pr_label"):
        items = by_kind.get(kind, [])
        if not items:
            continue
        lines.append(f"### {kind_labels.get(kind, kind)} ({len(items)})")
        for v in items:
            lines.append(f"- **{v['identifier']}** ({v['title'][:60]}) — {v['detail']}")
        lines.append("")

    return "\n".join(lines)
