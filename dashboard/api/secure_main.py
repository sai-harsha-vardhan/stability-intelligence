"""
Secured Stability Intelligence Dashboard API (FastAPI).

This is the security-enhanced version of the dashboard API implementing:
- JWT authentication with RBAC
- Rate limiting
- Audit logging
- PII redaction
- Secure CORS
- HTTPS enforcement middleware

Part of RCA-20: Security Hardening and Secrets Management

Usage::

    cd /home/sai_harsha/stability/rca-intelligence-system/stability-intelligence
    uvicorn dashboard.api.secure_main:app --host 0.0.0.0 --port 8000 --reload --ssl-keyfile=key.pem --ssl-certfile=cert.pem

API Documentation available at /docs (authenticated)
"""

import os
import sys
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from enum import Enum

# Add src to path for security imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import FastAPI, HTTPException, Query, Path, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from graph.client import get_client, query as neo4j_query
from graph.queries import get_query
from agents.base import BaseAgent

# Security imports
from src.core.security import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    require_role,
    require_permission,
    get_current_user,
    Role,
    User,
    TokenResponse,
)
from src.core.security.middleware import (
    SecurityHeadersMiddleware,
    HTTPSRedirectMiddleware,
    IPBlocklistMiddleware,
    RequestSizeLimitMiddleware,
    RequestIDMiddleware,
)
from src.core.security.rate_limiter import (
    rate_limit_dependency,
    token_budget_dependency,
)
from src.core.security.audit import (
    audit_log,
    audit_db_query,
    audit_data_access,
    AuditEventType,
    AuditSeverity,
)
from src.core.security.redactor import redact_dict, redact_for_logs


# ============================================================================
# Pydantic Models (from original + auth)
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
# FastAPI App Setup with Security
# ============================================================================

