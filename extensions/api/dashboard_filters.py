"""
Dashboard filtering functions for the Paperclip API.

Replace manual curl + jq queries with these pre-built filter functions.
See extensions/README.md for usage examples and deployment notes.
"""

import logging
import requests

from extensions.api.config import (
    COMPANY_ID,
    DIGEST_ISSUE_ID,
    ISSUES_LIMIT,
    MERGE_QUEUE_ISSUE_ID,
    PAPERCLIP_API_BASE,
    PAPERCLIP_API_ENDPOINT,
    PAPERCLIP_API_TOKEN,
    REQUEST_TIMEOUT,
    VALID_WAVES,
)
from extensions.api.models import PaperclipAPIError

logger = logging.getLogger(__name__)


def _fetch_all_issues() -> list[dict]:
    """Fetch all issues from the Paperclip API (up to ISSUES_LIMIT).

    Constructs the request URL using config constants, adds an optional
    Bearer auth header if PAPERCLIP_API_TOKEN is set, and handles network
    errors with a single retry on timeout.

    Returns:
        list[dict]: Raw issue dicts from the API response.

    Raises:
        PaperclipAPIError: On network failure, timeout (after retry),
            HTTP error, or non-JSON response.
    """
    url = f"{PAPERCLIP_API_ENDPOINT}/{COMPANY_ID}/issues?limit={ISSUES_LIMIT}"
    headers: dict[str, str] = {}
    if PAPERCLIP_API_TOKEN:
        headers["Authorization"] = f"Bearer {PAPERCLIP_API_TOKEN}"

    def _do_request() -> requests.Response:
        return requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)

    try:
        response = _do_request()
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as exc:
        logger.warning("API request timed out, retrying once: %s", exc)
        try:
            response = _do_request()
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout) as exc2:
            raise PaperclipAPIError(
                f"API request timed out after retry: {exc2}"
            ) from exc2
    except requests.exceptions.RequestException as exc:
        raise PaperclipAPIError(f"API request failed: {exc}") from exc

    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raise PaperclipAPIError(f"API returned HTTP error: {exc}") from exc

    try:
        issues: list[dict] = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise PaperclipAPIError("API returned non-JSON response") from exc

    if len(issues) >= ISSUES_LIMIT:
        logger.warning(
            "API returned exactly %d issues — results may be truncated (v1 limitation: no pagination).",
            ISSUES_LIMIT,
        )

    return issues


def get_issues_by_wave(wave: str) -> list[dict]:
    """Return all active (non-done) issues labelled with the given wave.

    Validates that ``wave`` is one of the four recognised wave labels and
    excludes issues whose status is ``"done"`` — i.e. this function targets
    the *in-flight* work for a wave.

    Note:
        Only ``get_issues_by_wave`` and the ``wave`` key in
        ``get_issues_combined`` exclude done issues automatically.
        ``get_issues_by_label("wave-1")`` does **not** exclude done.

    Args:
        wave: One of ``"wave-1"``, ``"wave-2"``, ``"wave-3"``, ``"wave-4"``.

    Returns:
        list[dict]: Issues that carry the given wave label and are not done.

    Raises:
        ValueError: If ``wave`` is not a recognised wave label.
        PaperclipAPIError: If the API request fails.

    Example::

        issues = get_issues_by_wave("wave-1")
        # Returns all wave-1 issues whose status is not "done"
    """
    if wave not in VALID_WAVES:
        raise ValueError(
            f"Invalid wave: '{wave}'. Must be one of: {', '.join(VALID_WAVES)}"
        )

    all_issues = _fetch_all_issues()
    return [
        issue
        for issue in all_issues
        if wave in (issue.get("labels") or [])
        and issue.get("status") != "done"
    ]


def get_issues_by_status(status: str) -> list[dict]:
    """Return all issues whose status exactly matches the given value.

    No validation is performed on ``status`` — unknown values will simply
    return an empty list, which keeps this function forward-compatible with
    new Paperclip status values.

    Args:
        status: The exact status string to match, e.g. ``"in_progress"``,
            ``"blocked"``, ``"merge-ready"``.

    Returns:
        list[dict]: Issues with the given status.

    Raises:
        PaperclipAPIError: If the API request fails.

    Example::

        issues = get_issues_by_status("blocked")
        # Returns all blocked issues
    """
    all_issues = _fetch_all_issues()
    return [
        issue
        for issue in all_issues
        if issue.get("status") == status
    ]


def get_issues_by_label(label: str) -> list[dict]:
    """Return all issues that carry the given label (any status).

    Matches any label in the issue's ``labels`` list. Issues with no labels
    (including those where the ``labels`` field is ``null`` or missing) are
    safely excluded.

    Args:
        label: The exact label string to match, e.g.
            ``"priority/critical"``, ``"domain/security"``, ``"wave-1"``.

    Returns:
        list[dict]: Issues that have the given label, regardless of status.

    Raises:
        PaperclipAPIError: If the API request fails.

    Example::

        issues = get_issues_by_label("priority/critical")
        # Returns all issues with the critical priority label
    """
    all_issues = _fetch_all_issues()
    return [
        issue
        for issue in all_issues
        if label in (issue.get("labels") or [])
    ]


def get_issues_by_parent(parent_id: str) -> list[dict]:
    """Return all child issues whose parentId exactly matches ``parent_id``.

    Use this to list all subtasks of an epic or parent issue. Issues with
    no parent (where ``parentId`` is ``None`` or the field is missing) are
    safely excluded unless they happen to match the given ID.

    Args:
        parent_id: The exact Paperclip issue ID of the parent.

    Returns:
        list[dict]: Issues whose ``parentId`` equals ``parent_id``.

    Raises:
        PaperclipAPIError: If the API request fails.

    Example::

        subtasks = get_issues_by_parent("task-abc123")
        # Returns all child issues of task-abc123
    """
    all_issues = _fetch_all_issues()
    return [
        issue
        for issue in all_issues
        if issue.get("parentId") == parent_id
    ]


