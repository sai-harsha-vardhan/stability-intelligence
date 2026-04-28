"""Strategy agent - generates systemic strategies from patterns."""
import json
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
        """Generate a strategy for a pattern cluster using LiteLLM for deep solution ideation.
        
        This method:
        1. Gathers historical context (past incidents and attempted solutions)
        2. Uses LiteLLM to generate context-aware, systemic solutions
        3. Calculates priority based on pattern frequency
        4. Returns enriched strategy with implementation details
        """
        try:
            # Get historical context
            incidents = self._get_incidents_for_cluster(cluster.get('id'))
            past_actions = self._get_past_actions_for_pattern(cluster)
            
            # Build comprehensive prompt for LiteLLM
            prompt = self._build_strategy_prompt(cluster, incidents, past_actions)
            
            # Call Claude for deep solution ideation
            logger.info(f"Generating strategy for cluster {cluster.get('id')} using LiteLLM")
            response = self.call_claude(
                prompt=prompt,
                trace_name=f"strategy-generation-{cluster.get('id')}",
                max_tokens=2000
            )
            
            # Parse JSON response
            strategy_data = self._parse_strategy_response(response)
            
            # Calculate priority score from pattern frequency
            priority_score = cluster.get('frequency', 1) * 1.5
            
            # Build final strategy object
            strategy = {
                "title": strategy_data.get("title", f"Strategy for {cluster.get('name')}"),
                "description": strategy_data.get("description", ""),
                "strategy_type": strategy_data.get("strategy_type", "automated_regression_suite"),
                "pattern_cluster_id": cluster.get("id"),
                "estimated_reduction_percent": strategy_data.get("estimated_reduction_percent", 30.0),
                "implementation_steps": strategy_data.get("implementation_steps", []),
                "risks": strategy_data.get("risks", []),
                "success_metrics": strategy_data.get("success_metrics", []),
                "status": "proposed",
                "forward_score": cluster.get("frequency", 1),
                "backward_score": cluster.get("frequency", 1),
                "blocking_multiplier": 1.5,
                "priority_score": priority_score,
            }
            
            logger.info(f"Generated strategy: {strategy.get('title')}")
            return strategy
            
        except Exception as e:
            logger.error(f"Failed to generate LiteLLM-powered strategy for cluster {cluster.get('id')}: {e}")
            logger.info(f"Falling back to simple pattern matching for cluster {cluster.get('id')}")
            return self._generate_fallback_strategy(cluster)
    
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
    
    def _build_strategy_prompt(
        self, 
        cluster: Dict[str, Any], 
        incidents: List[Dict[str, Any]], 
        past_actions: List[Dict[str, Any]]
    ) -> str:
        """Build a comprehensive prompt for LiteLLM strategy generation."""
        incidents_text = self._format_incidents(incidents[:5])
        actions_text = self._format_actions(past_actions)
        
        prompt = f"""You are generating a systemic solution strategy for a recurring pattern in the Hyperswitch platform.

Pattern Analysis:
Name: {cluster.get('name', 'Unknown Pattern')}
Description: {cluster.get('description', 'No description available')}
Frequency: {cluster.get('frequency', 0)} occurrences
Trend: {cluster.get('trend', 'unknown')}

Past Incidents (sample):
{incidents_text}

Past Solutions Attempted:
{actions_text}

Generate the BEST systemic solution that:
1. Addresses the ROOT CAUSE (not symptoms)
2. Prevents ALL future occurrences of this pattern
3. Is practical to implement in Hyperswitch (a payments switch platform)
4. Considers what didn't work before and learns from past attempts
5. Is proactive and preventive, not reactive

Strategy Types Available:
- contract_test_suite: For API contract/backward compatibility issues
- automated_regression_suite: For regression bugs, scheduler issues, idempotency problems
- environment_promotion_check: For config drift, environment differences
- staggered_rollout_gate: For deployment-related issues, webhook changes
- chaos_experiment: For race conditions, load issues, concurrency problems

Respond ONLY with a valid JSON object (no markdown, no extra text) in this EXACT format:
{{
  "title": "Clear, actionable strategy title (max 80 chars)",
  "description": "Detailed implementation approach explaining HOW this solves the root cause (2-3 paragraphs)",
  "strategy_type": "one of the 5 types listed above",
  "estimated_reduction_percent": <number between 0-100 representing expected incident reduction>,
  "implementation_steps": [
    "Step 1: Specific actionable step",
    "Step 2: Another specific step",
    "Step 3: ...",
    "Step 4-6: More steps as needed"
  ],
  "risks": [
    "Risk 1: Potential implementation risk",
    "Risk 2: Another risk to consider"
  ],
  "success_metrics": [
    "Metric 1: How to measure success",
    "Metric 2: Another success indicator"
  ]
}}"""
        
        return prompt
    
    def _parse_strategy_response(self, response: str) -> Dict[str, Any]:
        """Parse and validate the JSON response from LiteLLM.
        
        Handles:
        - Markdown code blocks wrapping JSON
        - Extra whitespace
        - Missing or invalid fields
        """
        try:
            # Remove markdown code blocks if present
            cleaned = response.strip()
            if cleaned.startswith("```"):
                # Find the JSON content between code fences
                lines = cleaned.split("\n")
                json_lines = []
                in_code_block = False
                for line in lines:
                    if line.strip().startswith("```"):
                        in_code_block = not in_code_block
                        continue
                    if in_code_block or not line.strip().startswith("```"):
                        json_lines.append(line)
                cleaned = "\n".join(json_lines).strip()
            
            # Parse JSON
            strategy_data = json.loads(cleaned)
            
            # Validate required fields
            required_fields = ["title", "description", "strategy_type"]
            for field in required_fields:
                if field not in strategy_data:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate strategy_type is valid
            valid_types = [
                "contract_test_suite",
                "automated_regression_suite",
                "environment_promotion_check",
                "staggered_rollout_gate",
                "chaos_experiment"
            ]
            if strategy_data["strategy_type"] not in valid_types:
                logger.warning(f"Invalid strategy_type: {strategy_data['strategy_type']}, defaulting to automated_regression_suite")
                strategy_data["strategy_type"] = "automated_regression_suite"
            
            # Ensure lists exist
            strategy_data.setdefault("implementation_steps", [])
            strategy_data.setdefault("risks", [])
            strategy_data.setdefault("success_metrics", [])
            
            # Ensure reduction percent is valid
            reduction = strategy_data.get("estimated_reduction_percent", 30.0)
            if not isinstance(reduction, (int, float)) or reduction < 0 or reduction > 100:
                logger.warning(f"Invalid estimated_reduction_percent: {reduction}, defaulting to 30.0")
                strategy_data["estimated_reduction_percent"] = 30.0
            
            return strategy_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {response}")
            raise ValueError(f"Invalid JSON response from LiteLLM: {e}")
        except Exception as e:
            logger.error(f"Failed to validate strategy response: {e}")
            raise
    
    def _get_incidents_for_cluster(self, cluster_id: str) -> List[Dict[str, Any]]:
        """Get all incidents that exhibit this pattern cluster.
        
        Returns up to 10 most recent incidents for context.
        """
        if not cluster_id:
            return []
        
        cypher = """
        MATCH (i:Incident)-[:EXHIBITS]->(pc:PatternCluster {id: $cluster_id})
        RETURN i.title AS title, 
               i.body AS body, 
               i.created_at AS created_at,
               i.severity AS severity
        ORDER BY i.created_at DESC
        LIMIT 10
        """
        try:
            results = self.query_graph(cypher, {"cluster_id": cluster_id})
            logger.debug(f"Found {len(results)} incidents for cluster {cluster_id}")
            return results
        except Exception as e:
            logger.error(f"Failed to fetch incidents for cluster {cluster_id}: {e}")
            return []
    
    def _get_past_actions_for_pattern(self, cluster: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find ActionItems related to incidents in this pattern cluster.
        
        This helps understand what solutions were attempted before and their outcomes.
        """
        cluster_id = cluster.get('id')
        if not cluster_id:
            return []
        
        cypher = """
        MATCH (i:Incident)-[:EXHIBITS]->(pc:PatternCluster {id: $cluster_id})
        MATCH (ai:ActionItem)-[:ADDRESSES]->(i)
        RETURN ai.title AS title, 
               ai.body AS body, 
               ai.status AS status,
               ai.created_at AS created_at
        ORDER BY ai.created_at DESC
        LIMIT 10
        """
        try:
            results = self.query_graph(cypher, {"cluster_id": cluster_id})
            logger.debug(f"Found {len(results)} past actions for cluster {cluster_id}")
            return results
        except Exception as e:
            logger.error(f"Failed to fetch past actions for cluster {cluster_id}: {e}")
            return []
    
    def _format_incidents(self, incidents: List[Dict[str, Any]]) -> str:
        """Format incidents for inclusion in LLM prompt."""
        if not incidents:
            return "No historical incidents available"
        
        formatted = []
        for inc in incidents:
            title = inc.get('title', 'Untitled incident')
            created = inc.get('created_at', 'Unknown date')
            severity = inc.get('severity', 'unknown')
            body = inc.get('body', '')
            
            # Truncate body if too long
            if body and len(body) > 200:
                body = body[:200] + "..."
            
            formatted.append(
                f"- [{severity.upper()}] {title}\n"
                f"  Date: {created}\n"
                f"  Details: {body if body else 'No details'}"
            )
        
        return "\n\n".join(formatted)
    
    def _format_actions(self, actions: List[Dict[str, Any]]) -> str:
        """Format past action items for inclusion in LLM prompt."""
        if not actions:
            return "No previous solutions attempted (this is a newly identified pattern)"
        
        formatted = []
        for act in actions:
            title = act.get('title', 'Untitled action')
            status = act.get('status', 'unknown')
            created = act.get('created_at', 'Unknown date')
            body = act.get('body', '')
            
            # Truncate body if too long
            if body and len(body) > 150:
                body = body[:150] + "..."
            
            formatted.append(
                f"- [{status.upper()}] {title}\n"
                f"  Date: {created}\n"
                f"  Details: {body if body else 'No details'}"
            )
        
        return "\n\n".join(formatted)
    
    def _generate_fallback_strategy(self, cluster: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a simple fallback strategy when LiteLLM fails.
        
        Uses basic pattern matching (original implementation).
        """
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
            "implementation_steps": [
                "Review pattern incidents",
                "Design and implement solution",
                "Test in staging environment",
                "Deploy to production"
            ],
            "risks": ["Implementation complexity", "Potential system impact"],
            "success_metrics": ["Reduction in pattern frequency", "Zero recurrence for 30 days"],
            "status": "proposed",
            "forward_score": cluster.get("frequency", 1),
            "backward_score": cluster.get("frequency", 1),
            "blocking_multiplier": 1.5,
            "priority_score": cluster.get("frequency", 1) * 1.5,
        }
        
        return strategy
    
    def _save_strategy(self, strategy: Dict[str, Any]):
        """Save a strategy to the graph with enhanced fields."""
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
            implementation_steps: $implementation_steps,
            risks: $risks,
            success_metrics: $success_metrics,
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
            "implementation_steps": strategy.get("implementation_steps", []),
            "risks": strategy.get("risks", []),
            "success_metrics": strategy.get("success_metrics", []),
            "forward_score": strategy["forward_score"],
            "backward_score": strategy["backward_score"],
            "blocking_multiplier": strategy["blocking_multiplier"],
            "priority_score": strategy["priority_score"],
        })
        
        logger.info(f"Created strategy: {strategy_id} - {strategy['title']}")
