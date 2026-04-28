"""Cypher queries for the Stability Intelligence System."""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta


# ============================================================================
# Feedback Loop Queries
# ============================================================================

GET_RESOLVED_ACTION_ITEMS_30D = """
MATCH (ai:ActionItem)
WHERE ai.status = 'resolved'
  AND ai.resolved_at >= $since
  AND (ai.effectiveness_checked_at IS NULL OR ai.effective IS NULL)
RETURN ai.id AS id,
       ai.resolved_at AS resolved_at,
       ai.pattern_cluster_id AS pattern_cluster_id
"""

GET_IMPLEMENTED_STRATEGIES_30D = """
MATCH (s:Strategy)
WHERE s.status = 'implemented'
  AND s.implemented_at >= $since
  AND (s.effectiveness_checked_at IS NULL OR s.effective IS NULL)
RETURN s.id AS id,
       s.implemented_at AS implemented_at,
       s.pattern_cluster_ids AS pattern_cluster_ids
"""

COUNT_NEW_INCIDENTS_SINCE_PATTERN = """
MATCH (i:Incident)
WHERE i.created_at >= $since
  AND i.pattern_cluster_id = $pattern_cluster_id
RETURN count(i) AS incident_count
"""

UPDATE_ACTION_ITEM_EFFECTIVENESS = """
MATCH (ai:ActionItem {id: $id})
SET ai.effective = $effective,
    ai.effectiveness_checked_at = datetime(),
    ai.updated_at = datetime()
RETURN ai.id AS id, ai.effective AS effective
"""

UPDATE_STRATEGY_EFFECTIVENESS = """
MATCH (s:Strategy {id: $id})
SET s.effective = $effective,
    s.effectiveness_checked_at = datetime(),
    s.updated_at = datetime()
RETURN s.id AS id, s.effective AS effective
"""

ADJUST_CAUSAL_EDGE_CONFIDENCE = """
MATCH (a)-[r:AFFECTS_PATTERN|BLOCKS_PATTERN|ADDRESSES_PATTERN]->(b)
WHERE a.id IN $node_ids
SET r.confidence = CASE 
    WHEN $effective = true THEN min(r.confidence + 0.1, 1.0)
    ELSE max(r.confidence - 0.1, 0.0)
END,
r.updated_at = datetime()
RETURN count(r) AS edges_updated
"""

CREATE_REINVESTIGATION_ACTION_ITEM = """
CREATE (ai:ActionItem {
    id: $id,
    title: $title,
    description: $description,
    status: 'open',
    created_at: datetime(),
    updated_at: datetime(),
    original_action_item_id: $original_id,
    trigger_reason: $trigger_reason,
    forward_score: 0,
    backward_score: 0,
    priority_score: 0.0
})
WITH ai
MATCH (pc:PatternCluster {id: $pattern_cluster_id})
CREATE (ai)-[:BLOCKS_PATTERN {confidence: 0.5}]->(pc)
RETURN ai.id AS id
"""

FINALIZE_EFFECTIVENESS_OUTSIDE_WINDOW = """
MATCH (ai:ActionItem)
WHERE ai.status = 'resolved'
  AND ai.resolved_at < $cutoff_date
  AND ai.effective IS NULL
SET ai.effective = true,
    ai.effectiveness_checked_at = datetime(),
    ai.updated_at = datetime()
RETURN count(ai) AS finalized
"""


# ============================================================================
# General Queries
# ============================================================================

GET_NODE_BY_ID = """
MATCH (n)
WHERE n.id = $id
RETURN n {.id, .title, .description, .status, .created_at, labels(n)[0] AS node_type}
LIMIT 1
"""

GET_ALL_NODES = """
MATCH (n)
RETURN n {.id, labels(n)[0] AS node_type}
SKIP $skip LIMIT $limit
"""

GET_ACTIVITY_EVENTS = """
MATCH (ae:ActivityEvent)
RETURN ae.id AS id,
       ae.agent_name AS agent_name,
       ae.event_type AS event_type,
       ae.message AS message,
       ae.details AS details,
       ae.linked_node_id AS linked_node_id,
       ae.linked_node_type AS linked_node_type,
       ae.created_at AS created_at
ORDER BY ae.created_at DESC
SKIP $skip LIMIT $limit
"""

LOG_ACTIVITY_EVENT = """
CREATE (ae:ActivityEvent {
    id: $id,
    agent_name: $agent_name,
    event_type: $event_type,
    message: $message,
    details: $details,
    linked_node_id: $linked_node_id,
    linked_node_type: $linked_node_type,
    created_at: datetime(),
    updated_at: datetime()
})
RETURN ae.id AS id
"""


# ============================================================================
# Priority Scoring Queries
# ============================================================================

GET_TOP_ACTION_ITEMS = """
MATCH (ai:ActionItem {status: 'open'})
OPTIONAL MATCH (ai)-[:BLOCKS_PATTERN]->(pc:PatternCluster)
RETURN ai.id AS id,
       ai.title AS title,
       COALESCE(ai.description, ai.body, '') AS description,
       COALESCE(ai.priority_score, 0.0) AS priority_score,
       COALESCE(ai.forward_score, 0) AS forward_score,
       COALESCE(ai.backward_score, 0) AS backward_score,
       COALESCE(ai.blocking_multiplier, 1.0) AS blocking_multiplier,
       ai.implementation_complexity AS implementation_complexity,
       ai.stagger_safe AS stagger_safe,
       collect(pc.name) AS pattern_clusters
ORDER BY COALESCE(ai.priority_score, 0.0) DESC
LIMIT $limit
"""