def get_issues_combined(filters: dict) -> list[dict]:
    """Return issues matching ALL of the given filters (AND logic).

    Recognised filter keys: ``"wave"``, ``"status"``, ``"label"``,
    ``"parent"``. Unknown keys are silently ignored.

    When ``wave`` is specified it also excludes done issues (consistent
    with :func:`get_issues_by_wave`). An empty ``filters`` dict returns
    all issues with no filtering applied.

    Args:
        filters: A dict of filter criteria. Supported keys:

            * ``"wave"`` — one of ``"wave-1"`` … ``"wave-4"``
              (validates; also excludes done issues)
            * ``"status"`` — exact status string
            * ``"label"`` — exact label string
            * ``"parent"`` — exact parent issue ID

    Returns:
        list[dict]: Issues matching every specified filter.

    Raises:
        ValueError: If the ``wave`` filter value is not recognised.
        PaperclipAPIError: If the API request fails.

    Example::

        issues = get_issues_combined({"wave": "wave-1", "status": "in_progress"})
        # Returns wave-1 issues that are currently in progress (and not done)

        all_issues = get_issues_combined({})
        # Returns all issues (no filters applied)
    """
    wave = filters.get("wave")
    status = filters.get("status")
    label = filters.get("label")
    parent = filters.get("parent")

    if wave is not None and wave not in VALID_WAVES:
        raise ValueError(
            f"Invalid wave: '{wave}'. Must be one of: {', '.join(VALID_WAVES)}"
        )

    all_issues = _fetch_all_issues()
    result = []
    for issue in all_issues:
        issue_labels = issue.get("labels") or []

        if wave is not None:
            if wave not in issue_labels:
                continue
            if issue.get("status") == "done":
                continue

        if status is not None and issue.get("status") != status:
            continue

        if label is not None and label not in issue_labels:
            continue

        if parent is not None and issue.get("parentId") != parent:
            continue

        result.append(issue)

    return result


def _get_issue_comments(issue_uuid: str) -> str:
    """Fetch latest comment from a specific issue by UUID.

    Returns the comment body as markdown, or empty string if no comments.
    """
    try:
        url = f"{PAPERCLIP_API_BASE}/api/issues/{issue_uuid}/comments"
        headers: dict[str, str] = {}
        if PAPERCLIP_API_TOKEN:
            headers["Authorization"] = f"Bearer {PAPERCLIP_API_TOKEN}"
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        comments = response.json()
        if comments:
            return comments[0].get("body", "")
    except Exception as e:
        logger.warning("Failed to fetch comments for %s: %s", issue_uuid, e)
    return ""


def _get_digest_comment(issue_uuid: str) -> str:
    """Fetch the most recent digest comment from an issue.

    Scans comments (newest first) for one whose body starts with a
    digest heading (``## Daily Board``). Returns the body as markdown,
    or empty string if no digest comment is found.
    """
    try:
        url = f"{PAPERCLIP_API_BASE}/api/issues/{issue_uuid}/comments"
        headers: dict[str, str] = {}
        if PAPERCLIP_API_TOKEN:
            headers["Authorization"] = f"Bearer {PAPERCLIP_API_TOKEN}"
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        comments = response.json()
        for comment in comments:
            body = comment.get("body", "")
            if body.startswith("## Daily Board"):
                return body
    except Exception as e:
        logger.warning("Failed to fetch digest for %s: %s", issue_uuid, e)
    return ""


def _extract_escalations(merge_queue_comment: str) -> list[str]:
    """Extract escalation lines from Merge Queue update comment."""
    if not merge_queue_comment:
        return []

    escalations = []
    in_escalations = False
    for line in merge_queue_comment.split("\n"):
        if "escalation" in line.lower() or "gate 2" in line.lower():
            in_escalations = True
            continue
        if in_escalations:
            if line.startswith("#"):
                break
            if line.strip():
                escalations.append(line.strip())

    return escalations[:5]


def get_issues_needing_board() -> dict:
    """Return board-relevant issues grouped by action type.

    Collects four categories:
    - ``action_required``: issues in in_review status with high/critical priority
    - ``blocked_on_board``: issues with blocked status and high/critical priority
    - ``escalations``: parsed from latest comment of the Merge Queue issue
    - ``daily_digest``: most recent digest comment from the Digest issue

    Returns:
        dict: With keys ``action_required``, ``action_required_count``,
              ``blocked_on_board``, ``blocked_on_board_count``, ``escalations``,
              ``escalations_count``, ``daily_digest``, ``last_updated``,
              and ``timestamp`` (ISO timestamp).
    """
    all_issues = _fetch_all_issues()

    action_required = [
        issue
        for issue in all_issues
        if issue.get("status") == "in_review"
        and issue.get("priority") in ("critical", "high")
    ]

    blocked_on_board = [
        issue
        for issue in all_issues
        if issue.get("status") == "blocked"
        and issue.get("priority") in ("critical", "high")
    ]

    merge_queue_comment = _get_issue_comments(MERGE_QUEUE_ISSUE_ID)
    escalations = _extract_escalations(merge_queue_comment)

    daily_digest = _get_digest_comment(DIGEST_ISSUE_ID)

    now = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat()

    return {
        "action_required": action_required,
        "action_required_count": len(action_required),
        "blocked_on_board": blocked_on_board,
        "blocked_on_board_count": len(blocked_on_board),
        "escalations": escalations,
        "escalations_count": len(escalations),
        "daily_digest": daily_digest,
        "last_updated": now,
        "timestamp": now,
    }
