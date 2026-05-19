#!/usr/bin/env python3
"""
Tests for neo4j_ingestion.py

Verifies that:
- _extract_assignee correctly pulls the first login from the `assignees` list
- ingest_issues() maps the assignee field onto ActionItem parameters
- All three issue types (action_item, incident, rca) are routed correctly
- Issues with missing github_issue_number are skipped
- Dry-run mode does not call neo4j_write

Usage:
    pytest tests/test_neo4j_ingestion.py -v
"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# Add scripts/ to path so we can import neo4j_ingestion directly
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from neo4j_ingestion import (
    _extract_assignee,
    _stable_id,
    ingest_issues,
)


def _make_action_item(
    number: int = 503,
    assignees=None,
    state: str = "open",
    title: str = "ACTION: Fix timeout",
) -> dict:
    """Build a minimal cached action-item dict."""
    if assignees is None:
        assignees = ["backend-dev-1"]
    return {
        "github_issue_number": number,
        "title": title,
        "body": "Increase timeout constant",
        "state": state,
        "labels": ["rca-action-item"],
        "author": "stability-team",
        "assignees": assignees,
        "issue_type": "action_item",
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


def _make_incident(number: int = 501) -> dict:
    return {
        "github_issue_number": number,
        "title": "INCIDENT-001: Timeout",
        "body": "Checkout timeouts at 14:00 UTC",
        "state": "closed",
        "labels": ["incident-reported", "P0"],
        "author": "oncall",
        "assignees": ["sre-lead"],
        "issue_type": "incident",
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


def _make_rca(number: int = 502) -> dict:
    return {
        "github_issue_number": number,
        "title": "RCA-001: Timeout analysis",
        "body": "Root cause: default timeout too short",
        "state": "closed",
        "labels": ["rca-discussed"],
        "author": "architect",
        "assignees": ["architect-lead"],
        "issue_type": "rca",
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


class TestExtractAssignee(unittest.TestCase):
    """Unit tests for the _extract_assignee helper."""

    def test_returns_first_login_string(self):
        issue = _make_action_item(assignees=["praveenvijay", "other-dev"])
        self.assertEqual(_extract_assignee(issue), "praveenvijay")

    def test_returns_login_from_dict(self):
        """Handles assignees stored as dicts (raw GitHub API format)."""
        issue = _make_action_item(assignees=[{"login": "praveenvijay"}])
        self.assertEqual(_extract_assignee(issue), "praveenvijay")

    def test_returns_empty_string_for_no_assignees(self):
        issue = _make_action_item(assignees=[])
        self.assertEqual(_extract_assignee(issue), "")

    def test_returns_empty_string_when_field_missing(self):
        issue = _make_action_item()
        del issue["assignees"]
        self.assertEqual(_extract_assignee(issue), "")

    def test_handles_none_assignees(self):
        issue = _make_action_item()
        issue["assignees"] = None
        self.assertEqual(_extract_assignee(issue), "")


class TestStableId(unittest.TestCase):
    """Unit tests for _stable_id determinism."""

    def test_same_inputs_give_same_id(self):
        self.assertEqual(_stable_id("ai", 503), _stable_id("ai", 503))

    def test_different_numbers_give_different_ids(self):
        self.assertNotEqual(_stable_id("ai", 503), _stable_id("ai", 504))

    def test_different_prefixes_give_different_ids(self):
        self.assertNotEqual(_stable_id("ai", 503), _stable_id("inc", 503))


class TestIngestIssues(unittest.TestCase):
    """Tests for ingest_issues() routing and parameter building."""

    def test_empty_list_returns_zero_counts(self):
        counts = ingest_issues([], dry_run=True)
        self.assertEqual(counts["action_item"], 0)
        self.assertEqual(counts["incident"], 0)
        self.assertEqual(counts["rca"], 0)
        self.assertEqual(counts["skipped"], 0)

    def test_action_item_counted(self):
        issues = [_make_action_item()]
        counts = ingest_issues(issues, dry_run=True)
        self.assertEqual(counts["action_item"], 1)
        self.assertEqual(counts["incident"], 0)
        self.assertEqual(counts["rca"], 0)

    def test_incident_counted(self):
        issues = [_make_incident()]
        counts = ingest_issues(issues, dry_run=True)
        self.assertEqual(counts["incident"], 1)
        self.assertEqual(counts["action_item"], 0)

    def test_rca_counted(self):
        issues = [_make_rca()]
        counts = ingest_issues(issues, dry_run=True)
        self.assertEqual(counts["rca"], 1)

    def test_mixed_types_counted_correctly(self):
        issues = [_make_incident(), _make_rca(), _make_action_item()]
        counts = ingest_issues(issues, dry_run=True)
        self.assertEqual(counts["incident"], 1)
        self.assertEqual(counts["rca"], 1)
        self.assertEqual(counts["action_item"], 1)
        self.assertEqual(counts["skipped"], 0)

    def test_unknown_type_skipped(self):
        issue = _make_action_item()
        issue["issue_type"] = "unknown"
        counts = ingest_issues([issue], dry_run=True)
        self.assertEqual(counts["skipped"], 1)
        self.assertEqual(counts["action_item"], 0)

    def test_missing_github_number_skipped(self):
        issue = _make_action_item()
        del issue["github_issue_number"]
        counts = ingest_issues([issue], dry_run=True)
        self.assertEqual(counts["skipped"], 1)

    # ------------------------------------------------------------------
    # Verify the assignee is correctly forwarded to neo4j_write
    # ------------------------------------------------------------------

    @patch("neo4j_ingestion.neo4j_write")
    def test_assignee_stored_in_neo4j_params(self, mock_write: MagicMock):
        """The assignee from GitHub is forwarded to UPSERT_ACTION_ITEM."""
        # Import the module-level write alias that ingest_issues uses
        mock_write.return_value = [{"id": "ai-abc", "assignee": "praveenvijay"}]

        issue = _make_action_item(assignees=["praveenvijay"])
        # Patch the write call inside the module
        import neo4j_ingestion
        with patch.object(neo4j_ingestion, "neo4j_write", mock_write):
            # We need graph.client to be importable; patch at module level
            with patch.dict("sys.modules", {"graph.client": MagicMock(write=mock_write)}):
                ingest_issues([issue], dry_run=False)

        self.assertTrue(mock_write.called)
        _, kwargs_or_args = mock_write.call_args[0], mock_write.call_args
        # Extract the params dict (second positional arg)
        call_args = mock_write.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("parameters", {})
        self.assertEqual(params.get("assignee"), "praveenvijay")

    @patch("neo4j_ingestion.neo4j_write")
    def test_empty_assignee_stored_when_no_assignees(self, mock_write: MagicMock):
        """An empty string is stored when the issue has no assignees."""
        mock_write.return_value = [{"id": "ai-abc", "assignee": ""}]
        issue = _make_action_item(assignees=[])
        import neo4j_ingestion
        with patch.object(neo4j_ingestion, "neo4j_write", mock_write):
            with patch.dict("sys.modules", {"graph.client": MagicMock(write=mock_write)}):
                ingest_issues([issue], dry_run=False)

        call_params = mock_write.call_args[0][1]
        self.assertEqual(call_params.get("assignee"), "")

    def test_dry_run_does_not_call_neo4j(self):
        """dry_run=True must never attempt to import or call graph.client."""
        issues = [_make_action_item(), _make_incident(), _make_rca()]
        # This would raise ImportError if neo4j_ingestion tried to connect
        with patch.dict("sys.modules", {}):  # graph.client NOT available
            # Should not raise even though graph.client isn't importable
            try:
                counts = ingest_issues(issues, dry_run=True)
                self.assertEqual(counts["action_item"], 1)
            except Exception as exc:
                self.fail(f"dry_run raised unexpectedly: {exc}")

    def test_closed_action_item_status_is_resolved(self):
        """Closed GitHub issues should map to status='resolved'."""
        issue = _make_action_item(state="closed")
        import neo4j_ingestion
        captured_params = {}

        def fake_write(query, params):
            captured_params.update(params)
            return [{"id": "ai-x", "assignee": params.get("assignee", "")}]

        with patch.object(neo4j_ingestion, "neo4j_write", fake_write):
            with patch.dict("sys.modules", {"graph.client": MagicMock(write=fake_write)}):
                ingest_issues([issue], dry_run=False)

        self.assertEqual(captured_params.get("status"), "resolved")

    def test_open_action_item_status_is_open(self):
        issue = _make_action_item(state="open")
        import neo4j_ingestion
        captured_params = {}

        def fake_write(query, params):
            captured_params.update(params)
            return [{"id": "ai-x", "assignee": params.get("assignee", "")}]

        with patch.object(neo4j_ingestion, "neo4j_write", fake_write):
            with patch.dict("sys.modules", {"graph.client": MagicMock(write=fake_write)}):
                ingest_issues([issue], dry_run=False)

        self.assertEqual(captured_params.get("status"), "open")


if __name__ == "__main__":
    unittest.main(verbosity=2)
