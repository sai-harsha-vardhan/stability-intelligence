"""APScheduler runner for Stability Intelligence System.

Manages 4 scheduled jobs:
1. github_sync - every N hours (configured via GITHUB_SYNC_INTERVAL_HOURS)
2. strategy_agent - weekly on Monday 09:00 (configured via STRATEGY_AGENT_CRON)
3. feedback_loop - daily
4. health_check - every 5 minutes

On first run, performs bootstrap:
- Bulk sync if no cache
- Tree-sitter parse
- Run all agents
"""
import os
import sys
import logging
import signal
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from graph.client import get_client, close_client
from scheduler.health import HealthMonitor, format_health_report

logger = logging.getLogger(__name__)


class SchedulerRunner:
    """Main scheduler coordinator."""
    
    def __init__(
        self,
        github_interval_hours: int = None,
        strategy_cron: str = None,
    ):
        self.github_interval_hours = github_interval_hours or int(
            os.getenv("GITHUB_SYNC_INTERVAL_HOURS", "6")
        )
        self.strategy_cron = strategy_cron or os.getenv(
            "STRATEGY_AGENT_CRON", "0 9 * * 1"  # Monday 09:00
        )
        
        self.scheduler = BackgroundScheduler()
        self.health_monitor = HealthMonitor()
        self._shutdown_requested = False
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self._shutdown_requested = True
        self.scheduler.shutdown(wait=True)
    
    def _job_listener(self, event: JobExecutionEvent):
        """Listen for job events and log results."""
        if event.exception:
            logger.error(f"Job {event.job_id} failed: {event.exception}")
            self.health_monitor.send_alert(
                f"Scheduled job '{event.job_id}' failed: {event.exception}",
                level="error",
                details={"job_id": event.job_id, "exception": str(event.exception)},
            )
        else:
            logger.info(f"Job {event.job_id} completed successfully")
    
    def setup_jobs(self):
        """Configure all scheduled jobs."""
        # 1. GitHub sync - interval based
        self.scheduler.add_job(
            self.run_github_sync,
            trigger=IntervalTrigger(hours=self.github_interval_hours),
            id="github_sync",
            name="GitHub Issue Sync",
            replace_existing=True,
        )
        logger.info(f"Scheduled github_sync every {self.github_interval_hours} hours")
        
        # 2. Strategy agent - cron based
        cron_parts = self.strategy_cron.split()
        self.scheduler.add_job(
            self.run_strategy_agent,
            trigger=CronTrigger(
                minute=cron_parts[0],
                hour=cron_parts[1],
                day=cron_parts[2],
                month=cron_parts[3],
                day_of_week=cron_parts[4],
            ),
            id="strategy_agent",
            name="Strategy Agent",
            replace_existing=True,
        )
        logger.info(f"Scheduled strategy_agent with cron: {self.strategy_cron}")
        
        # 3. Feedback loop - daily
        self.scheduler.add_job(
            self.run_feedback_loop,
            trigger=IntervalTrigger(hours=24),
            id="feedback_loop",
            name="Feedback Loop",
            replace_existing=True,
        )
        logger.info("Scheduled feedback_loop daily")
        
        # 4. Health check - every 5 minutes
        self.scheduler.add_job(
            self.run_health_check,
            trigger=IntervalTrigger(minutes=5),
            id="health_check",
            name="Health Monitor",
            replace_existing=True,
        )
        logger.info("Scheduled health_check every 5 minutes")
        
        # Add event listener
        self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    
    def bootstrap(self):
        """Bootstrap the system on first run.
        
        This runs before the scheduler starts and ensures the system is ready.
        """
        logger.info("Starting bootstrap sequence...")
        
        # Check if we have cached data
        cache_dir = Path("/app/github-cache")
        has_cache = any(cache_dir.glob("*.jsonl")) if cache_dir.exists() else False
        
        if not has_cache:
            logger.info("No cached data found, running bulk sync...")
            try:
                self.run_github_sync(bulk=True)
            except Exception as e:
                logger.error(f"Bulk sync failed: {e}")
                # Continue anyway - individual jobs will retry
        
        # Check if we have parsed code
        try:
            from graph.client import query
            result = query("MATCH (m:CodeModule) RETURN count(m) AS count LIMIT 1")
            has_code = result and result[0].get("count", 0) > 0 if result else False
            
            if not has_code:
                logger.info("No code modules in graph, running Tree-sitter parser...")
                self.run_tree_sitter_parse()
        except Exception as e:
            logger.error(f"Code check failed: {e}")
        
        logger.info("Bootstrap complete")
    
    def run_github_sync(self, bulk: bool = False):
        """Run GitHub sync."""
        logger.info(f"Running GitHub sync (bulk={bulk})...")
        
        try:
            from scripts.github_sync import bulk_sync, incremental_sync
            
            if bulk:
                count = bulk_sync()
                logger.info(f"Bulk sync complete: {count} issues synced")
            else:
                count = incremental_sync()
                logger.info(f"Incremental sync complete: {count} issues synced")
            
            return count
        except Exception as e:
            logger.error(f"GitHub sync failed: {e}")
            raise
    
    def run_tree_sitter_parse(self):
        """Run Tree-sitter parser to extract code knowledge."""
        logger.info("Running Tree-sitter parser...")
        
        try:
            # Import and run the parser
            from scripts.tree_sitter_parser import parse_and_write
            stats = parse_and_write()
            logger.info(f"Tree-sitter parse complete: {stats}")
            return stats
        except Exception as e:
            logger.error(f"Tree-sitter parse failed: {e}")
            raise
    
    def run_strategy_agent(self):
        """Run the strategy agent."""
        logger.info("Running strategy agent...")
        
        try:
            from agents.strategy_agent import StrategyAgent
            agent = StrategyAgent()
            agent.run()
            logger.info("Strategy agent complete")
        except ImportError:
            logger.warning("Strategy agent not yet implemented, skipping")
        except Exception as e:
            logger.error(f"Strategy agent failed: {e}")
            raise
    
    def run_feedback_loop(self):
        """Run the feedback loop."""
        logger.info("Running feedback loop...")
        
        try:
            from feedback.loop import run_feedback_loop
            result = run_feedback_loop()
            logger.info(f"Feedback loop complete: {result.effective_count} effective, {result.ineffective_count} ineffective")
            return result
        except Exception as e:
            logger.error(f"Feedback loop failed: {e}")
            raise
    
    def run_health_check(self):
        """Run health checks."""
        statuses = self.health_monitor.check_all()
        
        unhealthy = [s for s in statuses if s.status == "unhealthy"]
        degraded = [s for s in statuses if s.status == "degraded"]
        
        if unhealthy:
            logger.error(format_health_report(statuses))
        elif degraded:
            logger.warning(format_health_report(statuses))
        else:
            logger.debug("All health checks passed")
        
        return statuses
    
    def start(self):
        """Start the scheduler."""
        logger.info("=" * 60)
        logger.info("Stability Intelligence System Scheduler")
        logger.info("=" * 60)
        
        # Bootstrap first
        self.bootstrap()
        
        # Setup and start scheduler
        self.setup_jobs()
        self.scheduler.start()
        
        logger.info("Scheduler started. Press Ctrl+C to exit.")
        logger.info(f"Jobs registered: {[job.id for job in self.scheduler.get_jobs()]}")
        
        # Keep running until shutdown
        try:
            while not self._shutdown_requested:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            self.stop()
    
    def stop(self):
        """Stop the scheduler gracefully."""
        logger.info("Stopping scheduler...")
        
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
        
        close_client()
        logger.info("Scheduler stopped")


def main():
    """Main entry point."""
    # Setup logging
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    
    # Also log to file
    log_dir = Path("/app/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "scheduler.log")
    file_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(file_handler)
    
    runner = SchedulerRunner()
    runner.start()


if __name__ == "__main__":
    main()
