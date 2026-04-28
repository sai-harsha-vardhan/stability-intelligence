"""
Issue dependency tree for Paperclip.

Builds a hierarchical parent→child tree from the flat issues list returned
by the Paperclip API, using the ``parentId`` field.  The result is a forest
(list of root nodes) where every node carries a ``children`` key.

Public functions:

    get_issue_tree(api_key)
        Live fetch + tree assembly.  Returns roots with nested children.

    build_tree(issues)
        Pure function.  Accepts a flat list of raw issue dicts and returns
        the same forest structure.  Useful for testing and offline use.

Tree node shape (all original issue fields are preserved)::

    {
        "id": "abc",
        "identifier": "PROJ-42",
        "title": "...",
        "status": "in_progress",
        "labels": ["wave-1"],
        "parentId": None,
        "children": [
            {
                "id": "def",
                "identifier": "PROJ-43",
                ...
                "children": []
            }
        ]
    }

Orphaned children (parentId points to an ID not in the result set) are
promoted to root level so they are never silently dropped.
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


def build_tree(issues: list[dict]) -> list[dict]:
    """Assemble a flat list of issue dicts into a parent–child forest.

    Pure function — no I/O.  Safe to call with cached or test data.

    Args:
        issues: Flat list of raw issue dicts.  Each dict should have at
            minimum an ``id`` field and an optional ``parentId`` field.
            All other fields are preserved unchanged.

    Returns:
        list[dict]: Root nodes (issues whose parent is absent or null),
            each carrying a ``children`` key with recursively nested nodes.
            The original issue fields are preserved on every node.

    Example::

        flat = [
            {"id": "1", "title": "Epic", "parentId": None},
            {"id": "2", "title": "Task", "parentId": "1"},
        ]
        roots = build_tree(flat)
        # roots[0]["children"][0]["title"] == "Task"
    """
    by_id: dict[str, dict] = {}
    for issue in issues:
        node = dict(issue)
        node["children"] = []
        by_id[issue["id"]] = node

    roots: list[dict] = []
    for node in by_id.values():
        parent_id = node.get("parentId")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(node)
        else:
            roots.append(node)

    return roots


def count_nodes(tree: list[dict]) -> int:
    """Count total nodes in a tree (recursive).

    Args:
        tree: List of root nodes, each with a ``children`` key.

    Returns:
        int: Total node count across all levels.
    """
    total = 0
    for node in tree:
        total += 1 + count_nodes(node.get("children", []))
    return total


def _fetch_issues(api_key: str | None = None) -> list[dict]:
    """Fetch all issues from the Paperclip API.

    Args:
        api_key: Bearer token. Falls back to ``PAPERCLIP_API_TOKEN``.

    Returns:
        list[dict]: Raw issue dicts.

    Raises:
        PaperclipAPIError: On network error, timeout, or HTTP failure.
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
        except (
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ReadTimeout,
        ) as exc2:
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


def get_issue_tree(api_key: str | None = None) -> list[dict]:
    """Fetch all Paperclip issues and return them as a parent–child forest.

    Combines :func:`_fetch_issues` and :func:`build_tree`.

    Args:
        api_key: Bearer token for the Paperclip API. Defaults to
            ``PAPERCLIP_API_TOKEN`` env var.

    Returns:
        list[dict]: Root issue nodes, each with a ``children`` key
            containing nested child nodes.  Orphaned children (whose
            ``parentId`` is not in the result set) are promoted to root.

    Raises:
        PaperclipAPIError: If the API call fails.

    Example::

        tree = get_issue_tree()
        for root in tree:
            print(root["identifier"], "→", len(root["children"]), "children")
    """
    issues = _fetch_issues(api_key=api_key)
    return build_tree(issues)
