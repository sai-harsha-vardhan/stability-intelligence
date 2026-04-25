"""Strategy agent - generates systemic strategies from patterns."""
import logging
from typing import List, Dict, Any

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class StrategyAgent(BaseAgent):
    """Generates strategies from worsening pattern clusters."""
    
    def __init__(self):
        super().__init__(name="strategy_agent")
    
    def run(self):
        """Run the strategy agent.
        
        Steps:
        1. Query pattern clusters with frequency >= 3 and worsening trend
        2. Generate appropriate strategies based on pattern type
        3. Calculate unified priority ranking
        4. Write strategies to graph
        5. Log activity
        """
        logger.info("Strategy agent starting...")
        
        # Get worsening/high-frequency pattern clusters
        clusters = self._get_target_clusters()
        logger.info(f"Found {len(clusters)} clusters requiring strategies")
        
        strategies_created = 0
        
        for cluster in clusters:
            try:
                strategy = self._generate_strategy(cluster)
                if strategy:
                    self._save_strategy(strategy)
                    strategies_created += 1
            except Exception as e:
                logger.error(f"Failed to generate strategy for cluster {cluster.get('id')}: {e}")
        
        self.log_activity(
            message=f"Strategy agent complete: {strategies_created} strategies created",
            data={"clusters_analyzed": len(clusters), "strategies_created": strategies_created},
        )
        
        logger.info(f"Strategy agent complete: {strategies_created} strategies created")
    
    def _get_target_clusters(self) -> List[Dict[str, Any]]:
        """Get pattern clusters that need strategies."""
        # Get clusters with frequency >= 3 and worsening/stable trend
        cypher = """
        MATCH (pc:PatternCluster)
        WHERE pc.frequency >= 3
          AND pc.trend IN ['worsening', 'stable']
        OPTIONAL MATCH (pc)<-[:ADDRESSES_PATTERN]-(s:Strategy)
        WITH pc, count(s) AS existing_strategies
        WHERE existing_strategies = 0
        RETURN pc.id AS id,
               pc.name AS name,
               pc.description AS description,
               pc.frequency AS frequency,
               pc.trend AS trend
        """
        return self.query_graph(cypher)
    
    def _generate_strategy(self, cluster: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a strategy for a pattern cluster."""
        cluster_name = cluster.get("name", "").lower()
        description = cluster.get("description", "").lower()
        
        # Simple pattern matching for strategy type
        strategy_type = self._determine_strategy_type(cluster_name, description)
        
        strategy = {
            "title": f"{strategy_type.replace('_', ' ').title()} for {cluster.get('name')}",
            "description": f"Auto-generated strategy to address pattern: {cluster.get('description', '')}",
            "strategy_type": strategy_type,
            "pattern_cluster_id": cluster.get("id"),
            "estimated_reduction_percent": 30.0,  # Conservative estimate
            "status": "proposed",
            "forward_score": cluster.get("frequency", 1),
            "backward_score": cluster.get("frequency", 1),
            "blocking_multiplier": 1.5,
            "priority_score": cluster.get("frequency", 1) * 1.5 / 2,  # Normalize by complexity
        }
        
        return strategy
    
    def _determine_strategy_type(self, name: str, description: str) -> str:
        """Determine the appropriate strategy type based on pattern characteristics."""
        text = f"{name} {description}"
        
        if any(kw in text for kw in ["backward compat", "contract", "api change"]):
            return "contract_test_suite"
        elif any(kw in text for kw in ["regression", "scheduler", "idempotent"]):
            return "automated_regression_suite"
        elif any(kw in text for kw in ["config", "environment", "drift", "promotion"]):
            return "environment_promotion_check"
        elif any(kw in text for kw in ["rollout", "webhook", "psm", "staged"]):
            return "staggered_rollout_gate"
        elif any(kw in text for kw in ["race condition", "load", "chaos", "concurrency"]):
            return "chaos_experiment"
        else:
            return "automated_regression_suite"  # Default
    
    def _save_strategy(self, strategy: Dict[str, Any]):
        """Save a strategy to the graph."""
        import uuid
        
        strategy_id = f"strat-{uuid.uuid4().hex[:12]}"
        
        cypher = """
        CREATE (s:Strategy {
            id: $id,
            title: $title,
            description: $description,
            strategy_type: $strategy_type,
            pattern_cluster_ids: [$pattern_cluster_id],
            status: $status,
            estimated_reduction_percent: $estimated_reduction,
            forward_score: $forward_score,
            backward_score: $backward_score,
            blocking_multiplier: $blocking_multiplier,
            priority_score: $priority_score,
            created_at: datetime(),
            updated_at: datetime()
        })
        WITH s
        MATCH (pc:PatternCluster {id: $pattern_cluster_id})
        CREATE (s)-[:ADDRESSES_PATTERN {confidence: 0.7}]->(pc)
        RETURN s.id
        """
        
        self.write_graph(cypher, {
            "id": strategy_id,
            "title": strategy["title"],
            "description": strategy["description"],
            "strategy_type": strategy["strategy_type"],
            "pattern_cluster_id": strategy["pattern_cluster_id"],
            "status": strategy["status"],
            "estimated_reduction": strategy["estimated_reduction_percent"],
            "forward_score": strategy["forward_score"],
            "backward_score": strategy["backward_score"],
            "blocking_multiplier": strategy["blocking_multiplier"],
            "priority_score": strategy["priority_score"],
        })
        
        logger.info(f"Created strategy: {strategy_id} - {strategy['title']}")
