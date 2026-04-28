#!/usr/bin/env python3
"""
Test script for transform_issues_to_graph.py
Validates logic without requiring Neo4j connection.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock the graph client before importing transform module
class MockNeo4jClient:
    def __init__(self):
        self.queries_executed = []
    
    def write(self, query, params=None):
        self.queries_executed.append({
            'query': query,
            'params': params
        })
        return [{'id': 'test-id'}]
    
    def read(self, query, params=None):
        return []

# Replace the real client with mock
import sys
from unittest.mock import Mock, patch
sys.modules['graph.client'].get_client = Mock(return_value=MockNeo4jClient())

# Now import the transform functions
from scripts.transform_issues_to_graph import (
    extract_severity,
    extract_status,
    extract_action_status,
    extract_components,
)


def test_severity_extraction():
    """Test severity extraction from labels."""
    print("Testing severity extraction...")
    
    # Test SEV-1 -> critical
    assert extract_severity(['SEV-1', 'bug']) == 'critical'
    assert extract_severity(['sev-1']) == 'critical'
    assert extract_severity(['P0']) == 'critical'
    
    # Test SEV-2 -> high
    assert extract_severity(['SEV-2']) == 'high'
    assert extract_severity(['P1']) == 'high'
    
    # Test SEV-3 -> medium
    assert extract_severity(['SEV-3']) == 'medium'
    assert extract_severity(['P2']) == 'medium'
    
    # Test default -> low
    assert extract_severity(['bug']) == 'low'
    assert extract_severity([]) == 'low'
    
    print("✓ Severity extraction tests passed")


def test_status_extraction():
    """Test status extraction from labels."""
    print("Testing status extraction...")
    
    assert extract_status(['Incident Completed']) == 'completed'
    assert extract_status(['incident completed']) == 'completed'
    assert extract_status(['Incident Mitigated']) == 'mitigated'
    assert extract_status(['RCA Prepared']) == 'prepared'
    assert extract_status(['RCA Discussed']) == 'discussed'
    assert extract_status(['bug']) == 'reported'
    
    print("✓ Status extraction tests passed")


def test_action_status():
    """Test action item status extraction."""
    print("Testing action status extraction...")
    
    assert extract_action_status('closed') == 'resolved'
    assert extract_action_status('CLOSED') == 'resolved'
    assert extract_action_status('open') == 'open'
    assert extract_action_status('OPEN') == 'open'
    
    print("✓ Action status extraction tests passed")


def test_component_extraction():
    """Test component extraction from issue body."""
    print("Testing component extraction...")
    
    body = """
    ## Incident Report
    
    Affected components:
    - crates/router/src/connector/stripe.rs
    - crates/router/src/core/payments.rs
    - Payment gateway
    - Connector: Stripe
    """
    
    components = extract_components(body)
    assert 'crates/router' in components
    assert 'payment' in components or 'payments' in components
    
    print(f"  Found components: {components}")
    print("✓ Component extraction tests passed")


def test_cached_issues_load():
    """Test loading cached issues."""
    print("Testing cached issues load...")
    
    from scripts.github_sync import load_all_cached_issues
    
    issues = load_all_cached_issues()
    print(f"  Loaded {len(issues)} cached issues")
    
    if issues:
        # Verify structure of first issue
        first = issues[0]
        required_fields = [
            'github_issue_number',
            'title',
            'body',
            'labels',
            'issue_type'
        ]
        
        for field in required_fields:
            assert field in first, f"Missing field: {field}"
        
        print(f"  Sample issue #{first['github_issue_number']}: {first['title']}")
        print(f"  Issue type: {first['issue_type']}")
        print(f"  Labels: {first['labels']}")
    
    print("✓ Cached issues load test passed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Issue Transformation Logic")
    print("=" * 60)
    print()
    
    try:
        test_severity_extraction()
        print()
        
        test_status_extraction()
        print()
        
        test_action_status()
        print()
        
        test_component_extraction()
        print()
        
        test_cached_issues_load()
        print()
        
        print("=" * 60)
        print("All tests passed! ✓")
        print("=" * 60)
        
        return 0
    
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
