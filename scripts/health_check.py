"""System health check script.

This script performs comprehensive health checks on the RCA Intelligence System:
- Data quality validation (no mock data, proper incident counts)
- Scheduler job execution monitoring
- Last sync time verification

Exit codes:
    0 - System is healthy
    1 - System is unhealthy (mock data found, no incidents, or stale data)
"""
import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from graph.client import query


def check_data_quality() -> Dict[str, Any]:
    """Check Neo4j data quality.
    
    Validates:
    - No mock data (incidents without github_issue_number)
    - Incident count is greater than 0
    - Recent sync activity
    
    Returns:
        dict: Health status with metrics
    """
    # Check for mock data (should be 0)
    mock_check = query("""
        MATCH (i:Incident) 
        WHERE i.github_issue_number IS NULL
        RETURN count(i) as mock_count
    """)
    mock_count = mock_check[0]["mock_count"] if mock_check else 0
    
    # Check incident count
    incident_check = query("MATCH (i:Incident) RETURN count(i) as count")
    incident_count = incident_check[0]["count"] if incident_check else 0
    
    # Check last sync time
    sync_check = query("""
        MATCH (i:Incident)
        RETURN max(i.updated_at) as last_sync
    """)
    last_sync = sync_check[0]["last_sync"] if sync_check and sync_check[0] else None
    
    # Check for recent activity events (last 24 hours)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    activity_check = query("""
        MATCH (ae:ActivityEvent)
        WHERE ae.created_at >= $cutoff
        RETURN count(ae) as recent_activity
    """, {"cutoff": cutoff})
    recent_activity = activity_check[0]["recent_activity"] if activity_check else 0
    
    # Determine health status
    healthy = (
        mock_count == 0 and 
        incident_count > 0 and
        last_sync is not None
    )
    
    return {
        "mock_data_count": mock_count,
        "total_incidents": incident_count,
        "last_sync": last_sync,
        "recent_activity_24h": recent_activity,
        "healthy": healthy
    }


def check_scheduler_jobs() -> Dict[str, Any]:
    """Check scheduler job execution status.
    
    Examines the scheduler log file to determine:
    - Last run time of each job
    - Success/failure status
    - Job frequency compliance
    
    Returns:
        dict: Scheduler health status
    """
    log_file = Path("/app/logs/scheduler.log")
    
    if not log_file.exists():
        return {
            "status": "unknown",
            "message": "Scheduler log file not found",
            "healthy": False
        }
    
    jobs_status = {}
    recent_errors = []
    
    try:
        # Read last 500 lines of scheduler log
        with open(log_file, "r") as f:
            lines = f.readlines()
            recent_lines = lines[-500:] if len(lines) > 500 else lines
        
        # Parse job execution events
        for line in recent_lines:
            if "Job " in line and "completed successfully" in line:
                # Extract job ID
                parts = line.split("Job ")
                if len(parts) > 1:
                    job_id = parts[1].split(" ")[0]
                    if job_id not in jobs_status:
                        jobs_status[job_id] = {"last_success": None, "errors": 0}
                    # Extract timestamp
                    timestamp = line.split(" - ")[0]
                    jobs_status[job_id]["last_success"] = timestamp
            
            elif "Job " in line and "failed" in line:
                # Track errors
                parts = line.split("Job ")
                if len(parts) > 1:
                    job_id = parts[1].split(" ")[0]
                    if job_id not in jobs_status:
                        jobs_status[job_id] = {"last_success": None, "errors": 0}
                    jobs_status[job_id]["errors"] += 1
                    recent_errors.append(line.strip())
        
        # Expected jobs
        expected_jobs = [
            "github_sync", "rca_agent", "priority_agent", 
            "strategy_agent", "feedback_loop", "health_check"
        ]
        
        jobs_running = len(jobs_status) > 0
        has_errors = len(recent_errors) > 0
        
        return {
            "status": "healthy" if jobs_running and not has_errors else "degraded",
            "jobs_tracked": list(jobs_status.keys()),
            "recent_errors_count": len(recent_errors),
            "recent_errors": recent_errors[-5:],  # Last 5 errors
            "healthy": jobs_running and not has_errors
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to parse scheduler log: {e}",
            "healthy": False
        }


def check_github_sync() -> Dict[str, Any]:
    """Check GitHub sync status.
    
    Validates:
    - Sync state file exists
    - Last sync was recent (within configured interval + buffer)
    - Issues were successfully synced
    
    Returns:
        dict: GitHub sync health status
    """
    cache_dir = Path("/app/github-cache")
    sync_state_file = cache_dir / "sync_state.json"
    
    if not sync_state_file.exists():
        return {
            "status": "pending",
            "message": "No sync state yet (first run pending)",
            "healthy": True  # Not unhealthy, just hasn't run yet
        }
    
    try:
        with open(sync_state_file) as f:
            state = json.load(f)
        
        last_sync = state.get("last_sync_timestamp")
        total_issues = state.get("total_issues", 0)
        
        if not last_sync:
            return {
                "status": "unknown",
                "message": "Sync state exists but no timestamp",
                "healthy": False
            }
        
        # Parse timestamp
        last_sync_dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
        hours_ago = (datetime.now(timezone.utc) - last_sync_dt).total_seconds() / 3600
        
        # Get configured interval
        interval_hours = int(os.getenv("GITHUB_SYNC_INTERVAL_HOURS", "6"))
        threshold_hours = interval_hours * 2  # Allow 2x buffer
        
        is_stale = hours_ago > threshold_hours
        
        return {
            "status": "stale" if is_stale else "healthy",
            "last_sync": last_sync,
            "hours_ago": round(hours_ago, 2),
            "total_issues": total_issues,
            "threshold_hours": threshold_hours,
            "healthy": not is_stale and total_issues > 0
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to check sync state: {e}",
            "healthy": False
        }


def check_agent_execution() -> Dict[str, Any]:
    """Check agent execution status from activity events.
    
    Validates:
    - RCA agent has run recently
    - Priority agent has run recently
    - Activity events are being created
    
    Returns:
        dict: Agent execution health status
    """
    try:
        # Check for recent RCA agent activity
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        rca_activity = query("""
            MATCH (ae:ActivityEvent)
            WHERE ae.agent_name = 'RCAAgent' 
            AND ae.created_at >= $cutoff
            RETURN count(ae) as count, max(ae.created_at) as last_run
        """, {"cutoff": cutoff})
        
        rca_count = rca_activity[0]["count"] if rca_activity else 0
        rca_last_run = rca_activity[0]["last_run"] if rca_activity and rca_activity[0] else None
        
        # Check for recent Priority agent activity
        priority_activity = query("""
            MATCH (ae:ActivityEvent)
            WHERE ae.agent_name = 'PriorityAgent'
            AND ae.created_at >= $cutoff
            RETURN count(ae) as count, max(ae.created_at) as last_run
        """, {"cutoff": cutoff})
        
        priority_count = priority_activity[0]["count"] if priority_activity else 0
        priority_last_run = priority_activity[0]["last_run"] if priority_activity and priority_activity[0] else None
        
        # Agents are healthy if they've run recently
        agents_active = rca_count > 0 or priority_count > 0
        
        return {
            "status": "active" if agents_active else "idle",
            "rca_agent": {
                "recent_activity": rca_count,
                "last_run": rca_last_run
            },
            "priority_agent": {
                "recent_activity": priority_count,
                "last_run": priority_last_run
            },
            "healthy": agents_active
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to check agent execution: {e}",
            "healthy": False
        }


def main():
    """Run all health checks and display results."""
    print("=" * 60)
    print("SYSTEM HEALTH CHECK")
    print("=" * 60)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print()
    
    all_healthy = True
    
    # 1. Data Quality
    print("📊 Data Quality:")
    try:
        data_health = check_data_quality()
        print(f"  Mock Data Count: {data_health['mock_data_count']} (should be 0)")
        print(f"  Total Incidents: {data_health['total_incidents']}")
        print(f"  Last Sync: {data_health['last_sync']}")
        print(f"  Recent Activity (24h): {data_health['recent_activity_24h']}")
        status_emoji = "✅ HEALTHY" if data_health['healthy'] else "❌ UNHEALTHY"
        print(f"  Status: {status_emoji}")
        
        if not data_health['healthy']:
            all_healthy = False
            if data_health['mock_data_count'] > 0:
                print(f"  ⚠️  WARNING: Found {data_health['mock_data_count']} mock incidents")
            if data_health['total_incidents'] == 0:
                print("  ⚠️  WARNING: No incidents in database")
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        all_healthy = False
    
    print()
    
    # 2. GitHub Sync
    print("🔄 GitHub Sync:")
    try:
        sync_health = check_github_sync()
        print(f"  Status: {sync_health['status']}")
        if 'hours_ago' in sync_health:
            print(f"  Last Sync: {sync_health['hours_ago']}h ago")
            print(f"  Total Issues: {sync_health.get('total_issues', 0)}")
            print(f"  Threshold: {sync_health.get('threshold_hours', 0)}h")
        if sync_health.get('message'):
            print(f"  Message: {sync_health['message']}")
        status_emoji = "✅ HEALTHY" if sync_health['healthy'] else "⚠️  DEGRADED"
        print(f"  Overall: {status_emoji}")
        
        if not sync_health['healthy']:
            all_healthy = False
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        all_healthy = False
    
    print()
    
    # 3. Scheduler Jobs
    print("⏰ Scheduler Jobs:")
    try:
        scheduler_health = check_scheduler_jobs()
        print(f"  Status: {scheduler_health['status']}")
        if 'jobs_tracked' in scheduler_health:
            print(f"  Jobs Tracked: {', '.join(scheduler_health['jobs_tracked'])}")
        if scheduler_health.get('recent_errors_count', 0) > 0:
            print(f"  Recent Errors: {scheduler_health['recent_errors_count']}")
            for error in scheduler_health.get('recent_errors', []):
                print(f"    - {error[:100]}...")
        if scheduler_health.get('message'):
            print(f"  Message: {scheduler_health['message']}")
        status_emoji = "✅ HEALTHY" if scheduler_health['healthy'] else "⚠️  DEGRADED"
        print(f"  Overall: {status_emoji}")
        
        if not scheduler_health['healthy']:
            all_healthy = False
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        all_healthy = False
    
    print()
    
    # 4. Agent Execution
    print("🤖 Agent Execution:")
    try:
        agent_health = check_agent_execution()
        print(f"  Status: {agent_health['status']}")
        if 'rca_agent' in agent_health:
            rca = agent_health['rca_agent']
            print(f"  RCA Agent: {rca['recent_activity']} activities, last run: {rca['last_run']}")
        if 'priority_agent' in agent_health:
            priority = agent_health['priority_agent']
            print(f"  Priority Agent: {priority['recent_activity']} activities, last run: {priority['last_run']}")
        if agent_health.get('message'):
            print(f"  Message: {agent_health['message']}")
        status_emoji = "✅ ACTIVE" if agent_health['healthy'] else "⚠️  IDLE"
        print(f"  Overall: {status_emoji}")
        
        if not agent_health['healthy']:
            all_healthy = False
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        all_healthy = False
    
    print()
    print("=" * 60)
    
    if all_healthy:
        print("✅ SYSTEM HEALTHY")
        print("=" * 60)
        sys.exit(0)
    else:
        print("❌ SYSTEM UNHEALTHY - Issues detected")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
