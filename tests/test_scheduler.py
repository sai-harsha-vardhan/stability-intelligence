"""Tests for the APScheduler runner and health monitoring."""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from scheduler.runner import SchedulerRunner
from scheduler.health import HealthMonitor, HealthStatus, format_health_report


class TestSchedulerRunner:
    """Test suite for SchedulerRunner."""

    def test_initialization_defaults(self, mock_env_vars):
        """Test scheduler initializes with default values."""
        runner = SchedulerRunner()
        assert runner.github_interval_hours == 6
        assert runner.strategy_cron == "0 9 * * 1"
        assert runner._shutdown_requested is False

    def test_initialization_custom_values(self, mock_env_vars):
        """Test scheduler initializes with custom values."""
        runner = SchedulerRunner(
            github_interval_hours=4,
            strategy_cron="0 12 * * 3",
        )
        assert runner.github_interval_hours == 4
        assert runner.strategy_cron == "0 12 * * 3"

    def test_signal_handler_sets_shutdown_flag(self, mock_env_vars):
        """Test signal handler sets shutdown flag."""
        runner = SchedulerRunner()
        runner.scheduler = Mock()
        runner.scheduler.shutdown = Mock()
        runner.scheduler.running = True
        
        # Simulate SIGTERM
        runner._signal_handler(15, None)
        
        assert runner._shutdown_requested is True
        runner.scheduler.shutdown.assert_called_once_with(wait=True)

    def test_setup_jobs_registers_all_jobs(self, mock_env_vars):
        """Test that all jobs are registered during setup."""
        runner = SchedulerRunner()
        runner.scheduler = Mock()
        runner.scheduler.add_job = Mock()
        runner.scheduler.add_listener = Mock()
        
        runner.setup_jobs()
        
        # Should register 4 jobs
        assert runner.scheduler.add_job.call_count == 4
        
        # Check job IDs
        job_calls = [call[1]["id"] for call in runner.scheduler.add_job.call_args_list]
        assert "github_sync" in job_calls
        assert "strategy_agent" in job_calls
        assert "feedback_loop" in job_calls
        assert "health_check" in job_calls

    def test_job_listener_logs_success(self, mock_env_vars, caplog):
        """Test job listener logs successful job execution."""
        runner = SchedulerRunner()
        event = Mock()
        event.job_id = "test_job"
        event.exception = None
        
        with caplog.at_level("INFO"):
            runner._job_listener(event)
        
        assert "test_job completed successfully" in caplog.text

    def test_job_listener_logs_failure(self, mock_env_vars, caplog):
        """Test job listener logs failed job execution."""
        runner = SchedulerRunner()
        runner.health_monitor = Mock()
        runner.health_monitor.send_alert = Mock()
        
        event = Mock()
        event.job_id = "test_job"
        event.exception = RuntimeError("Test error")
        
        with caplog.at_level("ERROR"):
            runner._job_listener(event)
        
        assert "test_job failed" in caplog.text
        runner.health_monitor.send_alert.assert_called_once()


class TestSchedulerRunnerJobs:
    """Test suite for individual job execution."""

    @patch("scripts.neo4j_ingestion.run_ingestion", return_value={"action_item": 0, "incident": 0, "rca": 0, "skipped": 0})
    @patch("scripts.github_sync.bulk_sync")
    def test_run_github_sync_bulk(self, mock_bulk_sync, mock_run_ingestion, mock_env_vars):
        """Test bulk GitHub sync execution."""
        mock_bulk_sync.return_value = 100
        runner = SchedulerRunner()
        
        result = runner.run_github_sync(bulk=True)
        
        assert result == 100
        mock_bulk_sync.assert_called_once()

    @patch("scripts.neo4j_ingestion.run_ingestion", return_value={"action_item": 0, "incident": 0, "rca": 0, "skipped": 0})
    @patch("scripts.github_sync.incremental_sync")
    def test_run_github_sync_incremental(self, mock_incremental, mock_run_ingestion, mock_env_vars):
        """Test incremental GitHub sync execution."""
        mock_incremental.return_value = 5
        runner = SchedulerRunner()
        
        result = runner.run_github_sync(bulk=False)
        
        assert result == 5
        mock_incremental.assert_called_once()

    @patch("agents.strategy_agent.StrategyAgent")
    def test_run_strategy_agent(self, mock_strategy_class, mock_env_vars):
        """Test strategy agent execution."""
        mock_agent = Mock()
        mock_strategy_class.return_value = mock_agent
        runner = SchedulerRunner()
        
        runner.run_strategy_agent()
        
        mock_strategy_class.assert_called_once()
        mock_agent.run.assert_called_once()

    @patch("feedback.loop.run_feedback_loop")
    def test_run_feedback_loop(self, mock_feedback_loop, mock_env_vars):
        """Test feedback loop execution."""
        mock_result = Mock()
        mock_result.effective_count = 3
        mock_result.ineffective_count = 1
        mock_feedback_loop.return_value = mock_result
        runner = SchedulerRunner()
        
        result = runner.run_feedback_loop()
        
        assert result == mock_result
        mock_feedback_loop.assert_called_once()

    def test_run_health_check(self, mock_env_vars):
        """Test health check execution."""
        runner = SchedulerRunner()
        runner.health_monitor = Mock()
        runner.health_monitor.check_all.return_value = [
            HealthStatus(name="test", status="healthy", message="OK")
        ]
        
        result = runner.run_health_check()
        
        assert len(result) == 1
        assert result[0].status == "healthy"


