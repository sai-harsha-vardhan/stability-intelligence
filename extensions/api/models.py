"""
Type definitions for the Paperclip Dashboard Filtering API.

These TypedDicts are used for IDE support and documentation.
Filter functions return list[dict] — the FilterResponse type is defined
here for future FastAPI integration only.
"""

from typing import TypedDict


class IssueRef(TypedDict):
    """A single Paperclip issue as returned by the filtering API.

    Fields match the Paperclip API response shape.
    """

    id: str
    title: str
    status: str
    labels: list[str]
    parentId: str | None


class FilterResponse(TypedDict):
    """Response envelope for future FastAPI integration.

    NOTE: Filter functions currently return list[dict], not FilterResponse.
    This type is for documentation and future FastAPI wrapper use only.

    Example (future FastAPI shape)::

        {
            "query": {"wave": "wave-1", "status": "in_progress"},
            "count": 3,
            "issues": [{"id": "...", "title": "...", ...}]
        }
    """

    query: dict  # The filters that were applied
    count: int   # Total matching issues
    issues: list[IssueRef]


class PaperclipAPIError(Exception):
    """Raised when the Paperclip API request fails.

    This includes network errors, timeout exhaustion after retry,
    HTTP error responses, and non-JSON responses.

    Example::

        try:
            issues = get_issues_by_wave("wave-1")
        except PaperclipAPIError as e:
            logger.error("API error: %s", e)
    """

    pass