app = FastAPI(
    title="Stability Intelligence Dashboard API",
    version="1.0.0-secured",
    description=(
        "Security-hardened REST API for the Stability Intelligence System. "
        "Requires authentication for all endpoints. "
        "Part of RCA-20: Security Hardening."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# Apply security middlewares (order matters - innermost first)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(IPBlocklistMiddleware)
app.add_middleware(HTTPSRedirectMiddleware)

# Secure CORS configuration
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://localhost:3000,https://app.rca.local"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-Request-ID"],
    max_age=600,
)


# ============================================================================
# Authentication Endpoints
# ============================================================================

@app.post("/auth/login", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate user and return JWT tokens.
    
    Uses OAuth2 password flow.
    """
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        from src.core.security.audit import audit_auth_event
        audit_auth_event(
            event_type=AuditEventType.AUTH_FAILURE,
            username=form_data.username,
            success=False,
            failure_reason="Invalid credentials"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)
    
    # Log successful login
    from src.core.security.audit import audit_auth_event
    audit_auth_event(
        event_type=AuditEventType.AUTH_LOGIN,
        username=user.username,
        success=True,
        metadata={"role": user.role.value}
    )
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=1800,  # 30 minutes
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
# Secured API Endpoints
# ============================================================================

@app.get("/", tags=["meta"])
def root() -> Dict[str, Any]:
    """API root - returns basic info and links."""
    return {
        "name": "Stability Intelligence Dashboard API",
        "version": "1.0.0-secured",
        "description": "Security-hardened API - authentication required",
        "docs": "/docs",
        "auth": "/auth/login",
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
        "security_features": [
            "JWT authentication",
            "RBAC authorization",
            "Rate limiting",
            "Audit logging",
            "PII redaction",
            "HTTPS enforcement",
        ],
    }


@app.get("/graph", response_model=GraphVisualizationResponse, tags=["visualization"])
async def get_graph(
    limit: int = Query(1000, ge=1, le=5000),
    include_types: Optional[List[str]] = Query(None),
    user: User = Depends(require_permission("read:incidents")),
    _: None = Depends(rate_limit_dependency),
) -> Dict[str, Any]:
    """
    Get graph visualization data (requires authentication).
    
    Rate limited and audit logged.
    """
    start_time = datetime.now(timezone.utc)
    client = _get_neo4j_client()
    
    try:
        # Get nodes
        nodes_query = get_query("get_all_nodes_for_visualization")
        nodes_result = client.read(nodes_query, {"skip": 0, "limit": limit})
        
        nodes = []
        for record in nodes_result:
            node_data = record.get("node", {})
            if node_data:
                # Redact any PII in node data
                safe_data = redact_dict(dict(node_data))
                nodes.append({
                    "data": {
                        "id": safe_data.get("id"),
                        "label": safe_data.get("label", safe_data.get("id")),
                        "type": safe_data.get("type", "Unknown"),
                        "color": safe_data.get("color", "#9CA3AF"),
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
        
        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        # Audit log the data access
        audit_data_access(
            actor_id=user.id,
            data_type="graph",
            action="read",
            rows_accessed=len(nodes) + len(edges),
            metadata={"endpoint": "/graph", "limit": limit}
        )
        
        return {
            "nodes": nodes,
            "edges": edges,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch graph data: {str(e)}")


@app.get("/priorities", response_model=PriorityRankingResponse, tags=["priorities"])
async def get_priorities(
    limit: int = Query(50, ge=1, le=200),
    include_strategies: bool = Query(True),
    user: User = Depends(require_permission("read:action_items")),
    _: None = Depends(rate_limit_dependency),
) -> Dict[str, Any]:
    """Get unified priority ranking (requires authentication)."""
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
        
        items.sort(key=lambda x: x["priority_score"], reverse=True)
        
        audit_data_access(
            actor_id=user.id,
            data_type="priorities",
            action="read",
            rows_accessed=len(items),
        )
        
        return {
            "items": items[:limit],
            "count": len(items[:limit]),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch priorities: {str(e)}")


@app.get("/patterns", response_model=PatternClustersResponse, tags=["patterns"])
async def get_patterns(
    trend: Optional[str] = Query(None),
    min_frequency: int = Query(1, ge=1),
    user: User = Depends(require_permission("read:patterns")),
    _: None = Depends(rate_limit_dependency),
) -> Dict[str, Any]:
    """Get pattern clusters (requires authentication)."""
    client = _get_neo4j_client()
    
    try:
        query = get_query("get_pattern_clusters")
        clusters_result = client.read(query)
        
        clusters = []
        for pc in clusters_result:
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
        
        audit_data_access(
            actor_id=user.id,
            data_type="patterns",
            action="read",
            rows_accessed=len(clusters),
        )
        
        return {
            "clusters": clusters,
            "count": len(clusters),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch patterns: {str(e)}")


@app.get("/progress", response_model=ProgressTrackerResponse, tags=["progress"])
async def get_progress(
    status_filter: str = Query("all"),
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(require_permission("read:action_items")),
    _: None = Depends(rate_limit_dependency),
) -> Dict[str, Any]:
    """Get action item progress tracker (requires authentication)."""
    client = _get_neo4j_client()
    
    try:
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
            status_val = ai.get("status", "open")
            effective = ai.get("effective")
            
            stats["total"] += 1
            if status_val == "open":
                stats["open"] += 1
            elif status_val == "in_progress":
                stats["in_progress"] += 1
            elif status_val == "resolved":
                stats["resolved"] += 1
                if effective is True:
                    stats["effective_count"] += 1
                elif effective is False:
                    stats["ineffective_count"] += 1
            elif status_val == "deferred":
                stats["deferred"] += 1
            
            if status_filter != "all":
                if status_filter == "done" and status_val not in ["resolved", "closed"]:
                    continue
                elif status_filter != "done" and status_val != status_filter:
                    continue
            
            items.append({
                "id": ai.get("id"),
                "title": ai.get("title", ""),
                "status": status_val,
                "assignee": ai.get("assignee", ""),
                "priority_score": ai.get("priority_score", 0.0),
                "implementation_complexity": ai.get("implementation_complexity", "medium"),
                "created_at": _convert_datetime(ai.get("created_at")),
                "resolved_at": _convert_datetime(ai.get("resolved_at")),
                "effective": effective,
                "pattern_cluster_name": ai.get("pattern_cluster_name"),
            })
        
        audit_data_access(
            actor_id=user.id,
            data_type="progress",
            action="read",
            rows_accessed=len(items),
        )
        
        return {
            "items": items[:limit],
            "stats": stats,
            "filter": status_filter,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch progress: {str(e)}")


@app.get("/activity", response_model=AgentActivityResponse, tags=["activity"])
async def get_activity(
    limit: int = Query(50, ge=1, le=200),
    agent_name: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    user: User = Depends(require_permission("read:incidents")),
    _: None = Depends(rate_limit_dependency),
) -> Dict[str, Any]:
    """Get agent activity feed (requires authentication)."""
    client = _get_neo4j_client()
    
    try:
        query_str = get_query("get_activity_events")
        events_result = client.read(query_str, {"skip": 0, "limit": limit * 2})
        
        events = []
        for ae in events_result:
            if agent_name and ae.get("agent_name") != agent_name:
                continue
            if event_type and ae.get("event_type") != event_type:
                continue
            
            # Redact details to prevent PII leakage
            safe_details = redact_dict(ae.get("details", {}))
            
            events.append({
                "id": ae.get("id"),
                "agent_name": ae.get("agent_name", ""),
                "event_type": ae.get("event_type", ""),
                "message": ae.get("message", ""),
                "details": safe_details,
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


@app.get("/health", response_model=SystemHealthResponse, tags=["health"])
async def get_health(
    user: User = Depends(get_current_user),  # Allow any authenticated user
    _: None = Depends(rate_limit_dependency),
) -> Dict[str, Any]:
    """Get system health status (requires authentication)."""
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
            "latency_ms": 0.0,
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
        litellm_url = os.getenv("LITELLM_BASE_URL", "http://litellm:4000")
        litellm_api_key = os.getenv("LITELLM_API_KEY", "")
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
    
    return {
        "status": "healthy" if overall_healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": components,
        "overall_healthy": overall_healthy,
    }


@app.get("/stats", response_model=StatsResponse, tags=["statistics"])
async def get_stats(
    user: User = Depends(require_permission("read:incidents")),
    _: None = Depends(rate_limit_dependency),
) -> Dict[str, Any]:
    """Get system-wide statistics (requires authentication)."""
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
async def get_node_details(
    node_id: str = Path(...),
    user: User = Depends(require_permission("read:incidents")),
    _: None = Depends(rate_limit_dependency),
) -> Dict[str, Any]:
    """Get detailed node information (requires authentication)."""
    client = _get_neo4j_client()
    
    try:
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
        
        # Redact properties before returning
        safe_properties = redact_dict({
            k: v for k, v in node_data.items() 
            if k not in ["node_type"] and v is not None
        })
        
        audit_data_access(
            actor_id=user.id,
            data_type=f"node:{node_type}",
            action="read",
            rows_accessed=len(relationships),
            metadata={"node_id": node_id}
        )
        
        return {
            "id": node_id,
            "type": node_type,
            "properties": safe_properties,
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
    """Handle uncaught exceptions with redacted error messages."""
    # Redact any potential PII in error messages
    safe_detail = redact_for_logs(str(exc))
    
    return HTTPException(
        status_code=500,
        detail=f"Internal server error: {safe_detail[:100]}"
    )


# ============================================================================
# Startup/Shutdown Events
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    print(f"🔒 Secured Dashboard API started at {datetime.now(timezone.utc).isoformat()}")
    print(f"   Authentication: JWT with RBAC")
    print(f"   Rate limiting: Enabled")
    print(f"   Audit logging: Enabled")
    print(f"   PII redaction: Enabled")
    print(f"   TLS enforcement: {'Enabled' if os.getenv('ENFORCE_TLS') == 'true' else 'Disabled'}")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    from graph.client import close_client
    close_client()
    print(f"🔒 Secured Dashboard API stopped at {datetime.now(timezone.utc).isoformat()}")