GET_TOP_STRATEGIES = """
MATCH (s:Strategy)
WHERE s.status IN ['proposed', 'implemented']
RETURN s.id AS id,
       s.title AS title,
       COALESCE(s.description, s.body, '') AS description,
       COALESCE(s.priority_score, 0.0) AS priority_score,
       COALESCE(s.forward_score, 0) AS forward_score,
       COALESCE(s.backward_score, 0) AS backward_score,
       COALESCE(s.blocking_multiplier, 1.0) AS blocking_multiplier,
       s.estimated_reduction_percent AS estimated_reduction,
       s.status AS status
ORDER BY COALESCE(s.priority_score, 0.0) DESC
LIMIT $limit
"""


# ============================================================================
# Pattern Cluster Queries
# ============================================================================

GET_PATTERN_CLUSTERS = """
MATCH (pc:PatternCluster)
OPTIONAL MATCH (pc)<-[:BELONGS_TO_CLUSTER]-(i:Incident)
OPTIONAL MATCH (pc)<-[:BLOCKS_PATTERN]-(ai:ActionItem {status: 'open'})
OPTIONAL MATCH (pc)<-[:ADDRESSES_PATTERN]-(s:Strategy)
RETURN pc.id AS id,
       pc.name AS name,
       pc.description AS description,
       pc.frequency AS frequency,
       pc.trend AS trend,
       count(DISTINCT i) AS incident_count,
       count(DISTINCT ai) AS open_action_items,
       count(DISTINCT s) AS strategies
ORDER BY pc.frequency DESC
"""


# ============================================================================
# Graph Visualization Queries
# ============================================================================

GET_ALL_NODES_FOR_VISUALIZATION = """
MATCH (n)
WHERE n:Incident OR n:ActionItem OR n:PatternCluster OR n:Strategy OR n:CodeModule OR n:ConnectorNode
RETURN DISTINCT {
    id: n.id,
    label: COALESCE(n.title, n.name, n.description[0..50], n.id),
    type: CASE
        WHEN n:Incident THEN 'Incident'
        WHEN n:ActionItem THEN 'ActionItem'
        WHEN n:PatternCluster THEN 'PatternCluster'
        WHEN n:Strategy THEN 'Strategy'
        WHEN n:CodeModule THEN 'CodeModule'
        WHEN n:ConnectorNode THEN 'ConnectorNode'
        ELSE 'Unknown'
    END,
    color: CASE
        WHEN n:Incident AND n.severity = 'P0' THEN '#EF4444'
        WHEN n:Incident AND n.severity = 'P1' THEN '#F97316'
        WHEN n:Incident AND n.severity = 'P2' THEN '#EAB308'
        WHEN n:Incident THEN '#6B7280'
        WHEN n:PatternCluster THEN '#8B5CF6'
        WHEN n:ActionItem AND n.status = 'open' THEN '#3B82F6'
        WHEN n:ActionItem THEN '#22C55E'
        WHEN n:Strategy AND n.status = 'proposed' THEN '#06B6D4'
        WHEN n:Strategy THEN '#22C55E'
        ELSE '#9CA3AF'
    END
} AS node
SKIP $skip LIMIT $limit
"""

GET_ALL_EDGES_FOR_VISUALIZATION = """
MATCH (a)-[r]->(b)
WHERE a.id IS NOT NULL AND b.id IS NOT NULL
RETURN DISTINCT {
    id: a.id + '_' + type(r) + '_' + b.id,
    source: a.id,
    target: b.id,
    label: type(r),
    weight: r.confidence
} AS edge
SKIP $skip LIMIT $limit
"""


# ============================================================================
# Helper Functions
# ============================================================================

def get_query(name: str) -> str:
    """Get a query by name."""
    queries = {
        # Feedback loop
        "get_resolved_action_items_30d": GET_RESOLVED_ACTION_ITEMS_30D,
        "get_implemented_strategies_30d": GET_IMPLEMENTED_STRATEGIES_30D,
        "count_new_incidents_since_pattern": COUNT_NEW_INCIDENTS_SINCE_PATTERN,
        "update_action_item_effectiveness": UPDATE_ACTION_ITEM_EFFECTIVENESS,
        "update_strategy_effectiveness": UPDATE_STRATEGY_EFFECTIVENESS,
        "adjust_causal_edge_confidence": ADJUST_CAUSAL_EDGE_CONFIDENCE,
        "create_reinvestigation_action_item": CREATE_REINVESTIGATION_ACTION_ITEM,
        "finalize_effectiveness_outside_window": FINALIZE_EFFECTIVENESS_OUTSIDE_WINDOW,
        # General
        "get_node_by_id": GET_NODE_BY_ID,
        "get_all_nodes": GET_ALL_NODES,
        "get_activity_events": GET_ACTIVITY_EVENTS,
        "log_activity_event": LOG_ACTIVITY_EVENT,
        # Priority
        "get_top_action_items": GET_TOP_ACTION_ITEMS,
        "get_top_strategies": GET_TOP_STRATEGIES,
        # Patterns
        "get_pattern_clusters": GET_PATTERN_CLUSTERS,
        # Visualization
        "get_all_nodes_for_visualization": GET_ALL_NODES_FOR_VISUALIZATION,
        "get_all_edges_for_visualization": GET_ALL_EDGES_FOR_VISUALIZATION,
    }
    return queries.get(name, "")
