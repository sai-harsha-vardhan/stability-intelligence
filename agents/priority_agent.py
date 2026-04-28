"""Priority estimation agent - scores ActionItems based on impact and historical data."""
import json
import logging
import uuid
from typing import Dict, Any, List, Optional

from agents.base import BaseAgent
from graph.models import Complexity

logger = logging.getLogger(__name__)


class PriorityAgent(BaseAgent):
    """Estimates priority, complexity, and impact for ActionItem nodes."""
    
    def __init__(self):
        super().__init__(name="priority_agent")
    
    def run(self) -> Dict[str, Any]:
        """Main entry point for priority estimation.
        
        Steps:
        1. Find ActionItems without priority scores
        2. Estimate priority for each action item
        3. Update ActionItems with calculated scores
        4. Return statistics
        
        Returns:
            Dict with statistics about scored action items
        """
        logger.info("Priority agent starting...")
        
        # Find ActionItems needing scoring
        action_items = self._find_unscored_action_items()
        logger.info(f"Found {len(action_items)} action items to score")
        
        if not action_items:
            logger.info("No action items to score")
            return {"action_items_scored": 0}
        
        scored_count = 0
        
        for item in action_items:
            try:
                self.estimate_priority(item)
                scored_count += 1
            except Exception as e:
                logger.error(f"Failed to score action item {item.get('id')}: {e}")
        
        # Log activity
        self.log_activity(
            message=f"Priority agent complete: scored {scored_count} action items",
            data={
                "action_items_found": len(action_items),
                "action_items_scored": scored_count,
            },
        )
        
        logger.info(f"Priority agent complete: scored {scored_count} action items")
        
        return {"action_items_scored": scored_count}
    
    def _find_unscored_action_items(self) -> List[Dict[str, Any]]:
        """Find ActionItems that don't have priority scores yet."""
        cypher = """
        MATCH (ai:ActionItem)
        WHERE ai.priority_score IS NULL OR ai.priority_score = 0
        RETURN ai.id AS id,
               ai.title AS title,
               ai.description AS description,
               ai.status AS status
        ORDER BY ai.created_at DESC
        """
        return self.query_graph(cypher)
    
    def estimate_priority(self, action_item: Dict[str, Any]):
        """Calculate all scores for one action item.
        
        Steps:
        1. Find related PatternCluster to calculate forward score
        2. Count historical incidents to calculate backward score
        3. Use LiteLLM to estimate complexity and risk
        4. Calculate final priority score
        5. Update ActionItem with all scores
        
        Args:
            action_item: Dict containing action item data
        """
        action_item_id = action_item.get("id")
        logger.info(f"Scoring action item: {action_item_id}")
        
        # Calculate forward score (future impact)
        forward_score = self._calculate_forward_score(action_item)
        
        # Calculate backward score (historical impact)
        backward_score = self._calculate_backward_score(action_item)
        
        # Use LiteLLM to estimate complexity and risk
        llm_estimates = self._estimate_complexity_with_llm(
            action_item, forward_score, backward_score
        )
        
        # Calculate final priority score
        priority_score = self._calculate_priority_score(
            forward_score=forward_score,
            backward_score=backward_score,
            complexity=llm_estimates.get("implementation_complexity", "medium"),
            expected_reduction=llm_estimates.get("expected_reduction_percent", 30.0),
        )
        
        # Update ActionItem in graph
        self._update_action_item_scores(
            action_item_id=action_item_id,
            forward_score=forward_score,
            backward_score=backward_score,
            priority_score=priority_score,
            complexity=llm_estimates.get("implementation_complexity", "medium"),
            estimated_effort_hours=llm_estimates.get("estimated_effort_hours", 8.0),
            risk_of_breaking_changes=llm_estimates.get("risk_of_breaking_changes", 5),
            expected_reduction_percent=llm_estimates.get("expected_reduction_percent", 30.0),
        )
        
        logger.info(
            f"Scored {action_item_id}: forward={forward_score}, backward={backward_score}, "
            f"priority={priority_score:.2f}, complexity={llm_estimates.get('implementation_complexity')}"
        )
    
    def find_related_pattern(self, action_item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find PatternCluster that this action addresses.
        
        Searches for patterns by:
        1. Direct relationship (ActionItem)-[:ADDRESSES_PATTERN]->(PatternCluster)
        2. Shared RootCause nodes
        3. Matching affected components
        
        Args:
            action_item: Dict containing action item data
            
        Returns:
            PatternCluster dict or None if not found
        """
        action_item_id = action_item.get("id")
        
        # Try to find via direct relationship
        cypher = """
        MATCH (ai:ActionItem {id: $action_item_id})-[:ADDRESSES_PATTERN]->(pc:PatternCluster)
        RETURN pc.id AS id,
               pc.name AS name,
               pc.frequency AS frequency,
               pc.affected_components AS affected_components
        LIMIT 1
        """
        result = self.query_graph(cypher, {"action_item_id": action_item_id})
        
        if result:
            return result[0]
        
        # Try to find via shared RootCause
        cypher = """
        MATCH (ai:ActionItem {id: $action_item_id})<-[:SUGGESTS_ACTION]-(rc:RootCause)
        MATCH (rc)-[:CLUSTERED_INTO]->(pc:PatternCluster)
        RETURN pc.id AS id,
               pc.name AS name,
               pc.frequency AS frequency,
               pc.affected_components AS affected_components
        ORDER BY pc.frequency DESC
        LIMIT 1
        """
        result = self.query_graph(cypher, {"action_item_id": action_item_id})
        
        if result:
            return result[0]
        
        return None
    
    def _calculate_forward_score(self, action_item: Dict[str, Any]) -> int:
        """Calculate forward score: how many future incidents will this prevent?
        
        Based on the frequency of the related PatternCluster.
        
        Args:
            action_item: Dict containing action item data
            
        Returns:
            Forward score (default 1 if no pattern found)
        """
        pattern = self.find_related_pattern(action_item)
        
        if pattern:
            frequency = pattern.get("frequency", 1)
            logger.debug(f"Found related pattern with frequency {frequency}")
            return frequency
        
        logger.debug("No related pattern found, using default forward_score=1")
        return 1
    
    def _calculate_backward_score(self, action_item: Dict[str, Any]) -> int:
        """Calculate backward score: how many past incidents would this have prevented?
        
        Counts historical incidents that share affected components with this action item's
        related pattern or root cause.
        
        Args:
            action_item: Dict containing action item data
            
        Returns:
            Count of matching historical incidents
        """
        action_item_id = action_item.get("id")
        
        # Find incidents that share components with this action item's pattern
        cypher = """
        MATCH (ai:ActionItem {id: $action_item_id})<-[:SUGGESTS_ACTION]-(rc:RootCause)
        MATCH (rc)<-[:HAS_ROOT_CAUSE]-(inc:Incident)
        WITH ai, collect(DISTINCT inc.id) AS related_incident_ids
        MATCH (inc2:Incident)
        WHERE inc2.id IN related_incident_ids
        RETURN count(inc2) AS backward_count
        """
        result = self.query_graph(cypher, {"action_item_id": action_item_id})
        
        if result and result[0].get("backward_count"):
            count = result[0]["backward_count"]
            logger.debug(f"Found {count} historical incidents")
            return count
        
        logger.debug("No historical incidents found, using backward_score=0")
        return 0
    
    def _estimate_complexity_with_llm(
        self,
        action_item: Dict[str, Any],
        forward_score: int,
        backward_score: int,
    ) -> Dict[str, Any]:
        """Use LiteLLM to estimate complexity, effort, risk, and impact.
        
        Args:
            action_item: Dict containing action item data
            forward_score: Calculated forward score
            backward_score: Calculated backward score
            
        Returns:
            Dict with complexity estimates from LLM
        """
        title = action_item.get("title", "")
        description = action_item.get("description", "")
        
        # Get components context
        pattern = self.find_related_pattern(action_item)
        components = pattern.get("affected_components", []) if pattern else []
        
        prompt = f"""Estimate the implementation complexity and impact for this action item:

Action Item:
Title: {title}
Description: {description}

Context:
- Related pattern occurs {forward_score} times
- Would have prevented {backward_score} past incidents
- Affected components: {', '.join(components) if components else 'Unknown'}

Estimate in JSON format:
{{
  "implementation_complexity": "low|medium|high",
  "estimated_effort_hours": <number>,
  "risk_of_breaking_changes": <1-10>,
  "expected_reduction_percent": <0-100>,
  "reasoning": "brief explanation"
}}

Respond ONLY with valid JSON, no other text."""
        
        try:
            response = self.call_claude(
                prompt=prompt,
                system="You are an expert software engineer estimating implementation complexity.",
                trace_name="priority-complexity-estimation",
                max_tokens=500,
            )
            
            # Parse JSON response
            # Try to extract JSON from response (in case there's extra text)
            response = response.strip()
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                response = response.split("```")[1].split("```")[0].strip()
            
            estimates = json.loads(response)
            
            # Validate and normalize
            complexity = estimates.get("implementation_complexity", "medium").lower()
            if complexity not in ["low", "medium", "high"]:
                complexity = "medium"
            
            return {
                "implementation_complexity": complexity,
                "estimated_effort_hours": float(estimates.get("estimated_effort_hours", 8.0)),
                "risk_of_breaking_changes": int(estimates.get("risk_of_breaking_changes", 5)),
                "expected_reduction_percent": float(estimates.get("expected_reduction_percent", 30.0)),
            }
            
        except Exception as e:
            logger.error(f"LLM complexity estimation failed: {e}")
            # Return conservative defaults
            return {
                "implementation_complexity": "medium",
                "estimated_effort_hours": 8.0,
                "risk_of_breaking_changes": 5,
                "expected_reduction_percent": 30.0,
            }
    
    def _calculate_priority_score(
        self,
        forward_score: int,
        backward_score: int,
        complexity: str,
        expected_reduction: float,
    ) -> float:
        """Calculate final priority score using the formula.
        
        Formula:
        priority_score = (forward_score + backward_score) * (expected_reduction / 100) / complexity_weight
        
        Higher score = higher priority
        
        Args:
            forward_score: Future incidents prevented
            backward_score: Past incidents that would have been prevented
            complexity: Implementation complexity (low/medium/high)
            expected_reduction: Expected incident reduction percentage (0-100)
            
        Returns:
            Calculated priority score
        """
        complexity_weight = {
            "low": 1,
            "medium": 2,
            "high": 3,
        }
        
        weight = complexity_weight.get(complexity.lower(), 2)
        
        # Ensure we don't divide by zero
        if weight == 0:
            weight = 1
        
        priority_score = (
            (forward_score + backward_score) * 
            (expected_reduction / 100.0) /
            weight
        )
        
        return round(priority_score, 2)
    
    def _update_action_item_scores(
        self,
        action_item_id: str,
        forward_score: int,
        backward_score: int,
        priority_score: float,
        complexity: str,
        estimated_effort_hours: float,
        risk_of_breaking_changes: int,
        expected_reduction_percent: float,
    ):
        """Update ActionItem node with calculated scores.
        
        Args:
            action_item_id: ActionItem node ID
            forward_score: Future impact score
            backward_score: Historical impact score
            priority_score: Final priority score
            complexity: Implementation complexity
            estimated_effort_hours: Estimated hours to implement
            risk_of_breaking_changes: Risk score 1-10
            expected_reduction_percent: Expected incident reduction
        """
        cypher = """
        MATCH (ai:ActionItem {id: $action_item_id})
        SET ai.forward_score = $forward_score,
            ai.backward_score = $backward_score,
            ai.priority_score = $priority_score,
            ai.implementation_complexity = $complexity,
            ai.estimated_effort_hours = $estimated_effort_hours,
            ai.risk_of_breaking_changes = $risk_of_breaking_changes,
            ai.expected_reduction_percent = $expected_reduction_percent,
            ai.updated_at = datetime()
        RETURN ai.id
        """
        
        self.write_graph(cypher, {
            "action_item_id": action_item_id,
            "forward_score": forward_score,
            "backward_score": backward_score,
            "priority_score": priority_score,
            "complexity": complexity,
            "estimated_effort_hours": estimated_effort_hours,
            "risk_of_breaking_changes": risk_of_breaking_changes,
            "expected_reduction_percent": expected_reduction_percent,
        })
        
        logger.debug(f"Updated ActionItem {action_item_id} with scores")
