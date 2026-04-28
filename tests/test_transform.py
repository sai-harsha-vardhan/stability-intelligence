"""Tests for transform_issues_to_graph module."""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock neo4j and graph modules before importing
sys.modules['neo4j'] = MagicMock()
sys.modules['graph'] = MagicMock()
sys.modules['graph.client'] = MagicMock()

from scripts.transform_issues_to_graph import (
    extract_severity,
    extract_status,
    extract_action_status,
    extract_components,
    create_incident_node,
    create_action_item_node,
)


class TestSeverityExtraction:
    """Test severity extraction from labels."""
    
    def test_sev1_critical(self):
        """Test SEV-1 maps to critical."""
        labels = ["incident-reported", "SEV-1", "urgent"]
        assert extract_severity(labels) == "critical"
    
    def test_sev1_lowercase(self):
        """Test sev-1 (lowercase) maps to critical."""
        labels = ["sev-1"]
        assert extract_severity(labels) == "critical"
    
    def test_p0_critical(self):
        """Test P0 maps to critical."""
        labels = ["P0", "incident-reported"]
        assert extract_severity(labels) == "critical"
    
    def test_sev2_high(self):
        """Test SEV-2 maps to high."""
        labels = ["SEV-2", "incident-reported"]
        assert extract_severity(labels) == "high"
    
    def test_p1_high(self):
        """Test P1 maps to high."""
        labels = ["P1"]
        assert extract_severity(labels) == "high"
    
    def test_sev3_medium(self):
        """Test SEV-3 maps to medium."""
        labels = ["SEV-3"]
        assert extract_severity(labels) == "medium"
    
    def test_p2_medium(self):
        """Test P2 maps to medium."""
        labels = ["P2", "bug"]
        assert extract_severity(labels) == "medium"
    
    def test_default_low(self):
        """Test default severity is low."""
        labels = ["incident-reported"]
        assert extract_severity(labels) == "low"
    
    def test_empty_labels(self):
        """Test empty labels default to low."""
        labels = []
        assert extract_severity(labels) == "low"


class TestStatusExtraction:
    """Test status extraction from labels."""
    
    def test_incident_completed(self):
        """Test incident completed status."""
        labels = ["incident completed", "resolved"]
        assert extract_status(labels) == "completed"
    
    def test_incident_mitigated(self):
        """Test incident mitigated status."""
        labels = ["incident mitigated"]
        assert extract_status(labels) == "mitigated"
    
    def test_rca_prepared(self):
        """Test RCA prepared status."""
        labels = ["rca prepared", "analysis"]
        assert extract_status(labels) == "prepared"
    
    def test_rca_discussed(self):
        """Test RCA discussed status."""
        labels = ["rca discussed"]
        assert extract_status(labels) == "discussed"
    
    def test_default_reported(self):
        """Test default status is reported."""
        labels = ["incident-reported"]
        assert extract_status(labels) == "reported"
    
    def test_case_insensitive(self):
        """Test status extraction is case-insensitive."""
        labels = ["RCA DISCUSSED", "INCIDENT-REPORTED"]
        assert extract_status(labels) == "discussed"


class TestActionStatusExtraction:
    """Test action item status extraction."""
    
    def test_closed_resolved(self):
        """Test closed state maps to resolved."""
        assert extract_action_status("closed") == "resolved"
    
    def test_open_open(self):
        """Test open state maps to open."""
        assert extract_action_status("open") == "open"
    
    def test_case_insensitive_closed(self):
        """Test case-insensitive closed."""
        assert extract_action_status("CLOSED") == "resolved"
    
    def test_case_insensitive_open(self):
        """Test case-insensitive open."""
        assert extract_action_status("OPEN") == "open"


class TestComponentParsing:
    """Test affected components extraction."""
    
    def test_extract_crates(self):
        """Test extracting crates/ components."""
        body = """
        The issue is in crates/router and crates/api_models.
        Also affects crates/common_utils.
        """
        components = extract_components(body)
        
        assert "crates/router" in components
        assert "crates/api_models" in components
        assert "crates/common_utils" in components
    
    def test_extract_connector(self):
        """Test extracting connector components."""
        body = "Payment failed via connector: stripe. Also tried connector:paypal."
        components = extract_components(body)
        
        # Should find connector matches
        assert len(components) > 0
    
    def test_extract_payment(self):
        """Test extracting payment components."""
        body = "Payment processing failed. Payments API returned error."
        components = extract_components(body)
        
        assert "payment" in components or "payments" in components
    
    def test_extract_multiple_components(self):
        """Test extracting multiple component types."""
        body = """
        ## Incident Details
        
        Affected components:
        - crates/router
        - Payment gateway
        - Redis cache
        - Kafka consumer
        """
        components = extract_components(body)
        
        # Should find multiple components
        assert len(components) >= 2
        assert any("router" in c or "payment" in c or "redis" in c or "kafka" in c for c in components)
    
    def test_empty_body(self):
        """Test empty body returns empty list."""
        components = extract_components("")
        assert components == []
    
    def test_none_body(self):
        """Test None body returns empty list."""
        components = extract_components(None)
        assert components == []
    
    def test_no_components(self):
        """Test body without recognizable components."""
        body = "Generic issue description without specific component mentions."
        components = extract_components(body)
        
        # Should still work, might be empty or have generic matches
        assert isinstance(components, list)


