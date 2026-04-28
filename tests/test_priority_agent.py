"""Tests for Priority Estimation Agent."""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from agents.priority_agent import PriorityAgent


class TestPriorityAgent:
    """Test suite for PriorityAgent."""
    
    @pytest.fixture
    def agent(self):
        """Create a PriorityAgent instance."""
        return PriorityAgent()
    
    @pytest.fixture
    def sample_action_item(self):
        """Sample action item for testing."""
        return {
            "id": "ai-test-123",
            "title": "Add contract tests for payment API",
            "description": "Implement comprehensive contract tests to prevent backward compatibility issues",
            "status": "open",
        }
    
    def test_calculate_priority_score(self, agent):
        """Test priority score calculation with different inputs."""
        # Test Case 1: Low complexity, high impact
        score = agent._calculate_priority_score(
            forward_score=10,
            backward_score=5,
            complexity="low",
            expected_reduction=80.0,
        )
        # (10 + 5) * 0.8 / 1 = 12.0
        assert score == 12.0
        
        # Test Case 2: Medium complexity, medium impact
        score = agent._calculate_priority_score(
            forward_score=5,
            backward_score=3,
            complexity="medium",
            expected_reduction=50.0,
        )
        # (5 + 3) * 0.5 / 2 = 2.0
        assert score == 2.0
        
        # Test Case 3: High complexity, low impact
        score = agent._calculate_priority_score(
            forward_score=2,
            backward_score=1,
            complexity="high",
            expected_reduction=30.0,
        )
        # (2 + 1) * 0.3 / 3 = 0.3
        assert score == 0.3
        
        # Test Case 4: High frequency pattern, high expected reduction
        score = agent._calculate_priority_score(
            forward_score=15,
            backward_score=8,
            complexity="medium",
            expected_reduction=90.0,
        )
        # (15 + 8) * 0.9 / 2 = 10.35
        assert score == 10.35
    
    def test_find_related_pattern_direct(self, agent):
        """Test finding related pattern via direct relationship."""
        mock_result = [{
            "id": "pc-123",
            "name": "Backward Compatibility Issues",
            "frequency": 7,
            "affected_components": ["payment-api", "connector-stripe"],
        }]
        
        with patch.object(agent, 'query_graph', return_value=mock_result):
            pattern = agent.find_related_pattern({"id": "ai-test-123"})
            
            assert pattern is not None
            assert pattern["frequency"] == 7
            assert pattern["name"] == "Backward Compatibility Issues"
    
    def test_find_related_pattern_not_found(self, agent):
        """Test when no related pattern is found."""
        with patch.object(agent, 'query_graph', return_value=[]):
            pattern = agent.find_related_pattern({"id": "ai-test-123"})
            assert pattern is None
    
    def test_calculate_forward_score_with_pattern(self, agent):
        """Test forward score calculation when pattern exists."""
        mock_pattern = {
            "id": "pc-123",
            "frequency": 12,
        }
        
        with patch.object(agent, 'find_related_pattern', return_value=mock_pattern):
            score = agent._calculate_forward_score({"id": "ai-test-123"})
            assert score == 12
    
    def test_calculate_forward_score_without_pattern(self, agent):
        """Test forward score defaults to 1 when no pattern found."""
        with patch.object(agent, 'find_related_pattern', return_value=None):
            score = agent._calculate_forward_score({"id": "ai-test-123"})
            assert score == 1
    
    def test_calculate_backward_score(self, agent):
        """Test backward score calculation from historical incidents."""
        mock_result = [{"backward_count": 5}]
        
        with patch.object(agent, 'query_graph', return_value=mock_result):
            score = agent._calculate_backward_score({"id": "ai-test-123"})
            assert score == 5
    
    def test_calculate_backward_score_no_incidents(self, agent):
        """Test backward score when no historical incidents found."""
        with patch.object(agent, 'query_graph', return_value=[]):
            score = agent._calculate_backward_score({"id": "ai-test-123"})
            assert score == 0
    
    def test_estimate_complexity_with_llm_success(self, agent):
        """Test LLM complexity estimation with valid response."""
        llm_response = json.dumps({
            "implementation_complexity": "high",
            "estimated_effort_hours": 24,
            "risk_of_breaking_changes": 7,
            "expected_reduction_percent": 85,
            "reasoning": "Requires extensive refactoring of core API contracts",
        })
        
        with patch.object(agent, 'call_claude', return_value=llm_response):
            estimates = agent._estimate_complexity_with_llm(
                action_item={"id": "ai-123", "title": "Test", "description": "Test"},
                forward_score=5,
                backward_score=3,
            )
            
            assert estimates["implementation_complexity"] == "high"
            assert estimates["estimated_effort_hours"] == 24.0
            assert estimates["risk_of_breaking_changes"] == 7
            assert estimates["expected_reduction_percent"] == 85.0
    
    def test_estimate_complexity_with_llm_json_wrapped(self, agent):
        """Test LLM complexity estimation with JSON code block."""
        llm_response = """```json
{
  "implementation_complexity": "medium",
  "estimated_effort_hours": 16,
  "risk_of_breaking_changes": 4,
  "expected_reduction_percent": 60,
  "reasoning": "Moderate changes required"
}
```"""
        
        with patch.object(agent, 'call_claude', return_value=llm_response):
            estimates = agent._estimate_complexity_with_llm(
                action_item={"id": "ai-123", "title": "Test", "description": "Test"},
                forward_score=5,
                backward_score=3,
            )
            
            assert estimates["implementation_complexity"] == "medium"
            assert estimates["estimated_effort_hours"] == 16.0
    
    def test_estimate_complexity_with_llm_failure(self, agent):
        """Test LLM complexity estimation returns defaults on failure."""
        with patch.object(agent, 'call_claude', side_effect=Exception("LLM error")):
            with patch.object(agent, 'find_related_pattern', return_value=None):
                estimates = agent._estimate_complexity_with_llm(
                    action_item={"id": "ai-123", "title": "Test", "description": "Test"},
                    forward_score=5,
                    backward_score=3,
                )
                
                # Should return conservative defaults
                assert estimates["implementation_complexity"] == "medium"
                assert estimates["estimated_effort_hours"] == 8.0
                assert estimates["risk_of_breaking_changes"] == 5
                assert estimates["expected_reduction_percent"] == 30.0
    
    def test_update_action_item_scores(self, agent):
        """Test updating action item with calculated scores."""
        with patch.object(agent, 'write_graph') as mock_write:
            agent._update_action_item_scores(
                action_item_id="ai-123",
                forward_score=10,
                backward_score=5,
                priority_score=7.5,
                complexity="medium",
                estimated_effort_hours=16.0,
                risk_of_breaking_changes=4,
                expected_reduction_percent=75.0,
            )
            
            # Verify write_graph was called with correct parameters
            assert mock_write.called
            call_args = mock_write.call_args[0]
            assert "SET ai.forward_score" in call_args[0] or "SET ai." in call_args[0]
            
            # Check params were passed (may be in args or kwargs)
            if len(mock_write.call_args) > 1 and isinstance(mock_write.call_args[1], dict):
                params = mock_write.call_args[1]
                if params:  # Only check if params dict is not empty
                    assert params.get("forward_score") == 10
                    assert params.get("backward_score") == 5
                    assert params.get("priority_score") == 7.5
                    assert params.get("complexity") == "medium"
    
    def test_estimate_priority_integration(self, agent, sample_action_item):
        """Test full priority estimation flow."""
        # Mock all the dependencies
        mock_pattern = {"id": "pc-123", "frequency": 8, "affected_components": ["api"]}
        
        with patch.object(agent, 'find_related_pattern', return_value=mock_pattern), \
             patch.object(agent, 'query_graph', return_value=[{"backward_count": 4}]), \
             patch.object(agent, 'call_claude', return_value=json.dumps({
                 "implementation_complexity": "medium",
                 "estimated_effort_hours": 12,
                 "risk_of_breaking_changes": 5,
                 "expected_reduction_percent": 70,
             })), \
             patch.object(agent, 'write_graph'):
            
            # Run the estimation
            agent.estimate_priority(sample_action_item)
            
            # Verify write_graph was called
            assert agent.write_graph.called
    
    def test_run_no_action_items(self, agent):
        """Test run when no action items need scoring."""
        with patch.object(agent, '_find_unscored_action_items', return_value=[]), \
             patch.object(agent, 'log_activity'):
            
            result = agent.run()
            
            assert result["action_items_scored"] == 0
    
    def test_run_with_action_items(self, agent, sample_action_item):
        """Test run with action items to score."""
        with patch.object(agent, '_find_unscored_action_items', return_value=[sample_action_item]), \
             patch.object(agent, 'estimate_priority'), \
             patch.object(agent, 'log_activity'):
            
            result = agent.run()
            
            assert result["action_items_scored"] == 1
            assert agent.estimate_priority.called


