"""Feedback loop for monitoring effectiveness of resolved action items and strategies.

Monitors nodes resolved in the past 30 days:
- If no new incidents in the pattern cluster since resolution: marks effective=True
- If new incidents occurred: marks effective=False, decreases confidence, creates reinvestigation item

Also finalizes effectiveness for nodes outside the 30-day window.
"""
import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from graph.client import get_client
from graph.queries import get_query

logger = logging.getLogger(__name__)


class FeedbackLoopResult:
    """Result of a feedback loop run."""
    
    def __init__(self):
        self.action_items_checked = 0
        self.strategies_checked = 0
        self.effective_count = 0
        self.ineffective_count = 0
        self.reinvestigations_created = 0
        self.errors = []
    
    def summary(self) -> str:
        """Return a human-readable summary."""
        return (
            f"Feedback loop complete:\n"
            f"  - Action items checked: {self.action_items_checked}\n"
            f"  - Strategies checked: {self.strategies_checked}\n"
            f"  - Effective: {self.effective_count}\n"
            f"  - Ineffective (new incidents): {self.ineffective_count}\n"
            f"  - Reinvestigation items created: {self.reinvestigations_created}\n"
            f"  - Errors: {len(self.errors)}"
        )


class FeedbackLoop:
    """Feedback loop for evaluating effectiveness of interventions."""
    
    def __init__(
        self,
        window_days: int = 30,
        slack_webhook_url: Optional[str] = None,
    ):
        self.window_days = window_days
        self.slack_webhook_url = slack_webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.client = get_client()
    
    def run(self) -> FeedbackLoopResult:
        """Execute the full feedback loop.
        
        1. Query resolved ActionItems in past 30 days
        2. Query implemented Strategies in past 30 days
        3. For each: check if new incidents occurred in associated patterns
        4. Update effectiveness accordingly
        5. Adjust causal edge confidence
        6. Create reinvestigation items for ineffective interventions
        7. Finalize effectiveness for items outside window
        """
        result = FeedbackLoopResult()
        cutoff_date = datetime.utcnow() - timedelta(days=self.window_days)
        
        logger.info(f"Starting feedback loop for window: {self.window_days} days")
        
        try:
            # Process action items
            action_items = self._get_action_items_to_check(cutoff_date)
            logger.info(f"Found {len(action_items)} action items to check")
            
            for item in action_items:
                try:
                    self._process_action_item(item, result)
                except Exception as e:
                    logger.error(f"Error processing action item {item.get('id')}: {e}")
                    result.errors.append(f"Action item {item.get('id')}: {e}")
            
            # Process strategies
            strategies = self._get_strategies_to_check(cutoff_date)
            logger.info(f"Found {len(strategies)} strategies to check")
            
            for strategy in strategies:
                try:
                    self._process_strategy(strategy, result)
                except Exception as e:
                    logger.error(f"Error processing strategy {strategy.get('id')}: {e}")
                    result.errors.append(f"Strategy {strategy.get('id')}: {e}")
            
            # Finalize items outside window
            self._finalize_outside_window(result)
            
            logger.info(result.summary())
            return result
            
        except Exception as e:
            logger.error(f"Feedback loop failed: {e}")
            result.errors.append(f"Loop failure: {e}")
            return result
    
    def _get_action_items_to_check(self, cutoff_date: datetime) -> List[Dict[str, Any]]:
        """Get resolved action items within the monitoring window."""
        query = get_query("get_resolved_action_items_30d")
        return self.client.read(query, {"since": cutoff_date.isoformat()})
    
    def _get_strategies_to_check(self, cutoff_date: datetime) -> List[Dict[str, Any]]:
        """Get implemented strategies within the monitoring window."""
        query = get_query("get_implemented_strategies_30d")
        return self.client.read(query, {"since": cutoff_date.isoformat()})
    
    def _count_new_incidents_in_pattern(self, pattern_cluster_id: str, since: datetime) -> int:
        """Count incidents in a pattern cluster since the given date."""
        if not pattern_cluster_id:
            return 0
        
        query = get_query("count_new_incidents_since_pattern")
        result = self.client.read(query, {
            "since": since.isoformat(),
            "pattern_cluster_id": pattern_cluster_id,
        })
        
        if result:
            return result[0].get("incident_count", 0)
        return 0
    
    def _process_action_item(self, item: Dict[str, Any], result: FeedbackLoopResult):
        """Process a single action item for effectiveness."""
        item_id = item.get("id")
        resolved_at_str = item.get("resolved_at")
        pattern_cluster_id = item.get("pattern_cluster_id")
        
        if not resolved_at_str:
            logger.warning(f"Action item {item_id} has no resolved_at date, skipping")
            return
        
        # Parse resolved_at
        try:
            resolved_at = datetime.fromisoformat(resolved_at_str.replace("Z", "+00:00").replace("+00:00", ""))
        except (ValueError, AttributeError):
            logger.warning(f"Could not parse resolved_at for {item_id}: {resolved_at_str}")
            return
        
        # Count new incidents in the pattern
        new_incidents = self._count_new_incidents_in_pattern(pattern_cluster_id, resolved_at)
        
        if new_incidents == 0:
            # Effective!
            self._mark_action_item_effective(item_id, True)
            result.effective_count += 1
            logger.info(f"Action item {item_id}: effective (no new incidents)")
        else:
            # Ineffective - new incidents occurred
            self._mark_action_item_effective(item_id, False)
            self._decrease_edge_confidence([item_id])
            self._create_reinvestigation_item(item, new_incidents)
            self._send_slack_alert(f"Action item {item_id} marked ineffective: {new_incidents} new incidents occurred")
            result.ineffective_count += 1
            result.reinvestigations_created += 1
            logger.info(f"Action item {item_id}: ineffective ({new_incidents} new incidents)")
        
        result.action_items_checked += 1
    
    def _process_strategy(self, strategy: Dict[str, Any], result: FeedbackLoopResult):
        """Process a single strategy for effectiveness."""
        strategy_id = strategy.get("id")
        implemented_at_str = strategy.get("implemented_at")
        pattern_cluster_ids = strategy.get("pattern_cluster_ids", []) or []
        
        if not implemented_at_str:
            logger.warning(f"Strategy {strategy_id} has no implemented_at date, skipping")
            return
        
        # Parse implemented_at
        try:
            implemented_at = datetime.fromisoformat(implemented_at_str.replace("Z", "+00:00").replace("+00:00", ""))
        except (ValueError, AttributeError):
            logger.warning(f"Could not parse implemented_at for {strategy_id}: {implemented_at_str}")
            return
        
        # Count new incidents across all pattern clusters
        total_new_incidents = 0
        for pattern_id in pattern_cluster_ids:
            total_new_incidents += self._count_new_incidents_in_pattern(pattern_id, implemented_at)
        
        if total_new_incidents == 0:
            # Effective!
            self._mark_strategy_effective(strategy_id, True)
            result.effective_count += 1
            logger.info(f"Strategy {strategy_id}: effective (no new incidents)")
        else:
            # Ineffective - new incidents occurred
            self._mark_strategy_effective(strategy_id, False)
            self._decrease_edge_confidence([strategy_id])
            result.ineffective_count += 1
            logger.info(f"Strategy {strategy_id}: ineffective ({total_new_incidents} new incidents)")
        
        result.strategies_checked += 1
    
    def _mark_action_item_effective(self, item_id: str, effective: bool):
        """Mark an action item as effective or ineffective."""
        query = get_query("update_action_item_effectiveness")
        self.client.write(query, {"id": item_id, "effective": effective})
    
    def _mark_strategy_effective(self, strategy_id: str, effective: bool):
        """Mark a strategy as effective or ineffective."""
        query = get_query("update_strategy_effectiveness")
        self.client.write(query, {"id": strategy_id, "effective": effective})
    
    def _decrease_edge_confidence(self, node_ids: List[str]):
        """Decrease confidence of causal edges from ineffective nodes."""
        query = get_query("adjust_causal_edge_confidence")
        # Query expects effective=true to increase, false to decrease
        self.client.write(query, {"node_ids": node_ids, "effective": False})
    
    def _increase_edge_confidence(self, node_ids: List[str]):
        """Increase confidence of causal edges from effective nodes."""
        query = get_query("adjust_causal_edge_confidence")
        self.client.write(query, {"node_ids": node_ids, "effective": True})
    
    def _create_reinvestigation_item(self, original_item: Dict[str, Any], incident_count: int):
        """Create a new action item for reinvestigation when an item is ineffective."""
        query = get_query("create_reinvestigation_action_item")
        
        new_id = f"ai-reinvest-{uuid.uuid4().hex[:8]}"
        original_id = original_item.get("id")
        pattern_id = original_item.get("pattern_cluster_id")
        
        self.client.write(query, {
            "id": new_id,
            "title": f"Reinvestigate: Original action item {original_id}",
            "description": (
                f"Original action item was marked ineffective after {incident_count} "
                f"new incidents occurred in the pattern cluster. This suggests the "
                f"root cause was not fully addressed or a related issue emerged. "
                f"Requires deeper investigation into the pattern."
            ),
            "original_id": original_id,
            "trigger_reason": f"{incident_count} new incidents after resolution",
            "pattern_cluster_id": pattern_id,
        })
        
        logger.info(f"Created reinvestigation item: {new_id}")
    
    def _finalize_outside_window(self, result: FeedbackLoopResult):
        """Finalize effectiveness for items outside the 30-day monitoring window."""
        cutoff_date = datetime.utcnow() - timedelta(days=self.window_days)
        
        # Finalize action items
        query_ai = get_query("finalize_effectiveness_outside_window")
        ai_result = self.client.write(query_ai, {"cutoff_date": cutoff_date.isoformat()})
        
        # Log how many were finalized
        if ai_result:
            finalized_ai = ai_result[0].get("finalized", 0) if isinstance(ai_result, list) else 0
            logger.info(f"Finalized {finalized_ai} action items outside monitoring window")
        
        # Note: Strategies are in the same query (compound query in queries.py)
        # This is a simplification; in production you'd want separate queries
    
    def _send_slack_alert(self, message: str):
        """Send a Slack alert for ineffective interventions."""
        if not self.slack_webhook_url:
            logger.debug(f"No Slack webhook configured, would have sent: {message}")
            return
        
        import requests
        
        try:
            payload = {
                "text": f"🚨 Stability Intelligence Alert\n\n{message}",
                "username": "StabilityBot",
            }
            response = requests.post(
                self.slack_webhook_url,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info("Slack alert sent successfully")
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")


def run_feedback_loop() -> FeedbackLoopResult:
    """Convenience function to run the feedback loop."""
    loop = FeedbackLoop()
    return loop.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = run_feedback_loop()
    print(result.summary())
    exit(0 if len(result.errors) == 0 else 1)