class TestHealthMonitor:
    """Test suite for HealthMonitor."""

    def test_initialization(self, mock_env_vars):
        """Test health monitor initialization."""
        monitor = HealthMonitor()
        assert monitor.neo4j_uri == "bolt://localhost:7687"
        assert monitor.litellm_url == "http://localhost:4000"

    def test_check_all_runs_all_checks(self):
        """Test that check_all runs all health checks."""
        monitor = HealthMonitor()
        monitor.check_neo4j = Mock(return_value=HealthStatus("neo4j", "healthy", "OK"))
        monitor.check_litellm = Mock(return_value=HealthStatus("litellm", "healthy", "OK"))
        monitor.check_graph_staleness = Mock(return_value=HealthStatus("graph", "healthy", "OK"))
        monitor.send_alert = Mock()
        
        results = monitor.check_all()
        
        assert len(results) == 3
        monitor.check_neo4j.assert_called_once()
        monitor.check_litellm.assert_called_once()
        monitor.check_graph_staleness.assert_called_once()

    def test_check_neo4j_healthy(self):
        """Test Neo4j health check when healthy."""
        monitor = HealthMonitor()
        monitor.graph_client = Mock()
        monitor.graph_client.health_check.return_value = {
            "status": "healthy",
            "components": [{"name": "neo4j-kernel"}],
        }
        
        result = monitor.check_neo4j()
        
        assert result.status == "healthy"
        assert result.name == "neo4j"

    def test_check_neo4j_unhealthy(self):
        """Test Neo4j health check when unhealthy."""
        monitor = HealthMonitor()
        monitor.graph_client = Mock()
        monitor.graph_client.health_check.return_value = {
            "status": "unhealthy",
            "error": "Connection refused",
        }
        
        result = monitor.check_neo4j()
        
        assert result.status == "unhealthy"

    @patch("requests.get")
    def test_check_litellm_healthy(self, mock_get):
        """Test LiteLLM health check when healthy."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"model_list": ["claude-3-opus"]}
        mock_get.return_value = mock_response
        
        monitor = HealthMonitor()
        result = monitor.check_litellm()
        
        assert result.status == "healthy"
        assert result.name == "litellm"

    @patch("requests.get")
    def test_check_litellm_timeout(self, mock_get):
        """Test LiteLLM health check on timeout."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()
        
        monitor = HealthMonitor()
        result = monitor.check_litellm()
        
        assert result.status == "unhealthy"
        assert "timed out" in result.message.lower()

    def test_check_graph_staleness_healthy(self):
        """Test graph staleness check when recent activity exists."""
        monitor = HealthMonitor()
        monitor.graph_client = Mock()
        monitor.graph_client.read.return_value = [
            {"recent_events": 5, "last_event": datetime.utcnow()}
        ]
        
        result = monitor.check_graph_staleness()
        
        assert result.status == "healthy"

    def test_check_graph_staleness_degraded(self):
        """Test graph staleness check when no recent activity."""
        monitor = HealthMonitor()
        monitor.graph_client = Mock()
        monitor.graph_client.read.return_value = [{"recent_events": 0, "last_event": None}]
        
        result = monitor.check_graph_staleness()
        
        assert result.status == "degraded"

    def test_check_github_sync_no_state(self, tmp_path):
        """Test GitHub sync check when no sync state exists."""
        monitor = HealthMonitor()
        result = monitor.check_github_sync(str(tmp_path))
        
        assert result.status == "healthy"
        assert "first run pending" in result.message.lower()

    def test_check_github_sync_recent_sync(self, tmp_path):
        """Test GitHub sync check with recent sync."""
        import json
        sync_state = tmp_path / "sync_state.json"
        sync_state.write_text(json.dumps({
            "last_sync_timestamp": datetime.utcnow().isoformat(),
            "total_issues": 100,
        }))
        
        monitor = HealthMonitor()
        result = monitor.check_github_sync(str(tmp_path))
        
        assert result.status == "healthy"

    @patch("requests.post")
    def test_send_alert_with_slack(self, mock_post):
        """Test alert sending with Slack webhook."""
        mock_post.return_value.raise_for_status = Mock()
        
        monitor = HealthMonitor(slack_webhook_url="https://hooks.slack.com/test")
        monitor.send_alert("Test message", level="error", details={"key": "value"})
        
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "json" in call_args.kwargs
        assert "Test message" in call_args.kwargs["json"]["text"]

    def test_send_alert_without_webhook(self, caplog):
        """Test alert sending without Slack webhook logs instead."""
        monitor = HealthMonitor(slack_webhook_url=None)
        
        with caplog.at_level("INFO"):
            monitor.send_alert("Test message", level="warning")
        
        assert "Would send alert" in caplog.text