def test_sample_calculations():
    """Generate sample calculations for documentation."""
    agent = PriorityAgent()
    
    print("\n" + "=" * 80)
    print("PRIORITY ESTIMATION AGENT - SAMPLE CALCULATIONS")
    print("=" * 80)
    
    # Sample 1: High-impact, low-complexity action
    print("\nSample 1: Contract Test Suite")
    print("-" * 40)
    forward_score = 12  # Pattern occurs 12 times
    backward_score = 7  # Would have prevented 7 past incidents
    complexity = "low"
    expected_reduction = 85.0
    
    priority = agent._calculate_priority_score(
        forward_score, backward_score, complexity, expected_reduction
    )
    
    print(f"Forward Score (pattern frequency): {forward_score}")
    print(f"Backward Score (historical impact): {backward_score}")
    print(f"Complexity: {complexity}")
    print(f"Expected Reduction: {expected_reduction}%")
    print(f"Priority Score: {priority}")
    print(f"Formula: ({forward_score} + {backward_score}) * ({expected_reduction}/100) / 1 = {priority}")
    
    # Sample 2: Medium-impact, medium-complexity action
    print("\n\nSample 2: Automated Regression Suite")
    print("-" * 40)
    forward_score = 6
    backward_score = 4
    complexity = "medium"
    expected_reduction = 60.0
    
    priority = agent._calculate_priority_score(
        forward_score, backward_score, complexity, expected_reduction
    )
    
    print(f"Forward Score (pattern frequency): {forward_score}")
    print(f"Backward Score (historical impact): {backward_score}")
    print(f"Complexity: {complexity}")
    print(f"Expected Reduction: {expected_reduction}%")
    print(f"Priority Score: {priority}")
    print(f"Formula: ({forward_score} + {backward_score}) * ({expected_reduction}/100) / 2 = {priority}")
    
    # Sample 3: Low-frequency, high-complexity action
    print("\n\nSample 3: Architecture Refactoring")
    print("-" * 40)
    forward_score = 3
    backward_score = 2
    complexity = "high"
    expected_reduction = 40.0
    
    priority = agent._calculate_priority_score(
        forward_score, backward_score, complexity, expected_reduction
    )
    
    print(f"Forward Score (pattern frequency): {forward_score}")
    print(f"Backward Score (historical impact): {backward_score}")
    print(f"Complexity: {complexity}")
    print(f"Expected Reduction: {expected_reduction}%")
    print(f"Priority Score: {priority}")
    print(f"Formula: ({forward_score} + {backward_score}) * ({expected_reduction}/100) / 3 = {priority}")
    
    # Sample 4: Critical pattern with high impact
    print("\n\nSample 4: Critical Bug Fix with High Impact")
    print("-" * 40)
    forward_score = 20
    backward_score = 15
    complexity = "medium"
    expected_reduction = 95.0
    
    priority = agent._calculate_priority_score(
        forward_score, backward_score, complexity, expected_reduction
    )
    
    print(f"Forward Score (pattern frequency): {forward_score}")
    print(f"Backward Score (historical impact): {backward_score}")
    print(f"Complexity: {complexity}")
    print(f"Expected Reduction: {expected_reduction}%")
    print(f"Priority Score: {priority}")
    print(f"Formula: ({forward_score} + {backward_score}) * ({expected_reduction}/100) / 2 = {priority}")
    
    print("\n" + "=" * 80)
    print("INTERPRETATION GUIDE")
    print("=" * 80)
    print("Priority Score > 10: CRITICAL - Implement immediately")
    print("Priority Score 5-10: HIGH - Schedule in current sprint")
    print("Priority Score 2-5: MEDIUM - Plan for next sprint")
    print("Priority Score < 2: LOW - Backlog item")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    # Run sample calculations
    test_sample_calculations()
