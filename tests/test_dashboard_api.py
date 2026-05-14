"""Tests for Dashboard API (FastAPI endpoints)."""
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

# Add project root to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import app after path setup
from dashboard.api.main import app


client = TestClient(app)


class TestRootEndpoint:
    """Test API root endpoint."""
    
    def test_root_returns_200(self):
        """Root endpoint should return 200 with API info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "endpoints" in data
        assert "/graph" in data["endpoints"]
        assert "/priorities" in data["endpoints"]
        assert "/health" in data["endpoints"]


class TestHealthEndpoint:
    """Test /health endpoint."""
    
    @patch('dashboard.api.main.get_client')
    def test_health_returns_200(self, mock_get_client):
        """Health endpoint should return 200 with system status."""
        # Mock Neo4j client
        mock_client = MagicMock()
        mock_client.health_check.return_value = {
            "status": "healthy",
            "components": [{"name": "neo4j", "versions": ["5.18"]}]
        }
        mock_client.read.return_value = [
            {"last_update": datetime.now(timezone.utc).isoformat(), "node_count": 100}
        ]
        mock_get_client.return_value = mock_client
        
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "components" in data
        assert "overall_healthy" in data
        assert "neo4j" in data["components"]
        assert "litellm" in data["components"]
        assert "graph_freshness" in data["components"]
    
    @patch('dashboard.api.main.get_client')
    def test_health_handles_neo4j_error(self, mock_get_client):
        """Health endpoint should handle Neo4j errors gracefully."""
        mock_get_client.side_effect = Exception("Connection failed")
        
        response = client.get("/health")
        # Should still return 200 but with degraded status
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["overall_healthy"] is False


class TestGraphEndpoint:
    """Test /graph endpoint (Cytoscape.js format)."""
    
    @patch('dashboard.api.main.get_client')
    def test_graph_returns_cytoscape_format(self, mock_get_client):
        """Graph endpoint should return nodes and edges in Cytoscape format."""
        mock_client = MagicMock()
        mock_client.read.side_effect = [
            # Nodes result
            [
                {"node": {"id": "inc-1", "label": "Incident 1", "type": "Incident", "color": "#EF4444"}},
                {"node": {"id": "ai-1", "label": "Action Item 1", "type": "ActionItem", "color": "#3B82F6"}},
            ],
            # Edges result
            [
                {"edge": {"id": "inc-1_HAS_ROOT_CAUSE_rc-1", "source": "inc-1", "target": "rc-1", "label": "HAS_ROOT_CAUSE", "weight": 0.8}},
            ],
        ]
        mock_get_client.return_value = mock_client
        
        response = client.get("/graph")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert "total_nodes" in data
        assert "total_edges" in data
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        # Check Cytoscape format
        assert "data" in data["nodes"][0]
        assert "id" in data["nodes"][0]["data"]
        assert "label" in data["nodes"][0]["data"]
        assert "type" in data["nodes"][0]["data"]
    
    @patch('dashboard.api.main.get_client')
    def test_graph_with_limit_param(self, mock_get_client):
        """Graph endpoint should respect limit parameter."""
        mock_client = MagicMock()
        mock_client.read.return_value = []
        mock_get_client.return_value = mock_client
        
        response = client.get("/graph?limit=50")
        assert response.status_code == 200
        # Verify limit was passed to query
        calls = mock_client.read.call_args_list
        assert len(calls) == 2  # nodes and edges queries


class TestPrioritiesEndpoint:
    """Test /priorities endpoint (unified ranking)."""
    
    @patch('dashboard.api.main.get_client')
    def test_priorities_returns_unified_ranking(self, mock_get_client):
        """Priorities endpoint should return combined ActionItems and Strategies."""
        mock_client = MagicMock()
        mock_client.read.side_effect = [
            # Action items
            [
                {
                    "id": "ai-1",
                    "title": "Fix payment bug",
                    "description": "Critical payment processing fix",
                    "priority_score": 95.5,
                    "forward_score": 10,
                    "backward_score": 5,
                    "blocking_multiplier": 2.0,
                    "status": "open",
                    "implementation_complexity": "high",
                    "pattern_clusters": ["payment-issues"],
                }
            ],
            # Strategies
            [
                {
                    "id": "strat-1",
                    "title": "Contract Test Suite",
                    "description": "Add comprehensive contract tests",
                    "priority_score": 88.0,
                    "forward_score": 8,
                    "backward_score": 4,
                    "blocking_multiplier": 1.5,
                    "status": "proposed",
                    "estimated_reduction": 25.0,
                }
            ],
        ]
        mock_get_client.return_value = mock_client
        
        response = client.get("/priorities")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "count" in data
        assert "generated_at" in data
        assert len(data["items"]) == 2
        # Verify sorting by priority_score (descending)
        assert data["items"][0]["priority_score"] >= data["items"][1]["priority_score"]
        # Check item structure
        item = data["items"][0]
        assert "id" in item
        assert "type" in item
        assert "title" in item
        assert "priority_score" in item
        assert "forward_score" in item
        assert "backward_score" in item
    
    @patch('dashboard.api.main.get_client')
    def test_priorities_without_strategies(self, mock_get_client):
        """Priorities endpoint should exclude strategies when requested."""
        mock_client = MagicMock()
        mock_client.read.return_value = []
        mock_get_client.return_value = mock_client
        
        response = client.get("/priorities?include_strategies=false")
        assert response.status_code == 200
        # Should only call action items query, not strategies
        assert mock_client.read.call_count == 1


class TestPatternsEndpoint:
    """Test /patterns endpoint (pattern clusters)."""
    
    @patch('dashboard.api.main.get_client')
    def test_patterns_returns_clusters(self, mock_get_client):
        """Patterns endpoint should return pattern clusters."""
        mock_client = MagicMock()
        mock_client.read.return_value = [
            {
                "id": "pc-1",
                "name": "Payment Processing Issues",
                "description": "Issues related to payment processing",
                "frequency": 15,
                "trend": "worsening",
                "incident_count": 15,
                "open_action_items": 3,
                "strategies": 1,
                "affected_components": ["payment-service", "connector-adapter"],
            }
        ]
        mock_get_client.return_value = mock_client
        
        response = client.get("/patterns")
        assert response.status_code == 200
        data = response.json()
        assert "clusters" in data
        assert "count" in data
        assert "generated_at" in data
        assert len(data["clusters"]) == 1
        cluster = data["clusters"][0]
        assert cluster["id"] == "pc-1"
        assert cluster["trend"] == "worsening"
        assert "incident_count" in cluster
    
    @patch('dashboard.api.main.get_client')
    def test_patterns_with_trend_filter(self, mock_get_client):
        """Patterns endpoint should filter by trend."""
        mock_client = MagicMock()
        mock_client.read.return_value = [
            {"id": "pc-1", "trend": "worsening"},
            {"id": "pc-2", "trend": "stable"},
        ]
        mock_get_client.return_value = mock_client
        
        response = client.get("/patterns?trend=worsening")
        assert response.status_code == 200
        data = response.json()
        # Should only return worsening patterns
        assert all(c["trend"] == "worsening" for c in data["clusters"])


class TestProgressEndpoint:
    """Test /progress endpoint (action item tracker)."""
    
    @patch('dashboard.api.main.get_client')
    def test_progress_returns_tracker(self, mock_get_client):
        """Progress endpoint should return action items with stats."""
        mock_client = MagicMock()
        mock_client.read.return_value = [
            {
                "id": "ai-1",
                "title": "Fix critical bug",
                "status": "open",
                "assignee": "john.doe",
                "priority_score": 95.0,
                "implementation_complexity": "high",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "resolved_at": None,
                "effective": None,
                "pattern_cluster_name": "critical-bugs",
            },
            {
                "id": "ai-2",
                "title": "Update docs",
                "status": "resolved",
                "assignee": "jane.doe",
                "priority_score": 50.0,
                "implementation_complexity": "low",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "effective": True,
                "pattern_cluster_name": None,
            },
        ]
        mock_get_client.return_value = mock_client
        
        response = client.get("/progress")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "stats" in data
        assert "filter" in data
        # Check stats
        assert data["stats"]["total"] == 2
        assert data["stats"]["open"] == 1
        assert data["stats"]["resolved"] == 1
        assert data["stats"]["effective_count"] == 1
    
    @patch('dashboard.api.main.get_client')
    def test_progress_with_status_filter(self, mock_get_client):
        """Progress endpoint should filter by status."""
        mock_client = MagicMock()
        mock_client.read.return_value = [
            {"id": "ai-1", "status": "open"},
            {"id": "ai-2", "status": "resolved"},
        ]
        mock_get_client.return_value = mock_client
        
        response = client.get("/progress?status_filter=open")
        assert response.status_code == 200
        data = response.json()
        assert data["filter"] == "open"
        # Should only return open items
        assert all(item["status"] == "open" for item in data["items"])

    @patch('dashboard.api.main.get_client')
    def test_progress_normalizes_done_closed_completed_to_resolved(self, mock_get_client):
        """Progress endpoint should normalize done/closed/completed status to resolved."""
        mock_client = MagicMock()
        mock_client.read.return_value = [
            {"id": "ai-1", "status": "done", "title": "T1", "assignee": "",
             "priority_score": 0.0, "implementation_complexity": "low",
             "created_at": None, "resolved_at": None, "effective": None,
             "pattern_cluster_name": None},
            {"id": "ai-2", "status": "closed", "title": "T2", "assignee": "",
             "priority_score": 0.0, "implementation_complexity": "low",
             "created_at": None, "resolved_at": None, "effective": None,
             "pattern_cluster_name": None},
            {"id": "ai-3", "status": "completed", "title": "T3", "assignee": "",
             "priority_score": 0.0, "implementation_complexity": "low",
             "created_at": None, "resolved_at": None, "effective": None,
             "pattern_cluster_name": None},
        ]
        mock_get_client.return_value = mock_client

        response = client.get("/progress")
        assert response.status_code == 200
        data = response.json()
        # All three should be normalized to resolved
        assert data["stats"]["resolved"] == 3
        assert data["stats"]["total"] == 3
        assert all(item["status"] == "resolved" for item in data["items"])

    @patch('dashboard.api.main.get_client')
    def test_stats_normalizes_done_closed_completed_in_resolved_count(self, mock_get_client):
        """Stats endpoint should count done/closed/completed as resolved."""
        mock_client = MagicMock()

        def mock_read(query, *args, **kwargs):
            # Return counts query result
            if "UNION ALL" in query:
                return [{"count": 5}, {"count": 10}, {"count": 3}, {"count": 2}]
            # Action item status breakdown
            if "ai.status" in query and "ActionItem" in query:
                return [
                    {"status": "open", "count": 4},
                    {"status": "resolved", "count": 2},
                    {"status": "done", "count": 3},
                    {"status": "closed", "count": 1},
                    {"status": "completed", "count": 2},
                ]
            if "s.status" in query:
                return [{"status": "proposed", "count": 1}]
            if "pc.trend" in query:
                return []
            return []

        mock_client.read.side_effect = mock_read
        mock_get_client.return_value = mock_client

        response = client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        # resolved = 2 + 3 + 1 + 2 = 8
        assert data["stats"]["resolved_action_items"] == 8


class TestActivityEndpoint:
    """Test /activity endpoint (agent activity)."""
    
    @patch('dashboard.api.main.get_client')
    def test_activity_returns_events(self, mock_get_client):
        """Activity endpoint should return agent activity events."""
        mock_client = MagicMock()
        mock_client.read.return_value = [
            {
                "id": "evt-1",
                "agent_name": "ingestion_agent",
                "event_type": "ingestion",
                "message": "Ingested 50 issues",
                "details": {"count": 50},
                "linked_node_id": None,
                "linked_node_type": None,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        mock_get_client.return_value = mock_client
        
        response = client.get("/activity")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "count" in data
        assert "generated_at" in data
        assert len(data["events"]) == 1
        event = data["events"][0]
        assert event["agent_name"] == "ingestion_agent"
        assert event["event_type"] == "ingestion"
    
    @patch('dashboard.api.main.get_client')
    def test_activity_with_filters(self, mock_get_client):
        """Activity endpoint should filter by agent_name and event_type."""
        mock_client = MagicMock()
        mock_client.read.return_value = [
            {"id": "evt-1", "agent_name": "ingestion_agent", "event_type": "ingestion"},
            {"id": "evt-2", "agent_name": "pattern_agent", "event_type": "pattern"},
        ]
        mock_get_client.return_value = mock_client
        
        response = client.get("/activity?agent_name=ingestion_agent")
        assert response.status_code == 200
        data = response.json()
        assert all(e["agent_name"] == "ingestion_agent" for e in data["events"])


class TestChangeFeedEndpoint:
    """Test /change-feed endpoint (real-time changes)."""
    
    @patch('dashboard.api.main.get_client')
    def test_change_feed_returns_events(self, mock_get_client):
        """Change feed endpoint should return recent changes."""
        mock_client = MagicMock()
        mock_client.read.return_value = [
            {
                "id": "evt-1",
                "event_type": "ingestion",
                "agent_name": "ingestion_agent",
                "message": "New incident detected",
                "details": {"title": "Payment failure", "severity": "P1"},
                "linked_node_id": "inc-123",
                "linked_node_type": "Incident",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        ]
        mock_get_client.return_value = mock_client
        
        response = client.get("/change-feed")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "count" in data
        assert "generated_at" in data
        event = data["events"][0]
        assert "event_type" in event
        assert "node_type" in event
        assert "severity" in event


class TestStatsEndpoint:
    """Test /stats endpoint (system statistics)."""
    
    @patch('dashboard.api.main.get_client')
    def test_stats_returns_counts(self, mock_get_client):
        """Stats endpoint should return system-wide counts."""
        mock_client = MagicMock()
        mock_client.read.side_effect = [
            # Single query result with 4 rows (UNION ALL)
            [
                {"count": 100},  # incidents
                {"count": 50},   # action_items
                {"count": 10},   # strategies
                {"count": 5},    # pattern_clusters
            ],
            # Action item status breakdown
            [{"status": "open", "count": 30}, {"status": "resolved", "count": 20}],
            # Strategy status breakdown
            [{"status": "proposed", "count": 8}, {"status": "implemented", "count": 2}],
            # Pattern trend breakdown
            [{"trend": "worsening", "count": 2}, {"trend": "stable", "count": 2}, {"trend": "improving", "count": 1}],
        ]
        mock_get_client.return_value = mock_client
        
        response = client.get("/stats")
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data
        assert "generated_at" in data
        stats = data["stats"]
        assert stats["total_incidents"] == 100
        assert stats["total_action_items"] == 50
        assert stats["open_action_items"] == 30
        assert stats["resolved_action_items"] == 20
        assert stats["worsening_patterns"] == 2
        assert stats["stable_patterns"] == 2
        assert stats["improving_patterns"] == 1


class TestNodeDetailsEndpoint:
    """Test /nodes/{node_id} endpoint."""
    
    @patch('dashboard.api.main.get_client')
    def test_node_details_returns_node_info(self, mock_get_client):
        """Node details endpoint should return node with relationships."""
        mock_client = MagicMock()
        mock_client.read.side_effect = [
            # Node details
            [{"id": "inc-1", "title": "Incident 1", "node_type": "Incident"}],
            # Relationships
            [
                {
                    "rel_type": "HAS_ROOT_CAUSE",
                    "confidence": 0.9,
                    "related_id": "rc-1",
                    "related_type": "RootCause",
                    "related_label": "Database timeout",
                    "is_outgoing": True,
                }
            ],
        ]
        mock_get_client.return_value = mock_client
        
        response = client.get("/nodes/inc-1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "inc-1"
        assert data["type"] == "Incident"
        assert "properties" in data
        assert "relationships" in data
        assert "related_nodes" in data
        assert len(data["related_nodes"]) == 1
        assert data["related_nodes"][0]["relationship"] == "HAS_ROOT_CAUSE"
    
    @patch('dashboard.api.main.get_client')
    def test_node_details_not_found(self, mock_get_client):
        """Node details endpoint should return 404 for unknown nodes."""
        mock_client = MagicMock()
        mock_client.read.return_value = []  # No node found
        mock_get_client.return_value = mock_client
        
        response = client.get("/nodes/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


class TestDocsAccessibility:
    """Test that FastAPI docs are accessible."""
    
    def test_openapi_json_accessible(self):
        """OpenAPI JSON should be accessible at /openapi.json."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data
        # Check our endpoints are documented
        assert "/graph" in data["paths"]
        assert "/priorities" in data["paths"]
        assert "/health" in data["paths"]
    
    def test_swagger_ui_accessible(self):
        """Swagger UI should be accessible at /docs."""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    def test_redoc_accessible(self):
        """ReDoc should be accessible at /redoc."""
        response = client.get("/redoc")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestCors:
    """Test CORS configuration."""
    
    def test_cors_headers_present(self):
        """CORS headers should be present on responses."""
        response = client.get("/", headers={"Origin": "http://localhost:3000"})
        assert "access-control-allow-origin" in response.headers
        # Allow either wildcard or specific origin
        assert response.headers["access-control-allow-origin"] in ["*", "http://localhost:3000"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
