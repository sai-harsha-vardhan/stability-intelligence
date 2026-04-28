"""Paperclip dashboard filtering and execution alerting API.

See extensions/README.md for usage.

# Note: The main module is named dashboard_filters.py (underscore, not hyphen)
# for Python import compatibility. The original spec used dashboard-filters.py
# (hyphen) but hyphens are invalid in Python module names.
"""

from extensions.api.dashboard_filters import (
    get_issues_by_wave,
    get_issues_by_status,
    get_issues_by_label,
    get_issues_by_parent,
    get_issues_combined,
)
from extensions.api.execution_alerts import (
    get_routine_alerts,
    format_alert_report,
)
from extensions.api.status_validator import (
    validate_transition,
    validate_transitions_bulk,
    get_status_violations,
    format_violation_report,
)
from extensions.api.issue_tree import (
    get_issue_tree,
    build_tree,
    count_nodes,
)
from extensions.api.models import PaperclipAPIError

__all__ = [
    # Dashboard filtering
    "get_issues_by_wave",
    "get_issues_by_status",
    "get_issues_by_label",
    "get_issues_by_parent",
    "get_issues_combined",
    # Execution alerting
    "get_routine_alerts",
    "format_alert_report",
    # Status validation
    "validate_transition",
    "validate_transitions_bulk",
    "get_status_violations",
    "format_violation_report",
    # Issue tree
    "get_issue_tree",
    "build_tree",
    "count_nodes",
    # Exceptions
    "PaperclipAPIError",
]
