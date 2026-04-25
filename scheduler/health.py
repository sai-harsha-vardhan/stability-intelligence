"""Health monitoring for Stability Intelligence System components."""
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

import requests
import httpx

from graph.client import get_client

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Health status for a component."""
    name: str
    status: str  # "healthy", "degraded", "unhealthy"
    message: str
    last_check: datetime = field(default_factory=datetime.utcnow)
    details: Dict[str, Any] = field(default_factory=dict)


class HealthMonitor:
    """Monitor health of all system components."""
    
    def __init__(
        self,
        neo4j_uri: Optional[str] = None,
        litellm_url: Optional[str] = None,
        slack_webhook_url: Optional[str] = None,
    ):
        self.neo4j_uri = neo4j_uri or os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        self.litellm_url = litellm_url or os.getenv("LITELLM_BASE_URL", "http://litellm:4000")
        self.slack_webhook_url = slack_webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.graph_client = get_client()
    
    def check_all(self) -> List[HealthStatus]:
        """Run all health checks.
        
        Returns a list of status objects for each component.
        """
        results = []
        
        # Neo4j
        try:
            results.append(self.check_neo4j())
        except Exception as e:
            results.append(HealthStatus(
                name="neo4j",
                status="unhealthy",
                message=f"Check failed: {e}",
            ))
        
        # LiteLLM
        try:
            results.append(self.check_litellm())
        except Exception as e:
            results.append(HealthStatus(
                name="litellm",
                status="unhealthy",
                message=f"Check failed: {e}",
            ))
        
        # Graph staleness
        try:
            results.append(self.check_graph_staleness())
        except Exception as e:
            results.append(HealthStatus(
                name="graph_staleness",
                status="unhealthy",
                message=f"Check failed: {e}",
            ))
        
        # Check for alerts
        unhealthy = [r for r in results if r.status != "healthy"]
        if unhealthy:
            alert_msg = "Health check failures:\n" + "\n".join(
                f"  - {r.name}: {r.message}" for r in unhealthy
            )
            self.send_alert(alert_msg, level="warning")
        
        return results
    
    def check_neo4j(self) -> HealthStatus:
        """Check Neo4j connectivity."""
        try:
            result = self.graph_client.health_check()
            
            if result["status"] == "healthy":
                return HealthStatus(
                    name="neo4j",
                    status="healthy",
                    message="Connected successfully",
                    details={
                        "components": result.get("components", []),
                        "uri": self.neo4j_uri,
                    },
                )
            else:
                return HealthStatus(
                    name="neo4j",
                    status="unhealthy",
                    message=result.get("error", "Unknown error"),
                )
        except Exception as e:
            return HealthStatus(
                name="neo4j",
                status="unhealthy",
                message=str(e),
            )
    
    def check_litellm(self) -> HealthStatus:
        """Check LiteLLM health endpoint."""
        try:
            url = f"{self.litellm_url}/health"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return HealthStatus(
                    name="litellm",
                    status="healthy",
                    message="LiteLLM responding",
                    details={
                        "status_code": response.status_code,
                        "models_available": data.get("model_list", []),
                    },
                )
            else:
                return HealthStatus(
                    name="litellm",
                    status="degraded",
                    message=f"Health check returned {response.status_code}",
                    details={"response": response.text[:200]},
                )
        except requests.exceptions.Timeout:
            return HealthStatus(
                name="litellm",
                status="unhealthy",
                message="Connection timed out",
            )
        except requests.exceptions.ConnectionError as e:
            return HealthStatus(
                name="litellm",
                status="unhealthy",
                message=f"Connection refused: {e}",
            )
        except Exception as e:
            return HealthStatus(
                name="litellm",
                status="unhealthy",
                message=f"Unexpected error: {e}",
            )
    
    def check_graph_staleness(self) -> HealthStatus:
        """Check if the graph has had recent activity."""
        try:
            # Check for ActivityEvent in the last 8 hours
            cutoff = datetime.utcnow() - timedelta(hours=8)
            
            query = """
            MATCH (ae:ActivityEvent)
            WHERE ae.created_at >= $cutoff
            RETURN count(ae) AS recent_events,
                   max(ae.created_at) AS last_event
            """
            result = self.graph_client.read(query, {"cutoff": cutoff.isoformat()})
            
            if result and result[0].get("recent_events", 0) > 0:
                return HealthStatus(
                    name="graph_staleness",
                    status="healthy",
                    message=f"{result[0]['recent_events']} events in last 8 hours",
                    details={
                        "recent_events": result[0]["recent_events"],
                        "last_event": str(result[0]["last_event"]),
                    },
                )
            else:
                return HealthStatus(
                    name="graph_staleness",
                    status="degraded",
                    message="No activity events in last 8 hours",
                    details={"hours_since_last_event": 8},
                )
        except Exception as e:
            return HealthStatus(
                name="graph_staleness",
                status="unhealthy",
                message=f"Failed to check staleness: {e}",
            )
    
    def check_github_sync(self, cache_dir: str = "/app/github-cache") -> HealthStatus:
        """Check if GitHub sync has run recently.
        
        This is an optional check - if no sync state exists, it's not an error.
        """
        import json
        from pathlib import Path
        
        try:
            sync_state_file = Path(cache_dir) / "sync_state.json"
            
            if not sync_state_file.exists():
                return HealthStatus(
                    name="github_sync",
                    status="healthy",
                    message="No sync state yet (first run pending)",
                )
            
            with open(sync_state_file) as f:
                state = json.load(f)
            
            last_sync = state.get("last_sync_timestamp")
            if last_sync:
                last_sync_dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
                hours_ago = (datetime.utcnow() - last_sync_dt.replace(tzinfo=None)).total_seconds() / 3600
                
                interval_hours = int(os.getenv("GITHUB_SYNC_INTERVAL_HOURS", "6"))
                
                if hours_ago < interval_hours * 2:  # Allow some buffer
                    return HealthStatus(
                        name="github_sync",
                        status="healthy",
                        message=f"Last sync {hours_ago:.1f}h ago",
                        details={
                            "last_sync": last_sync,
                            "issues_synced": state.get("total_issues", 0),
                        },
                    )
                else:
                    return HealthStatus(
                        name="github_sync",
                        status="degraded",
                        message=f"Sync stale: {hours_ago:.1f}h ago (threshold: {interval_hours * 2}h)",
                        details={"last_sync": last_sync},
                    )
            
            return HealthStatus(
                name="github_sync",
                status="degraded",
                message="Sync state exists but no timestamp",
            )
            
        except Exception as e:
            return HealthStatus(
                name="github_sync",
                status="unhealthy",
                message=f"Failed to check sync state: {e}",
            )
    
    def send_alert(self, message: str, level: str = "info", details: Optional[Dict[str, Any]] = None):
        """Send an alert via Slack webhook.
        
        Args:
            message: The alert message
            level: One of "info", "warning", "error", "critical"
            details: Additional context for the alert
        """
        if not self.slack_webhook_url:
            logger.info(f"Would send alert ({level}): {message}")
            return
        
        emoji = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨",
        }.get(level, "📢")
        
        payload = {
            "text": f"{emoji} Stability Intelligence Alert [{level.upper()}]\n\n{message}",
            "username": "StabilityBot",
        }
        
        if details:
            payload["attachments"] = [{
                "color": "danger" if level in ("error", "critical") else "warning" if level == "warning" else "good",
                "fields": [
                    {"title": k, "value": str(v), "short": True}
                    for k, v in details.items()
                ],
            }]
        
        try:
            response = requests.post(
                self.slack_webhook_url,
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
            logger.info(f"Alert sent ({level})")
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")


def check_all() -> List[HealthStatus]:
    """Convenience function to run all health checks."""
    monitor = HealthMonitor()
    return monitor.check_all()


def format_health_report(statuses: List[HealthStatus]) -> str:
    """Format health statuses for display/logging."""
    lines = ["System Health Report", "=" * 40]
    
    for status in statuses:
        emoji = {
            "healthy": "✅",
            "degraded": "⚠️",
            "unhealthy": "❌",
        }.get(status.status, "❓")
        
        lines.append(f"{emoji} {status.name}: {status.status}")
        lines.append(f"   {status.message}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    statuses = check_all()
    print(format_health_report(statuses))
    
    # Exit with error if any unhealthy
    unhealthy = [s for s in statuses if s.status == "unhealthy"]
    exit(1 if unhealthy else 0)
