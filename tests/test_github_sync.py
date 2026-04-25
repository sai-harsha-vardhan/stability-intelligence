#!/usr/bin/env python3
"""
Tests for GitHub sync scripts.

Usage:
    python tests/test_github_sync.py
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from github_sync import (
    transform_issue,
    generate_mock_issues,
    load_all_cached_issues,
    save_sync_state,
    load_sync_state,
)
from link_resolver import extract_issue_references
from link_resolver import (
    find_rca_to_incident_links,
    find_rca_to_action_item_links,
    build_link_graph,
)


class TestGitHubSync(unittest.TestCase):
    """Tests for github_sync.py."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.old_cache = os.environ.get("GITHUB_CACHE_DIR")
        os.environ["GITHUB_CACHE_DIR"] = self.temp_dir
    
    def tearDown(self):
        """Clean up test fixtures."""
        if self.old_cache:
            os.environ["GITHUB_CACHE_DIR"] = self.old_cache
        else:
            del os.environ["GITHUB_CACHE_DIR"]
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_transform_issue(self):
        """Test transforming a raw GitHub issue."""
        raw_issue = {
            "number": 123,
            "title": "Test Issue",
            "body": "Test body",
            "state": "open",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-02T00:00:00Z",
            "closed_at": None,
            "labels": [{"name": "rca-discussed"}],
            "user": {"login": "testuser"},
            "assignees": [],
            "milestone": None,
            "comments": 0,
        }
        
        comments = []
        linked = [456, 789]
        
        result = transform_issue(raw_issue, comments, linked)
        
        self.assertEqual(result["github_issue_number"], 123)
        self.assertEqual(result["title"], "Test Issue")
        self.assertEqual(result["issue_type"], "rca")
        self.assertEqual(result["linked_issues"], [456, 789])
        self.assertIn("synced_at", result)
    
    def test_extract_issue_references(self):
        """Test extracting issue references from text."""
        text = "Fixes #123 and relates to #456. See also GH-789"
        refs = extract_issue_references(text)
        
        self.assertIn(123, refs)
        self.assertIn(456, refs)
        self.assertIn(789, refs)
    
    def test_generate_mock_issues(self):
        """Test generating mock issues."""
        issues = generate_mock_issues()
        
        self.assertEqual(len(issues), 3)
        
        # Check all types are present
        types = {i["issue_type"] for i in issues}
        self.assertIn("incident", types)
        self.assertIn("rca", types)
        self.assertIn("action_item", types)
        
        # Check structure
        for issue in issues:
            self.assertIn("github_issue_number", issue)
            self.assertIn("title", issue)
            self.assertIn("labels", issue)
            self.assertIn("synced_at", issue)
    
    def test_load_all_cached_issues(self):
        """Test loading cached issues from JSONL."""
        sample_issues = [
            {
                "github_issue_number": 1,
                "title": "Test",
                "issue_type": "incident",
                "synced_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        
        # Create a JSONL file
        filepath = Path(self.temp_dir) / "test_issues.jsonl"
        with open(filepath, "w") as f:
            for issue in sample_issues:
                f.write(json.dumps(issue) + "\n")
        
        # Load and verify
        loaded = load_all_cached_issues()
        
        self.assertEqual(len(loaded), 1)
        self.assertIn("github_issue_number", loaded[0])
    
    def test_sync_state_save_load(self):
        """Test saving and loading sync state."""
        state = {
            "last_sync": datetime.now(timezone.utc).isoformat(),
            "repos": {
                "test/repo": {
                    "last_full_sync": "2024-01-01T00:00:00Z",
                    "issue_count": 100,
                }
            }
        }
        
        save_sync_state(state)
        loaded = load_sync_state()
        
        self.assertEqual(loaded["repos"]["test/repo"]["issue_count"], 100)


class TestLinkResolver(unittest.TestCase):
    """Tests for link_resolver.py."""
    
    def setUp(self):
        """Set up sample issues."""
        self.sample_issues = [
            {
                "github_issue_number": 501,
                "title": "INCIDENT-001: Payment timeout",
                "body": "Payment gateway timeout. Linked RCA: #502",
                "state": "closed",
                "created_at": "2024-01-15T14:00:00Z",
                "updated_at": "2024-01-15T15:00:00Z",
                "closed_at": "2024-01-15T15:00:00Z",
                "labels": ["incident-reported", "P0"],
                "author": "oncall",
                "assignees": ["sre"],
                "milestone": "Sprint-1",
                "comments_count": 1,
                "comments": [],
                "linked_issues": [502],
                "issue_type": "incident",
                "synced_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "github_issue_number": 502,
                "title": "RCA-001: Root cause analysis",
                "body": "Analysis of incident #501. Action item: #503",
                "state": "closed",
                "created_at": "2024-01-16T09:00:00Z",
                "updated_at": "2024-01-16T10:00:00Z",
                "closed_at": "2024-01-16T10:00:00Z",
                "labels": ["rca-discussed"],
                "author": "stability",
                "assignees": ["architect"],
                "milestone": "Sprint-1",
                "comments_count": 0,
                "comments": [],
                "linked_issues": [501, 503],
                "issue_type": "rca",
                "synced_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "github_issue_number": 503,
                "title": "ACTION-001: Fix timeout",
                "body": "Source RCA: #502",
                "state": "open",
                "created_at": "2024-01-16T10:00:00Z",
                "updated_at": "2024-01-16T10:00:00Z",
                "closed_at": None,
                "labels": ["rca-action-item"],
                "author": "stability",
                "assignees": ["dev"],
                "milestone": "Sprint-1",
                "comments_count": 0,
                "comments": [],
                "linked_issues": [502],
                "issue_type": "action_item",
                "synced_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
    
    def test_find_rca_to_incident_links(self):
        """Test finding RCA to incident links."""
        links = find_rca_to_incident_links(self.sample_issues)
        
        # Should find link from RCA #502 to Incident #501
        self.assertIn((502, 501), links)
    
    def test_find_rca_to_action_item_links(self):
        """Test finding RCA to action item links."""
        links = find_rca_to_action_item_links(self.sample_issues)
        
        # Should find link from RCA #502 to Action #503
        self.assertIn((502, 503), links)
    
    def test_build_link_graph(self):
        """Test building complete link graph."""
        graph = build_link_graph(self.sample_issues)
        
        # Check summary
        self.assertEqual(graph["summary"]["total_issues"], 3)
        self.assertEqual(graph["summary"]["rca_count"], 1)
        self.assertEqual(graph["summary"]["incident_count"], 1)
        self.assertEqual(graph["summary"]["action_item_count"], 1)
        
        # Check links found
        self.assertEqual(graph["summary"]["rca_to_incident_links"], 1)
        self.assertEqual(graph["summary"]["rca_to_action_item_links"], 1)
        
        # Check detailed links
        self.assertEqual(len(graph["rca_to_incident"]), 1)
        self.assertEqual(len(graph["rca_to_action_item"]), 1)
        
        # Verify no unmapped items
        self.assertEqual(len(graph["summary"]["unmapped_incidents"]), 0)
        self.assertEqual(len(graph["summary"]["unresolved_actions"]), 0)


class TestIntegration(unittest.TestCase):
    """Integration tests for the full sync pipeline."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.old_cache = os.environ.get("GITHUB_CACHE_DIR")
        os.environ["GITHUB_CACHE_DIR"] = self.temp_dir
    
    def tearDown(self):
        """Clean up test fixtures."""
        if self.old_cache:
            os.environ["GITHUB_CACHE_DIR"] = self.old_cache
        else:
            del os.environ["GITHUB_CACHE_DIR"]
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_full_pipeline(self):
        """Test the full sync and resolve pipeline."""
        # Generate mock issues
        issues = generate_mock_issues()
        
        # Save to cache
        filepath = Path(self.temp_dir) / "pipeline_test.jsonl"
        with open(filepath, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")
        
        # Load from cache
        loaded = load_all_cached_issues()
        self.assertEqual(len(loaded), 3)
        
        # Build link graph
        graph = build_link_graph(loaded)
        
        # Verify graph integrity
        self.assertEqual(graph["summary"]["total_issues"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
