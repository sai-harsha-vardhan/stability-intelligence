"""Base agent class with common utilities."""
import os
import uuid
import logging
from typing import Optional, Dict, Any, List

import httpx

from graph.client import get_client, query, write

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base class for all Stability Intelligence agents."""
    
    def __init__(
        self,
        name: str,
        litellm_url: Optional[str] = None,
        litellm_api_key: Optional[str] = None,
    ):
        self.name = name
        self.litellm_url = litellm_url or os.getenv("LITELLM_BASE_URL", "http://litellm:4000")
        self.litellm_api_key = litellm_api_key or os.getenv("LITELLM_API_KEY", "")
        self.graph_client = get_client()
    
    @property
    def neo4j_client(self):
        """Alias for graph_client for backward compatibility."""
        return self.graph_client
    
    def call_claude(
        self,
        prompt: str,
        system: Optional[str] = None,
        trace_name: Optional[str] = None,
        max_tokens: int = 4000,
    ) -> str:
        """Call Claude model via LiteLLM with Langfuse tracing."""
        model = os.getenv("LITELLM_CLAUDE_MODEL", "claude-critical")
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = httpx.post(
                f"{self.litellm_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.litellm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "metadata": {
                        "trace_name": trace_name or f"{self.name}-call",
                    },
                },
                timeout=120,
            )
            response.raise_for_status()
            
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Claude call failed: {e}")
            raise
    
    def call_kimi(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 4000,
    ) -> str:
        """Call Kimi model via LiteLLM."""
        model = os.getenv("LITELLM_KIMI_MODEL", "kimi-default")
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = httpx.post(
                f"{self.litellm_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.litellm_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                },
                timeout=60,
            )
            response.raise_for_status()
            
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Kimi call failed: {e}")
            raise
    
    def query_graph(self, cypher: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a read query against the graph."""
        return query(cypher, parameters)
    
    def write_graph(self, cypher: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a write query against the graph."""
        return write(cypher, parameters)
    
    def log_activity(
        self,
        message: str,
        data: Optional[Dict[str, Any]] = None,
        linked_node_id: Optional[str] = None,
        linked_node_type: Optional[str] = None,
    ):
        """Log an activity event to the graph."""
        event_id = f"evt-{uuid.uuid4().hex[:12]}"
        
        cypher = """
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
        RETURN ae.id
        """
        
        self.write_graph(cypher, {
            "id": event_id,
            "agent_name": self.name,
            "event_type": "agent_run",
            "message": message,
            "details": data or {},
            "linked_node_id": linked_node_id,
            "linked_node_type": linked_node_type,
        })
        
        logger.info(f"Activity logged: {message}")