class TestHealthUtilities:
    """Test suite for health utility functions."""

    def test_format_health_report(self):
        """Test health report formatting."""
        statuses = [
            HealthStatus("db", "healthy", "OK"),
            HealthStatus("api", "degraded", "Slow response"),
            HealthStatus("cache", "unhealthy", "Down"),
        ]
        
        report = format_health_report(statuses)
        
        assert "System Health Report" in report
        assert "✅" in report
        assert "⚠️" in report
        assert "❌" in report
        assert "db" in report
        assert "api" in report
        assert "cache" in report

    def test_health_status_dataclass(self):
        """Test HealthStatus dataclass properties."""
        status = HealthStatus(
            name="test",
            status="healthy",
            message="All good",
            details={"extra": "info"},
        )
        
        assert status.name == "test"
        assert status.status == "healthy"
        assert status.message == "All good"
        assert status.details == {"extra": "info"}
        assert isinstance(status.last_check, datetime)


class TestSchedulerBootstrap:
    """Test suite for scheduler bootstrap sequence."""

    def test_bootstrap_with_no_cache(self, mock_env_vars, tmp_path):
        """Test bootstrap when no cache exists."""
        runner = SchedulerRunner()
        runner.run_github_sync = Mock(return_value=50)
        runner.run_tree_sitter_parse = Mock()
        
        # Mock the cache check and graph query
        with patch.object(Path, "exists", return_value=False):
            with patch("graph.client.query", return_value=[{"count": 1}]):
                runner.bootstrap()
        
        runner.run_github_sync.assert_called_once_with(bulk=True)

    def test_bootstrap_with_cache(self, mock_env_vars):
        """Test bootstrap skips sync when cache exists."""
        runner = SchedulerRunner()
        runner.run_github_sync = Mock()
        runner.run_tree_sitter_parse = Mock()
        
        # Mock cache exists and graph query
        with patch.object(Path, "glob", return_value=[Path("test.jsonl")]):
            with patch.object(Path, "exists", return_value=True):
                with patch("graph.client.query", return_value=[{"count": 1}]):
                    runner.bootstrap()
        
        runner.run_github_sync.assert_not_called()

    def test_bootstrap_handles_errors_gracefully(self, mock_env_vars):
        """Test bootstrap continues even if sync fails."""
        runner = SchedulerRunner()
        runner.run_github_sync = Mock(side_effect=RuntimeError("Sync failed"))
        runner.run_tree_sitter_parse = Mock()
        
        with patch.object(Path, "exists", return_value=False):
            with patch("graph.client.query", return_value=[{"count": 1}]):
                # Should not raise
                runner.bootstrap()