class TestIncidentNodeCreation:
    """Test Incident node creation."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mock Neo4j client."""
        client = Mock()
        client.write.return_value = [{"id": "inc-123"}]
        return client
    
    @pytest.fixture
    def sample_incident_issue(self):
        """Sample incident issue data."""
        return {
            "github_issue_number": 501,
            "title": "Payment timeout in production",
            "body": "Payment processing timing out in crates/router. SEV-1 incident.",
            "labels": ["incident-reported", "SEV-1", "payment"],
            "author": "oncall-engineer",
            "created_at": "2024-01-15T14:00:00Z",
            "updated_at": "2024-01-15T15:00:00Z",
            "state": "closed",
        }
    
    def test_create_incident_node_success(self, mock_client, sample_incident_issue):
        """Test successful incident node creation."""
        result = create_incident_node(mock_client, sample_incident_issue)
        
        assert result is True
        assert mock_client.write.called
        
        # Verify the query parameters
        call_args = mock_client.write.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        
        assert "MERGE (i:Incident" in query
        assert params["github_number"] == 501
        assert params["severity"] == "critical"
        assert "crates/router" in params["components"]
    
    def test_create_incident_node_extracts_severity(self, mock_client, sample_incident_issue):
        """Test incident node extracts correct severity."""
        sample_incident_issue["labels"] = ["incident-reported", "P1"]
        
        result = create_incident_node(mock_client, sample_incident_issue)
        
        assert result is True
        params = mock_client.write.call_args[0][1]
        assert params["severity"] == "high"
    
    def test_create_incident_node_failure(self, mock_client, sample_incident_issue):
        """Test incident node creation handles errors gracefully."""
        mock_client.write.side_effect = Exception("Database error")
        
        result = create_incident_node(mock_client, sample_incident_issue)
        
        assert result is False


class TestActionItemNodeCreation:
    """Test ActionItem node creation."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mock Neo4j client."""
        client = Mock()
        client.write.return_value = [{"id": "action-123"}]
        return client
    
    @pytest.fixture
    def sample_action_issue(self):
        """Sample action item issue data."""
        return {
            "github_issue_number": 503,
            "title": "Add timeout configuration for payment gateway",
            "body": "Implement configurable timeouts to prevent future incidents.",
            "labels": ["rca-action-item", "enhancement"],
            "author": "developer",
            "created_at": "2024-01-16T10:00:00Z",
            "updated_at": "2024-01-16T10:00:00Z",
            "state": "open",
        }
    
    def test_create_action_item_node_success(self, mock_client, sample_action_issue):
        """Test successful action item node creation."""
        result = create_action_item_node(mock_client, sample_action_issue)
        
        assert result is True
        assert mock_client.write.called
        
        # Verify the query parameters
        call_args = mock_client.write.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        
        assert "MERGE (a:ActionItem" in query or "MERGE (ai:ActionItem" in query
        assert params["github_number"] == 503
        assert params["status"] == "open"
    
    def test_create_action_item_node_closed_status(self, mock_client, sample_action_issue):
        """Test action item with closed status."""
        sample_action_issue["state"] = "closed"
        
        result = create_action_item_node(mock_client, sample_action_issue)
        
        assert result is True
        params = mock_client.write.call_args[0][1]
        assert params["status"] == "resolved"
    
    def test_create_action_item_node_failure(self, mock_client, sample_action_issue):
        """Test action item creation handles errors gracefully."""
        mock_client.write.side_effect = Exception("Database error")
        
        result = create_action_item_node(mock_client, sample_action_issue)
        
        assert result is False


class TestTransformationIntegration:
    """Integration tests for transformation pipeline."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mock Neo4j client."""
        client = Mock()
        client.write.return_value = [{"id": "test-id"}]
        client.read.return_value = []
        return client
    
    def test_incident_transformation_pipeline(self, mock_client):
        """Test full incident transformation pipeline."""
        issue = {
            "github_issue_number": 600,
            "title": "Database connection pool exhaustion",
            "body": """
            Production incident affecting crates/router and crates/storage.
            
            Severity: SEV-2
            Impact: Payment processing degraded
            """,
            "labels": ["incident-reported", "SEV-2", "database"],
            "author": "oncall",
            "created_at": "2024-01-20T10:00:00Z",
            "updated_at": "2024-01-20T11:00:00Z",
            "state": "closed",
        }
        
        result = create_incident_node(mock_client, issue)
        
        assert result is True
        params = mock_client.write.call_args[0][1]
        
        # Verify all transformations occurred
        assert params["severity"] == "high"
        assert params["github_number"] == 600
        assert len(params["components"]) > 0
        assert params["title"] == issue["title"]
    
    def test_action_item_transformation_pipeline(self, mock_client):
        """Test full action item transformation pipeline."""
        issue = {
            "github_issue_number": 601,
            "title": "Implement connection pool monitoring",
            "body": "Add monitoring and alerting for database connection pool usage.",
            "labels": ["rca-action-item", "monitoring"],
            "author": "sre-team",
            "created_at": "2024-01-20T12:00:00Z",
            "updated_at": "2024-01-20T12:00:00Z",
            "state": "open",
        }
        
        result = create_action_item_node(mock_client, issue)
        
        assert result is True
        params = mock_client.write.call_args[0][1]
        
        # Verify all transformations occurred
        assert params["status"] == "open"
        assert params["github_number"] == 601
        assert params["title"] == issue["title"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
