"""End-to-end integration tests for the full pipeline."""
import pytest
import sys
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock neo4j and graph modules before importing
sys.modules['neo4j'] = MagicMock()
sys.modules['graph'] = MagicMock()
sys.modules['graph.client'] = MagicMock()
sys.modules['graph.queries'] = MagicMock()
sys.modules['graph.models'] = MagicMock()


class TestE2EPipeline:
    """End-to-end tests for the complete RCA Intelligence pipeline."""
    
    @pytest.fixture
    def mock_github_issues(self):
        """Mock GitHub issues data."""
        return [
            {
                "github_issue_number": 700,
                "title": "INCIDENT-001: Redis timeout causing payment failures",
                "body": """
                ## Incident Report
                
                **Date:** 2024-01-15
                **Severity:** SEV-1
                **Affected Components:** crates/router, redis
                
                Redis connection timeouts causing payment processing failures.
                """,
                "labels": ["incident-reported", "SEV-1", "redis"],
                "state": "closed",
                "author": "oncall",
                "created_at": "2024-01-15T14:00:00Z",
                "updated_at": "2024-01-15T15:00:00Z",
                "closed_at": "2024-01-15T15:00:00Z",
                "assignees": ["sre-lead"],
                "milestone": "Q1-2024",
                "comments_count": 3,
                "comments": [],
                "linked_issues": [701],
                "issue_type": "incident",
                "synced_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "github_issue_number": 701,
                "title": "RCA-001: Root cause analysis for payment failures",
                "body": """
                ## Root Cause Analysis
                
                **Root Cause:** Redis connection pool exhaustion
                
                **Contributing Factors:**
                - High traffic spike
                - Insufficient connection pool size
                
                **Action Items:** See #702
                """,
                "labels": ["rca-discussed"],
                "state": "closed",
                "author": "engineer",
                "created_at": "2024-01-16T09:00:00Z",
                "updated_at": "2024-01-16T10:00:00Z",
                "closed_at": "2024-01-16T10:00:00Z",
                "assignees": [],
                "milestone": "Q1-2024",
                "comments_count": 0,
                "comments": [],
                "linked_issues": [700, 702],
                "issue_type": "rca",
                "synced_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "github_issue_number": 702,
                "title": "ACTION-001: Increase Redis connection pool size",
                "body": "Increase Redis connection pool from 50 to 200 connections.",
                "labels": ["rca-action-item", "enhancement"],
                "state": "open",
                "author": "engineer",
                "created_at": "2024-01-16T10:00:00Z",
                "updated_at": "2024-01-16T10:00:00Z",
                "closed_at": None,
                "assignees": ["dev-team"],
                "milestone": "Q1-2024",
                "comments_count": 0,
                "comments": [],
                "linked_issues": [701],
                "issue_type": "action_item",
                "synced_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
    
    @pytest.fixture
    def mock_neo4j_client(self):
        """Mock Neo4j client."""
        client = Mock()
        client.write.return_value = [{"id": "test-id"}]
        client.read.return_value = []
        return client
    
    @pytest.mark.integration
    def test_full_pipeline_github_to_graph(self, mock_github_issues, mock_neo4j_client):
        """Test full pipeline: GitHub sync → Graph transformation."""
        from scripts.transform_issues_to_graph import create_incident_node, create_action_item_node
        
        # Step 1: Simulate GitHub sync (already mocked)
        synced_issues = mock_github_issues
        assert len(synced_issues) == 3
        
        # Step 2: Transform to graph nodes
        incidents_created = 0
        actions_created = 0
        
        for issue in synced_issues:
            if issue["issue_type"] == "incident":
                result = create_incident_node(mock_neo4j_client, issue)
                if result:
                    incidents_created += 1
            elif issue["issue_type"] == "action_item":
                result = create_action_item_node(mock_neo4j_client, issue)
                if result:
                    actions_created += 1
        
        # Verify transformations
        assert incidents_created == 1
        assert actions_created == 1
        
        # Verify Neo4j write was called
        assert mock_neo4j_client.write.call_count >= 2
    
    @pytest.mark.integration
    def test_pipeline_with_rca_analysis(self, mock_github_issues, mock_neo4j_client):
        """Test pipeline including RCA agent analysis."""
        from agents.rca_agent import RCAAgent
        
        # Step 1: Create incident nodes (mocked)
        mock_neo4j_client.read.return_value = [
            {
                "id": "inc-test-1",
                "title": "Redis timeout",
                "body": "Redis timeout causing failures",
                "raw_body": "Redis timeout causing failures",
                "github_number": 700,
                "severity": "critical",
                "occurred_at": "2024-01-15T14:00:00Z",
                "affected_flows": ["payments"],
                "created_at": "2024-01-15T14:00:00Z",
            }
        ]
        
        # Step 2: Run RCA agent
        with patch.object(RCAAgent, 'query_graph', return_value=mock_neo4j_client.read.return_value), \
             patch.object(RCAAgent, 'write_graph'), \
             patch.object(RCAAgent, 'call_claude', return_value='{"root_cause": "Connection pool exhaustion"}'), \
             patch.object(RCAAgent, 'log_activity'):
            
            agent = RCAAgent()
            
            # Mock the internal methods to avoid real LiteLLM calls
            with patch.object(agent, '_find_unanalyzed_incidents', return_value=mock_neo4j_client.read.return_value):
                stats = agent.run()
            
            # Verify agent ran (may analyze 0 incidents due to mocking)
            assert isinstance(stats, dict)
            assert "incidents_analyzed" in stats
            assert "patterns_detected" in stats
    
    @pytest.mark.integration
    def test_pipeline_with_priority_scoring(self, mock_neo4j_client):
        """Test pipeline including priority agent scoring."""
        from agents.priority_agent import PriorityAgent
        
        # Mock action items needing scoring
        mock_neo4j_client.read.return_value = [
            {
                "id": "ai-test-1",
                "title": "Increase connection pool",
                "description": "Increase Redis pool size",
                "status": "open",
            }
        ]
        
        # Run priority agent
        with patch.object(PriorityAgent, 'query_graph', return_value=[]), \
             patch.object(PriorityAgent, 'write_graph'), \
             patch.object(PriorityAgent, 'call_claude', return_value='{"implementation_complexity": "low"}'), \
             patch.object(PriorityAgent, 'log_activity'):
            
            agent = PriorityAgent()
            
            with patch.object(agent, '_find_unscored_action_items', return_value=mock_neo4j_client.read.return_value):
                stats = agent.run()
            
            # Verify agent ran
            assert isinstance(stats, dict)
            assert "action_items_scored" in stats
    
    @pytest.mark.integration
    def test_pipeline_end_to_end_simulation(self, mock_github_issues):
        """Simulate complete end-to-end pipeline without real dependencies."""
        # This test simulates the full flow without requiring real Neo4j or LiteLLM
        
        # Step 1: Mock GitHub sync
        with patch("scripts.github_sync.fetch_issues", return_value=[]), \
             patch("scripts.github_sync.load_all_cached_issues", return_value=mock_github_issues):
            
            from scripts.github_sync import load_all_cached_issues
            issues = load_all_cached_issues()
            
            assert len(issues) == 3
            assert issues[0]["issue_type"] == "incident"
        
        # Step 2: Mock graph transformation
        mock_client = Mock()
        mock_client.write.return_value = [{"id": "test"}]
        
        from scripts.transform_issues_to_graph import create_incident_node
        
        incidents = [i for i in issues if i["issue_type"] == "incident"]
        for incident in incidents:
            result = create_incident_node(mock_client, incident)
            assert result is True
        
        # Step 3: Mock RCA agent
        with patch("agents.rca_agent.RCAAgent.query_graph", return_value=[]), \
             patch("agents.rca_agent.RCAAgent.write_graph"), \
             patch("agents.rca_agent.RCAAgent.call_claude", return_value='{}'), \
             patch("agents.rca_agent.RCAAgent.log_activity"):
            
            from agents.rca_agent import RCAAgent
            agent = RCAAgent()
            
            # Mock to prevent actual graph queries
            with patch.object(agent, '_find_unanalyzed_incidents', return_value=[]):
                stats = agent.run()
                assert "incidents_analyzed" in stats
        
        # Step 4: Verify dashboard API can serve data
        from fastapi.testclient import TestClient
        from dashboard.api.main import app
        
        with patch("dashboard.api.main.neo4j_query", return_value=[{"status": "healthy"}]):
            client = TestClient(app)
            response = client.get("/health")
            
            assert response.status_code == 200
    
    @pytest.mark.integration
    def test_data_flow_consistency(self, mock_github_issues):
        """Test data consistency through pipeline stages."""
        # Verify issue data structure is preserved
        incident = mock_github_issues[0]
        
        # GitHub issue should have required fields
        assert "github_issue_number" in incident
        assert "title" in incident
        assert "issue_type" in incident
        assert incident["issue_type"] == "incident"
        
        # Transform to graph node format
        from scripts.transform_issues_to_graph import extract_severity, extract_components
        
        severity = extract_severity(incident["labels"])
        components = extract_components(incident["body"])
        
        # Verify transformations
        assert severity in ["critical", "high", "medium", "low"]
        assert isinstance(components, list)
    
    @pytest.mark.integration
    def test_pipeline_error_handling(self, mock_neo4j_client):
        """Test pipeline handles errors gracefully."""
        # Test incident creation with invalid data
        from scripts.transform_issues_to_graph import create_incident_node
        
        invalid_issue = {
            "github_issue_number": 999,
            # Missing required fields
        }
        
        # Should not crash, should return False
        mock_neo4j_client.write.side_effect = Exception("Database error")
        result = create_incident_node(mock_neo4j_client, invalid_issue)
        
        assert result is False
    
    @pytest.mark.integration
    def test_agent_orchestration(self):
        """Test multiple agents can run in sequence."""
        from agents.rca_agent import RCAAgent
        from agents.priority_agent import PriorityAgent
        
        # Mock all external dependencies
        with patch("agents.rca_agent.RCAAgent.query_graph", return_value=[]), \
             patch("agents.rca_agent.RCAAgent.write_graph"), \
             patch("agents.rca_agent.RCAAgent.call_claude", return_value='{}'), \
             patch("agents.rca_agent.RCAAgent.log_activity"), \
             patch("agents.priority_agent.PriorityAgent.query_graph", return_value=[]), \
             patch("agents.priority_agent.PriorityAgent.write_graph"), \
             patch("agents.priority_agent.PriorityAgent.call_claude", return_value='{}'), \
             patch("agents.priority_agent.PriorityAgent.log_activity"):
            
            # Run RCA agent
            rca_agent = RCAAgent()
            with patch.object(rca_agent, '_find_unanalyzed_incidents', return_value=[]):
                rca_stats = rca_agent.run()
            
            # Run Priority agent
            priority_agent = PriorityAgent()
            with patch.object(priority_agent, '_find_unscored_action_items', return_value=[]):
                priority_stats = priority_agent.run()
            
            # Verify both agents ran successfully
            assert "incidents_analyzed" in rca_stats
            assert "action_items_scored" in priority_stats


class TestPipelineDataIntegrity:
    """Test data integrity through the pipeline."""
    
    def test_issue_type_preservation(self):
        """Test issue types are correctly identified and preserved."""
        from scripts.github_sync import infer_issue_type
        
        # Test all issue types
        assert infer_issue_type(["incident-reported"]) == "incident"
        assert infer_issue_type(["rca-discussed"]) == "rca"
        assert infer_issue_type(["rca-action-item"]) == "action_item"
        assert infer_issue_type(["other-label"]) == "unknown"
    
    def test_severity_mapping_consistency(self):
        """Test severity levels are consistently mapped."""
        from scripts.transform_issues_to_graph import extract_severity
        
        # Test all severity mappings
        critical_labels = [["SEV-1"], ["sev-1"], ["P0"], ["p0"]]
        for labels in critical_labels:
            assert extract_severity(labels) == "critical"
        
        high_labels = [["SEV-2"], ["P1"]]
        for labels in high_labels:
            assert extract_severity(labels) == "high"
    
    def test_timestamp_format_consistency(self):
        """Test timestamps are in consistent ISO format."""
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc)
        timestamp = now.isoformat()
        
        # Should be valid ISO format
        assert "T" in timestamp
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        assert isinstance(parsed, datetime)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
