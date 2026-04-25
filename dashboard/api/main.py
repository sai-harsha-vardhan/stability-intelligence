"""
Stability Intelligence Dashboard API (FastAPI).

Provides 9 REST endpoints for the stability intelligence dashboard:
- Graph visualization (Cytoscape.js format)
- Unified priority ranking
- Pattern clusters
- Progress tracking
- Agent activity
- Change feed
- System health
- Statistics
- Node details

Usage::

    cd /home/sai_harsha/stability/rca-intelligence-system/stability-intelligence
    uvicorn dashboard.api.main:app --host 0.0.0.0 --port 8000 --reload

API Documentation available at /docs
"""

import os
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from enum import Enum

from fastapi import FastAPI, HTTPException, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from graph.client import get_client, query as neo4j_query
from graph.queries import get_query
from agents.base import BaseAgent


# ============================================================================
# Pydantic Models
# ============================================================================

class CytoscapeNode(BaseModel):
    """Cytoscape.js node element."""
    data: Dict[str, Any] = Field(..., description="Node data including id, label, type")


class CytoscapeEdge(BaseModel):
    """Cytoscape.js edge element."""
    data: Dict[str, Any] = Field(..., description="Edge data including source, target, label")


class GraphVisualizationResponse(BaseModel):
    """Graph data in Cytoscape.js format."""
    nodes: List[CytoscapeNode]
    edges: List[CytoscapeEdge]
    total_nodes: int
    total_edges: int


class PriorityItem(BaseModel):
    """Unified priority ranking item (ActionItem or Strategy)."""
    id: str
    type: str = Field(..., description="'action_item' or 'strategy'")
    title: str
    description: str
    priority_score: float
    forward_score: int
    backward_score: int
    blocking_multiplier: float
    status: str
    implementation_complexity: Optional[str] = None
    estimated_reduction_percent: Optional[float] = None
    pattern_clusters: List[str]
    trend: Optional[str] = None


class PriorityRankingResponse(BaseModel):
    """Unified priority ranking response."""
    items: List[PriorityItem]
    count: int
    generated_at: str


class PatternCluster(BaseModel):
    """Pattern cluster card data."""
    id: str
    name: str
    description: str
    frequency: int
    trend: str
    incident_count: int
    open_action_items: int
    strategies: int
    affected_components: List[str]


class PatternClustersResponse(BaseModel):
    """Pattern clusters response."""
    clusters: List[PatternCluster]
    count: int
    generated_at: str


class ProgressItem(BaseModel):
    """Action item progress tracker item."""
    id: str
    title: str
    status: str
    assignee: str
    priority_score: float
    implementation_complexity: str
    created_at: Optional[str] = None
    resolved_at: Optional[str] = None
    effective: Optional[bool] = None
    pattern_cluster_name: Optional[str] = None


class ProgressStats(BaseModel):
    """Progress statistics."""
    total: int
    open: int
    in_progress: int
    resolved: int
    deferred: int
    effective_count: int
    ineffective_count: int


class ProgressTrackerResponse(BaseModel):
    """Progress tracker response."""
    items: List[ProgressItem]
    stats: ProgressStats
    filter: str


class ActivityEvent(BaseModel):
    """Agent activity event."""
    id: str
    agent_name: str
    event_type: str
    message: str
    details: Dict[str, Any]
    linked_node_id: Optional[str] = None
    linked_node_type: Optional[str] = None
    created_at: Optional[str] = None


class AgentActivityResponse(BaseModel):
    """Agent activity feed response."""
    events: List[ActivityEvent]
    count: int
    generated_at: str


class ChangeEvent(BaseModel):
    """Real-time change event."""
    id: str
    event_type: str
    node_type: str
    node_id: str
    title: str
    change_description: str
    severity: Optional[str] = None
    created_at: str


class ChangeFeedResponse(BaseModel):
    """Change feed response."""
    events: List[ChangeEvent]
    count: int
    generated_at: str


class ComponentHealth(BaseModel):
    """Component health status."""
    name: str
    status: str
    latency_ms: float
    last_check: str


class SystemHealthResponse(BaseModel):
    """System health status response."""
    status: str
    timestamp: str
    components: Dict[str, ComponentHealth]
    overall_healthy: bool


