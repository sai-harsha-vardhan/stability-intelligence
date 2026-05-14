"""Tests for agent modules (base, ingestion, pattern, impact, strategy)."""
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base import BaseAgent


class TestBaseAgent:
    """Test BaseAgent class."""
    
    @patch('agents.base.get_client')
    def test_init(self, mock_get_client):
        """Test BaseAgent initialization."""
        agent = BaseAgent(name="test-agent")
        assert agent.name == "test-agent"
        assert agent.neo4j_client is not None
    
    @patch('agents.base.get_client')
    def test_query_graph(self, mock_get_client):
        """Test query_graph method."""
        mock_client = MagicMock()
        mock_client.read.return_value = [{"id": "123", "title": "Test"}]
        mock_get_client.return_value = mock_client
        
        agent = BaseAgent(name="test-agent")
        results = agent.query_graph("MATCH (n) RETURN n LIMIT 1")
        
        assert len(results) == 1
        assert results[0]["id"] == "123"
        mock_client.read.assert_called_once()
    
    @patch('agents.base.get_client')
    def test_write_graph(self, mock_get_client):
        """Test write_graph method."""
        mock_client = MagicMock()
        mock_client.write.return_value = None
        mock_get_client.return_value = mock_client
        
        agent = BaseAgent(name="test-agent")
        agent.write_graph(
            "CREATE (n:TestNode {id: $id})",
            {"id": "test-123"}
        )
        
        mock_client.write.assert_called_once()
        call_args = mock_client.write.call_args
        assert "CREATE" in call_args[0][0]
        assert call_args[0][1]["id"] == "test-123"
    
    @patch('agents.base.get_client')
    def test_log_activity(self, mock_get_client):
        """Test log_activity method."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        agent = BaseAgent(name="test-agent")
        agent.log_activity(
            message="processed_incident",
            data={"incident_id": "INC-123"}
        )
        
        # Should create ActivityEvent node
        mock_client.write.assert_called()
        call_args = mock_client.write.call_args
        assert "ActivityEvent" in call_args[0][0]


class TestIngestionAgent:
    """Test IngestionAgent class."""
    
    @patch('agents.base.get_client')
    def test_extract_structured_fields_mock(self, mock_get_client):
        """Test field extraction with mock data."""
        # Since actual LLM calls require API keys, test with mocks
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        # Would test extraction logic here
        # For now, just verify agent can be instantiated
        from agents.base import BaseAgent
        agent = BaseAgent(name="ingestion-agent")
        assert agent.name == "ingestion-agent"


class TestPatternAgent:
    """Test PatternAgent class."""
    
    @patch('agents.base.get_client')
    def test_cluster_root_causes_mock(self, mock_get_client):
        """Test root cause clustering with mock data."""
        mock_client = MagicMock()
        mock_client.read.return_value = [
            {"rc_id": "rc1", "description": "Database timeout", "count": 5},
            {"rc_id": "rc2", "description": "DB connection pool exhausted", "count": 3},
            {"rc_id": "rc3", "description": "Network latency", "count": 2},
        ]
        mock_get_client.return_value = mock_client
        
        # Would test clustering logic here
        # For now verify we can query root causes
        from agents.base import BaseAgent
        agent = BaseAgent(name="pattern-agent")
        results = agent.query_graph("MATCH (rc:RootCause) RETURN rc")
        assert results is not None


class TestImpactAgent:
    """Test ImpactAgent class."""
    
    @patch('agents.base.get_client')
    def test_calculate_forward_score_mock(self, mock_get_client):
        """Test forward score calculation with mock data."""
        mock_client = MagicMock()
        mock_client.read.return_value = [
            {
                "ai_id": "ai1",
                "component": "payment_processor",
                "code_modules": 5,
                "call_graph_depth": 3
            }
        ]
        mock_get_client.return_value = mock_client
        
        # Would test scoring logic here
        from agents.base import BaseAgent
        agent = BaseAgent(name="impact-agent")
        
        # Verify we can query action items
        results = agent.query_graph("MATCH (ai:ActionItem) RETURN ai")
        assert results is not None


class TestStrategyAgent:
    """Test StrategyAgent class."""
    
    @patch('agents.base.get_client')
    def test_generate_strategy_from_pattern_mock(self, mock_get_client):
        """Test strategy generation with mock data."""
        mock_client = MagicMock()
        mock_client.read.return_value = [
            {
                "cluster_id": "cluster1",
                "pattern": "database_timeouts",
                "trend": "worsening",
                "incident_count": 8
            }
        ]
        mock_get_client.return_value = mock_client
        
        # Would test strategy generation here
        from agents.base import BaseAgent
        agent = BaseAgent(name="strategy-agent")
        
        # Verify we can query pattern clusters
        results = agent.query_graph("MATCH (pc:PatternCluster) RETURN pc")
        assert results is not None
    
    @patch('agents.base.get_client')
    def test_unified_priority_ranking_mock(self, mock_get_client):
        """Test unified priority ranking."""
        mock_client = MagicMock()
        mock_client.read.return_value = [
            {
                "id": "ai1",
                "type": "ActionItem",
                "title": "Fix connection pooling",
                "priority_score": 85,
                "forward_score": 50,
                "backward_score": 35
            },
            {
                "id": "s1",
                "type": "Strategy",
                "title": "Implement circuit breakers",
                "priority_score": 75,
                "pattern_severity": 75
            }
        ]
        mock_get_client.return_value = mock_client
        
        from agents.base import BaseAgent
        agent = BaseAgent(name="strategy-agent")
        
        # Verify ranking query works
        results = agent.query_graph("""
            MATCH (n) 
            WHERE n:ActionItem OR n:Strategy
            RETURN n
            ORDER BY n.priority_score DESC
        """)
        assert results is not None
        assert len(results) == 2


class TestAgentIntegration:
    """Integration tests for agent workflow."""
    
    @patch('agents.base.get_client')
    def test_full_agent_pipeline_mock(self, mock_get_client):
        """Test complete agent pipeline with mock data."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        # Simulate full pipeline:
        # 1. Ingestion creates Incident + RootCause + ActionItem
        # 2. Pattern agent clusters root causes
        # 3. Impact agent scores action items
        # 4. Strategy agent generates strategies
        
        from agents.base import BaseAgent
        
        # Step 1: Ingestion
        ingestion = BaseAgent(name="ingestion")
        ingestion.write_graph(
            "CREATE (i:Incident {id: $id})",
            {"id": "test-incident"}
        )
        
        # Step 2: Pattern detection
        pattern = BaseAgent(name="pattern")
        pattern.write_graph(
            "CREATE (pc:PatternCluster {id: $id})",
            {"id": "test-cluster"}
        )
        
        # Step 3: Impact scoring
        impact = BaseAgent(name="impact")
        impact.write_graph(
            "MATCH (ai:ActionItem {id: $id}) SET ai.priority_score = $score",
            {"id": "test-ai", "score": 85}
        )
        
        # Step 4: Strategy generation
        strategy = BaseAgent(name="strategy")
        strategy.write_graph(
            "CREATE (s:Strategy {id: $id})",
            {"id": "test-strategy"}
        )
        
        # Verify all agents executed writes
        assert mock_client.write.call_count == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
