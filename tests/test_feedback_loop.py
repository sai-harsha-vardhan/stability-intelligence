"""Tests for feedback loop module."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# Add project root to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from feedback.loop import FeedbackLoop, FeedbackLoopResult


class TestFeedbackLoopResult:
    """Test FeedbackLoopResult class."""
    
    def test_initialization(self):
        """Test result object initializes with zeros."""
        result = FeedbackLoopResult()
        assert result.action_items_checked == 0
        assert result.strategies_checked == 0
        assert result.effective_count == 0
        assert result.ineffective_count == 0
        assert result.reinvestigations_created == 0
        assert result.errors == []
    
    def test_summary(self):
        """Test summary string generation."""
        result = FeedbackLoopResult()
        result.action_items_checked = 5
        result.strategies_checked = 3
        result.effective_count = 4
        result.ineffective_count = 2
        result.reinvestigations_created = 1
        
        summary = result.summary()
        assert "5" in summary
        assert "3" in summary
        assert "4" in summary
        assert "2" in summary
        assert "1" in summary


class TestFeedbackLoop:
    """Test FeedbackLoop class."""
    
    @patch('feedback.loop.get_client')
    def test_init(self, mock_get_client):
        """Test FeedbackLoop initialization."""
        loop = FeedbackLoop(window_days=15)
        assert loop.window_days == 15
        assert loop.client == mock_get_client.return_value
    
    @patch('feedback.loop.get_client')
    def test_count_new_incidents_with_pattern(self, mock_get_client):
        """Test counting incidents in a pattern cluster."""
        mock_client = MagicMock()
        mock_client.read.return_value = [{"incident_count": 3}]
        mock_get_client.return_value = mock_client
        
        loop = FeedbackLoop()
        count = loop._count_new_incidents_in_pattern("pattern-123", datetime.now())
        
        assert count == 3
        mock_client.read.assert_called_once()
    
    @patch('feedback.loop.get_client')
    def test_count_new_incidents_no_pattern(self, mock_get_client):
        """Test counting incidents returns 0 with no pattern id."""
        loop = FeedbackLoop()
        count = loop._count_new_incidents_in_pattern(None, datetime.now())
        assert count == 0
    
    @patch('feedback.loop.get_client')
    def test_process_action_item_effective(self, mock_get_client):
        """Test processing effective action item."""
        mock_client = MagicMock()
        mock_client.read.return_value = [{"incident_count": 0}]
        mock_get_client.return_value = mock_client
        
        loop = FeedbackLoop()
        result = FeedbackLoopResult()
        
        item = {
            "id": "ai-123",
            "resolved_at": datetime.utcnow().isoformat(),
            "pattern_cluster_id": "pc-123"
        }
        
        loop._process_action_item(item, result)
        
        assert result.action_items_checked == 1
        assert result.effective_count == 1
        mock_client.write.assert_called_once()
    
    @patch('feedback.loop.get_client')
    def test_process_action_item_ineffective(self, mock_get_client):
        """Test processing ineffective action item."""
        mock_client = MagicMock()
        mock_client.read.return_value = [{"incident_count": 2}]
        mock_get_client.return_value = mock_client
        
        loop = FeedbackLoop()
        result = FeedbackLoopResult()
        
        item = {
            "id": "ai-123",
            "resolved_at": datetime.utcnow().isoformat(),
            "pattern_cluster_id": "pc-123"
        }
        
        loop._process_action_item(item, result)
        
        assert result.action_items_checked == 1
        assert result.ineffective_count == 1
        assert result.reinvestigations_created == 1
    
    @patch('feedback.loop.get_client')
    def test_mark_action_item_effective(self, mock_get_client):
        """Test marking action item as effective."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        loop = FeedbackLoop()
        loop._mark_action_item_effective("ai-123", True)
        
        mock_client.write.assert_called_once()
        call_args = mock_client.write.call_args[0][1]
        assert call_args["id"] == "ai-123"
        assert call_args["effective"] == True


def test_run_feedback_loop_imports():
    """Test that run_feedback_loop function can be imported."""
    from feedback.loop import run_feedback_loop
    assert callable(run_feedback_loop)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