class SystemStats(BaseModel):
    """System-wide statistics."""
    total_incidents: int
    total_action_items: int
    total_strategies: int
    total_pattern_clusters: int
    open_action_items: int
    resolved_action_items: int
    proposed_strategies: int
    implemented_strategies: int
    worsening_patterns: int
    stable_patterns: int
    improving_patterns: int


class StatsResponse(BaseModel):
    """Statistics response."""
    stats: SystemStats
    generated_at: str


class NodeDetailsResponse(BaseModel):
    """Detailed node information."""
    id: str
    type: str
    properties: Dict[str, Any]
    relationships: List[Dict[str, Any]]
    related_nodes: List[Dict[str, Any]]


# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="Stability Intelligence Dashboard API",
    version="1.0.0",
    description=(
        "REST API for the Stability Intelligence System dashboard. "
        "Provides graph visualization, priority rankings, pattern clusters, "
        "progress tracking, agent activity, and system health monitoring."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Helper Functions
# ============================================================================

def _get_neo4j_client():
    """Get Neo4j client with error handling."""
    try:
        return get_client()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Neo4j connection failed: {str(e)}")


def _convert_datetime(dt: Any) -> Optional[str]:
    """Convert datetime to ISO string."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    if isinstance(dt, str):
        return dt
    return str(dt)


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", tags=["meta"])
def root() -> Dict[str, Any]:
    """API root - returns basic info and links."""
    return {
        "name": "Stability Intelligence Dashboard API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": [
            "/graph",
            "/priorities",
            "/patterns",
            "/progress",
            "/activity",
            "/change-feed",
            "/health",
            "/stats",
            "/nodes/{node_id}",
        ],
    }


@app.get("/graph", response_model=GraphVisualizationResponse, tags=["visualization"])
def get_graph(
    limit: int = Query(1000, ge=1, le=5000, description="Maximum nodes to return"),
    include_types: Optional[List[str]] = Query(None, description="Filter by node types"),
) -> Dict[str, Any]:
    """
    Get graph visualization data in Cytoscape.js format.
    
    Returns nodes and edges for interactive graph visualization including
    incidents, action items, pattern clusters, strategies, and components.
    """
    client = _get_neo4j_client()
    
    try:
        # Get nodes
        nodes_query = get_query("get_all_nodes_for_visualization")
        nodes_result = client.read(nodes_query, {"skip": 0, "limit": limit})
        
        nodes = []
        for record in nodes_result:
            node_data = record.get("node", {})
            if node_data:
                nodes.append({
                    "data": {
                        "id": node_data.get("id"),
                        "label": node_data.get("label", node_data.get("id")),
                        "type": node_data.get("type", "Unknown"),
                        "color": node_data.get("color", "#9CA3AF"),
                    }
                })
        
        # Get edges
        edges_query = get_query("get_all_edges_for_visualization")
        edges_result = client.read(edges_query, {"skip": 0, "limit": limit * 2})
        
        edges = []
        for record in edges_result:
            edge_data = record.get("edge", {})
            if edge_data:
                edges.append({
                    "data": {
                        "id": edge_data.get("id"),
                        "source": edge_data.get("source"),
                        "target": edge_data.get("target"),
                        "label": edge_data.get("label", ""),
                        "weight": edge_data.get("weight", 1.0),
                    }
                })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch graph data: {str(e)}")


@app.get("/priorities", response_model=PriorityRankingResponse, tags=["priorities"])
def get_priorities(
    limit: int = Query(50, ge=1, le=200, description="Number of items to return"),
    include_strategies: bool = Query(True, description="Include strategies in ranking"),
) -> Dict[str, Any]:
    """
    Get unified priority ranking combining ActionItems and Strategies.
    
    Items are sorted by priority_score (descending), showing the most impactful
    work items first. Includes forward/backward scores and trend indicators.
    """
    client = _get_neo4j_client()
    items = []
    
    try:
        # Get action items
        action_items_query = get_query("get_top_action_items")
        action_items = client.read(action_items_query, {"limit": limit})
        
        for ai in action_items:
            items.append({
                "id": ai.get("id"),
                "type": "action_item",
                "title": ai.get("title", ""),
                "description": ai.get("description", ""),
                "priority_score": ai.get("priority_score", 0.0),
                "forward_score": ai.get("forward_score", 0),
                "backward_score": ai.get("backward_score", 0),
                "blocking_multiplier": ai.get("blocking_multiplier", 1.0),
                "status": ai.get("status", "open"),
                "implementation_complexity": ai.get("implementation_complexity"),
                "pattern_clusters": ai.get("pattern_clusters", []) or [],
            })
        
        # Get strategies if requested
        if include_strategies:
            strategies_query = get_query("get_top_strategies")
            strategies = client.read(strategies_query, {"limit": limit})
            
            for s in strategies:
                items.append({
                    "id": s.get("id"),
                    "type": "strategy",
                    "title": s.get("title", ""),
                    "description": s.get("description", ""),
                    "priority_score": s.get("priority_score", 0.0),
                    "forward_score": s.get("forward_score", 0),
                    "backward_score": s.get("backward_score", 0),
                    "blocking_multiplier": s.get("blocking_multiplier", 1.0),
                    "status": s.get("status", "proposed"),
                    "estimated_reduction_percent": s.get("estimated_reduction"),
                    "pattern_clusters": [],
                })
        
        # Sort by priority score descending
        items.sort(key=lambda x: x["priority_score"], reverse=True)
        
        return {
            "items": items[:limit],
            "count": len(items[:limit]),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch priorities: {str(e)}")


@app.get("/patterns", response_model=PatternClustersResponse, tags=["patterns"])
def get_patterns(
    trend: Optional[str] = Query(None, description="Filter by trend: worsening, stable, improving"),
    min_frequency: int = Query(1, ge=1, description="Minimum incident frequency"),
) -> Dict[str, Any]:
    """
    Get pattern clusters with trend analysis.
    
    Returns pattern clusters showing related incidents, common components,
    and trend indicators (worsening/stable/improving).
    """
    client = _get_neo4j_client()
    
    try:
        query = get_query("get_pattern_clusters")
        clusters_result = client.read(query)
        
        clusters = []
        for pc in clusters_result:
            # Apply filters
            if trend and pc.get("trend") != trend:
                continue
            if pc.get("frequency", 0) < min_frequency:
                continue
            
            clusters.append({
                "id": pc.get("id"),
                "name": pc.get("name", ""),
                "description": pc.get("description", ""),
                "frequency": pc.get("frequency", 0),
                "trend": pc.get("trend", "stable"),
                "incident_count": pc.get("incident_count", 0),
                "open_action_items": pc.get("open_action_items", 0),
                "strategies": pc.get("strategies", 0),
                "affected_components": pc.get("affected_components", []) or [],
            })
        
        return {
            "clusters": clusters,
            "count": len(clusters),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch patterns: {str(e)}")


@app.get("/progress", response_model=ProgressTrackerResponse, tags=["progress"])
def get_progress(
    status_filter: str = Query("all", description="Filter: all, open, in_progress, done"),
    limit: int = Query(100, ge=1, le=500, description="Number of items to return"),
) -> Dict[str, Any]:
    """
    Get action item progress tracker.
    
    Returns action items with their status, assignee, priority score,
    and effectiveness metrics for completed items.
    """
    client = _get_neo4j_client()
    
    try:
        # Get all action items with details
        query = """
        MATCH (ai:ActionItem)
        OPTIONAL MATCH (ai)-[:BLOCKS_PATTERN]->(pc:PatternCluster)
        RETURN ai.id AS id,
               ai.title AS title,
               ai.status AS status,
               ai.assignee AS assignee,
               ai.priority_score AS priority_score,
               ai.implementation_complexity AS implementation_complexity,
               ai.created_at AS created_at,
               ai.resolved_at AS resolved_at,
               ai.effective AS effective,
               pc.name AS pattern_cluster_name
        ORDER BY ai.priority_score DESC
        """
        
        action_items = client.read(query)
        
        items = []
        stats = {"total": 0, "open": 0, "in_progress": 0, "resolved": 0, "deferred": 0, "effective_count": 0, "ineffective_count": 0}
        
        for ai in action_items:
            status = ai.get("status", "open")
            effective = ai.get("effective")
            
            # Update stats
            stats["total"] += 1
            if status == "open":
                stats["open"] += 1
            elif status == "in_progress":
                stats["in_progress"] += 1
            elif status == "resolved":
                stats["resolved"] += 1
                if effective is True:
                    stats["effective_count"] += 1
                elif effective is False:
                    stats["ineffective_count"] += 1
            elif status == "deferred":
                stats["deferred"] += 1
            
            # Apply filter
            if status_filter != "all":
                if status_filter == "done" and status not in ["resolved", "closed"]:
                    continue
                elif status_filter != "done" and status != status_filter:
                    continue
            
            items.append({
                "id": ai.get("id"),
                "title": ai.get("title", ""),
                "status": status,
                "assignee": ai.get("assignee", ""),
                "priority_score": ai.get("priority_score", 0.0),
                "implementation_complexity": ai.get("implementation_complexity", "medium"),
                "created_at": _convert_datetime(ai.get("created_at")),
                "resolved_at": _convert_datetime(ai.get("resolved_at")),
                "effective": effective,
                "pattern_cluster_name": ai.get("pattern_cluster_name"),
            })
        
        return {
            "items": items[:limit],
            "stats": stats,
            "filter": status_filter,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch progress: {str(e)}")


@app.get("/activity", response_model=AgentActivityResponse, tags=["activity"])
def get_activity(
    limit: int = Query(50, ge=1, le=200, description="Number of events to return"),
    agent_name: Optional[str] = Query(None, description="Filter by agent name"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
) -> Dict[str, Any]:
    """
    Get agent activity feed.
    
    Returns recent agent run history including ingestion, pattern detection,
    impact scoring, strategy generation, and feedback loop events.
    """
    client = _get_neo4j_client()
    
    try:
        query_str = get_query("get_activity_events")
        events_result = client.read(query_str, {"skip": 0, "limit": limit * 2})
        
        events = []
        for ae in events_result:
            # Apply filters
            if agent_name and ae.get("agent_name") != agent_name:
                continue
            if event_type and ae.get("event_type") != event_type:
                continue
            
            events.append({
                "id": ae.get("id"),
                "agent_name": ae.get("agent_name", ""),
                "event_type": ae.get("event_type", ""),
                "message": ae.get("message", ""),
                "details": ae.get("details", {}),
                "linked_node_id": ae.get("linked_node_id"),
                "linked_node_type": ae.get("linked_node_type"),
                "created_at": _convert_datetime(ae.get("created_at")),
            })
        
        return {
            "events": events[:limit],
            "count": len(events[:limit]),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch activity: {str(e)}")


@app.get("/change-feed", response_model=ChangeFeedResponse, tags=["changes"])
def get_change_feed(
    limit: int = Query(50, ge=1, le=200, description="Number of events to return"),
    since_hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
) -> Dict[str, Any]:
    """
    Get real-time change feed.
    
    Returns recent activity events including issue updates, pattern detections,
    and strategy generations within the specified time window.
    """
    client = _get_neo4j_client()
    
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        
        query_str = """
        MATCH (ae:ActivityEvent)
        WHERE ae.created_at >= $since
        RETURN ae.id AS id,
               ae.event_type AS event_type,
               ae.agent_name AS agent_name,
               ae.message AS message,
               ae.details AS details,
               ae.linked_node_id AS linked_node_id,
               ae.linked_node_type AS linked_node_type,
               ae.created_at AS created_at
        ORDER BY ae.created_at DESC
        LIMIT $limit
        """
        
        events_result = client.read(query_str, {"since": since.isoformat(), "limit": limit})
        
        events = []
        for ae in events_result:
            # Map event types to change descriptions
            event_type = ae.get("event_type", "")
            message = ae.get("message", "")
            details = ae.get("details", {})
            node_type = ae.get("linked_node_type", "ActivityEvent")
            
            events.append({
                "id": ae.get("id"),
                "event_type": event_type,
                "node_type": node_type,
                "node_id": ae.get("linked_node_id", ae.get("id")),
                "title": details.get("title", message[:50]),
                "change_description": message,
                "severity": details.get("severity"),
                "created_at": _convert_datetime(ae.get("created_at")),
            })
        
        return {
            "events": events,
            "count": len(events),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch change feed: {str(e)}")


@app.get("/health", response_model=SystemHealthResponse, tags=["health"])
def get_health() -> Dict[str, Any]:
    """
    Get system health status.
    
    Returns health status of all system components including Neo4j,
    LiteLLM, and graph data freshness.
    """
    components = {}
    overall_healthy = True
    
    # Check Neo4j
    try:
        client = _get_neo4j_client()
        neo4j_health = client.health_check()
        is_healthy = neo4j_health.get("status") == "healthy"
        components["neo4j"] = {
            "name": "Neo4j Graph Database",
            "status": "healthy" if is_healthy else "unhealthy",
            "latency_ms": 0.0,  # Could measure actual latency
            "last_check": datetime.now(timezone.utc).isoformat(),
        }
        if not is_healthy:
            overall_healthy = False
    except Exception as e:
        components["neo4j"] = {
            "name": "Neo4j Graph Database",
            "status": "error",
            "latency_ms": 0.0,
            "last_check": datetime.now(timezone.utc).isoformat(),
        }
        overall_healthy = False
    
    # Check LiteLLM
    try:
        # Simple health check - verify LiteLLM URL is configured
        litellm_url = os.getenv("LITELLM_BASE_URL", "http://litellm:4000")
        litellm_api_key = os.getenv("LITELLM_API_KEY", "")
        # Try to create a BaseAgent instance to verify connectivity
        temp_agent = BaseAgent("health-check", litellm_url=litellm_url, litellm_api_key=litellm_api_key)
        components["litellm"] = {
            "name": "LiteLLM Gateway",
            "status": "healthy",
            "latency_ms": 0.0,
            "last_check": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        components["litellm"] = {
            "name": "LiteLLM Gateway",
            "status": "error",
            "latency_ms": 0.0,
            "last_check": datetime.now(timezone.utc).isoformat(),
        }
        overall_healthy = False
    
    # Check graph staleness
    try:
        client = _get_neo4j_client()
        staleness_result = client.read("""
            MATCH (n) 
            RETURN max(n.updated_at) as last_update, count(n) as node_count
        """)
        if staleness_result:
            last_update = staleness_result[0].get("last_update")
            node_count = staleness_result[0].get("node_count", 0)
            
            is_stale = False
            if last_update:
                last_update_dt = datetime.fromisoformat(str(last_update).replace('Z', '+00:00'))
                hours_since_update = (datetime.now(timezone.utc) - last_update_dt).total_seconds() / 3600
                is_stale = hours_since_update > 24
            
            components["graph_freshness"] = {
                "name": "Graph Data Freshness",
                "status": "stale" if is_stale else "fresh",
                "latency_ms": 0.0,
                "last_check": datetime.now(timezone.utc).isoformat(),
            }
            if is_stale:
                overall_healthy = False
    except Exception as e:
        components["graph_freshness"] = {
            "name": "Graph Data Freshness",
            "status": "error",
            "latency_ms": 0.0,
            "last_check": datetime.now(timezone.utc).isoformat(),
        }
    
    return {
        "status": "healthy" if overall_healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": components,
        "overall_healthy": overall_healthy,
    }


@app.get("/stats", response_model=StatsResponse, tags=["statistics"])
def get_stats() -> Dict[str, Any]:
    """
    Get system-wide statistics.
    
    Returns counts of incidents, action items, strategies, and patterns
    along with their breakdowns.
    """
    client = _get_neo4j_client()
    
    try:
        # Get counts
        counts_result = client.read("""
            MATCH (i:Incident) RETURN count(i) as count
            UNION ALL
            MATCH (ai:ActionItem) RETURN count(ai) as count
            UNION ALL
            MATCH (s:Strategy) RETURN count(s) as count
            UNION ALL
            MATCH (pc:PatternCluster) RETURN count(pc) as count
        """)
        
        total_incidents = counts_result[0]["count"] if len(counts_result) > 0 else 0
        total_action_items = counts_result[1]["count"] if len(counts_result) > 1 else 0
        total_strategies = counts_result[2]["count"] if len(counts_result) > 2 else 0
        total_pattern_clusters = counts_result[3]["count"] if len(counts_result) > 3 else 0
        
        # Get status breakdowns
        action_item_status = client.read("""
            MATCH (ai:ActionItem)
            RETURN ai.status as status, count(ai) as count
        """)
        
        open_action_items = sum(r["count"] for r in action_item_status if r["status"] == "open")
        resolved_action_items = sum(r["count"] for r in action_item_status if r["status"] == "resolved")
        
        strategy_status = client.read("""
            MATCH (s:Strategy)
            RETURN s.status as status, count(s) as count
        """)
        
        proposed_strategies = sum(r["count"] for r in strategy_status if r["status"] == "proposed")
        implemented_strategies = sum(r["count"] for r in strategy_status if r["status"] == "implemented")
        
        pattern_trends = client.read("""
            MATCH (pc:PatternCluster)
            RETURN pc.trend as trend, count(pc) as count
        """)
        
        worsening_patterns = sum(r["count"] for r in pattern_trends if r["trend"] == "worsening")
        stable_patterns = sum(r["count"] for r in pattern_trends if r["trend"] == "stable")
        improving_patterns = sum(r["count"] for r in pattern_trends if r["trend"] == "improving")
        
        return {
            "stats": {
                "total_incidents": total_incidents,
                "total_action_items": total_action_items,
                "total_strategies": total_strategies,
                "total_pattern_clusters": total_pattern_clusters,
                "open_action_items": open_action_items,
                "resolved_action_items": resolved_action_items,
                "proposed_strategies": proposed_strategies,
                "implemented_strategies": implemented_strategies,
                "worsening_patterns": worsening_patterns,
                "stable_patterns": stable_patterns,
                "improving_patterns": improving_patterns,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {str(e)}")


@app.get("/nodes/{node_id}", response_model=NodeDetailsResponse, tags=["nodes"])
def get_node_details(
    node_id: str = Path(..., description="Unique node identifier"),
) -> Dict[str, Any]:
    """
    Get detailed information for a specific node.
    
    Returns node properties, relationships, and related nodes.
    """
    client = _get_neo4j_client()
    
    try:
        # Get node details
        node_query = get_query("get_node_by_id")
        node_result = client.read(node_query, {"id": node_id})
        
        if not node_result:
            raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
        
        node_data = node_result[0]
        node_type = node_data.get("node_type", "Unknown")
        
        # Get relationships
        rels_query = """
        MATCH (n {id: $id})-[r]-(m)
        RETURN type(r) as rel_type,
               r.confidence as confidence,
               m.id as related_id,
               labels(m)[0] as related_type,
               CASE 
                   WHEN m.title IS NOT NULL THEN m.title
                   WHEN m.name IS NOT NULL THEN m.name
                   ELSE m.id
               END as related_label,
               startNode(r).id = $id as is_outgoing
        LIMIT 50
        """
        
        relationships = client.read(rels_query, {"id": node_id})
        
        # Get related nodes
        related_nodes = []
        for rel in relationships:
            related_nodes.append({
                "id": rel.get("related_id"),
                "type": rel.get("related_type"),
                "label": rel.get("related_label"),
                "relationship": rel.get("rel_type"),
                "direction": "outgoing" if rel.get("is_outgoing") else "incoming",
                "confidence": rel.get("confidence", 1.0),
            })
        
        return {
            "id": node_id,
            "type": node_type,
            "properties": {
                k: v for k, v in node_data.items() 
                if k not in ["node_type"] and v is not None
            },
            "relationships": [
                {
                    "type": r.get("rel_type"),
                    "confidence": r.get("confidence", 1.0),
                    "direction": "outgoing" if r.get("is_outgoing") else "incoming",
                }
                for r in relationships
            ],
            "related_nodes": related_nodes,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch node details: {str(e)}")


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    """Handle uncaught exceptions."""
    return HTTPException(
        status_code=500,
        detail=f"Internal server error: {str(exc)}"
    )


# ============================================================================
# Startup/Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    print(f"Dashboard API started at {datetime.now(timezone.utc).isoformat()}")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    from graph.client import close_client
    close_client()
    print(f"Dashboard API stopped at {datetime.now(timezone.utc).isoformat()}")
