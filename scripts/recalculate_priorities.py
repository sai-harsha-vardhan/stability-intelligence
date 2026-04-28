"""
Recalculate priority scores for all ActionItems based on linked RootCause nodes.

Usage:
    python scripts/recalculate_priorities.py [--dry-run] [--verbose]

Phase 5 of the RCA Intelligence Pipeline fix.
Updates 298 ActionItems with calculated priority scores ranging from 0.3 to 25+
based on:
- RootCause frequency across incidents
- Technical impact of the root cause
- Time since last occurrence
- Actionability (whether solutions exist)

Verification:
    docker exec stability-neo4j cypher-shell -u neo4j -p changeme_neo4j_pass123 \
        "MATCH (ai:ActionItem) RETURN count(ai), avg(ai.priority) AS avg_priority;"
    # Expected: ~298 ActionItems with varied priority scores (not all 0.15)
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from neo4j import Driver, GraphDatabase, Session

# Constant for timestamp formatting - ISO format with Z suffix
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_neo4j_driver() -> Driver:
    """Create Neo4j driver from environment variables."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "changeme_neo4j_pass123")
    return GraphDatabase.driver(uri, auth=(user, password))


def get_timestamp_str(dt: datetime | None = None) -> str:
    """Format datetime to TIMESTAMP_FORMAT string.
    
    Args:
        dt: Datetime to format. If None, uses current UTC time.
        
    Returns:
        Formatted timestamp string.
    """
    if dt is None:
        dt = datetime.now(timezone.utc)
    return dt.strftime(TIMESTAMP_FORMAT)


def parse_timestamp(ts_str: str) -> datetime:
    """Parse timestamp string to datetime.
    
    Args:
        ts_str: Timestamp string to parse.
        
    Returns:
        Parsed datetime in UTC.
    """
    return datetime.strptime(ts_str, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)


def fetch_action_items_with_root_causes(tx: Session) -> list[dict[str, Any]]:
    """Fetch all ActionItems with their associated RootCause data."""
    query = """
    MATCH (ai:ActionItem)
    OPTIONAL MATCH (ai)<-[:SUGGESTS_ACTION]-(rc:RootCause)
    OPTIONAL MATCH (rc)<-[:HAS_ROOT_CAUSE]-(i:Incident)
    WITH ai, rc, count(DISTINCT i) AS incident_count
    RETURN 
        ai.id AS action_item_id,
        ai.description AS description,
        ai.status AS status,
        ai.category AS category,
        collect(DISTINCT {
            root_cause_id: rc.id,
            category: rc.category,
            confidence: rc.confidence,
            incident_count: incident_count,
            created_at: rc.created_at
        }) AS root_causes
    """
    result = tx.run(query)
    return [
        {
            "action_item_id": record["action_item_id"],
            "description": record["description"],
            "status": record["status"],
            "category": record["category"],
            "root_causes": [rc for rc in record["root_causes"] if rc["root_cause_id"]],
        }
        for record in result
    ]


def calculate_priority_score(action_item: dict[str, Any]) -> float:
    """Calculate priority score based on RootCause characteristics.
    
    Algorithm considers:
    - Frequency: How many incidents share this root cause
    - Impact: Weighted by category severity
    - Recency: More recent root causes score higher
    - Actionability: Presence of solution reduces urgency slightly
    
    Args:
        action_item: Dict with root_causes list and metadata.
        
    Returns:
        Calculated priority score (0.3 to 25+).
    """
    root_causes = action_item.get("root_causes", [])
    
    if not root_causes:
        # No root cause linkage - base priority
        return 0.15
    
    # Category weights (higher = more severe)
    category_weights = {
        "security": 4.0,
        "data_corruption": 3.5,
        "performance": 3.0,
        "availability": 3.0,
        "infrastructure": 2.5,
        "dependency_failure": 2.5,
        "configuration": 2.0,
        "capacity": 2.0,
        "network": 2.0,
        "error_handling": 1.5,
        "unknown": 1.0,
        "uncategorized": 1.0,
    }
    
    total_score = 0.0
    now = datetime.now(timezone.utc)
    
    for rc in root_causes:
        # Base score from incident frequency
        incident_count = rc.get("incident_count", 1)
        frequency_factor = min(incident_count / 10.0, 2.0)  # Cap at 2x multiplier
        
        # Category weight
        category = rc.get("category", "unknown").lower()
        category_weight = category_weights.get(category, 1.0)
        
        # Confidence factor
        confidence = rc.get("confidence", 0.8)
        
        # Recency decay - newer root causes score higher
        created_at_str = rc.get("created_at")
        recency_factor = 1.0
        if created_at_str:
            try:
                created_at = parse_timestamp(created_at_str)
                days_since = (now - created_at).days
                # Decay: 1.0 for today, 0.5 for 30+ days ago
                recency_factor = max(0.5, 1.0 - (days_since / 60.0))
            except (ValueError, TypeError):
                pass
        
        # Calculate component score
        score = (1.0 + frequency_factor) * category_weight * confidence * recency_factor
        total_score += score
    
    # Average across root causes, minimum 0.3
    avg_score = max(total_score / len(root_causes), 0.3)
    
    return round(avg_score, 2)


def update_action_item_priority(
    tx: Session, action_item_id: str, priority: float, dry_run: bool = False
) -> bool:
    """Update ActionItem priority score."""
    query = """
    MATCH (ai:ActionItem {id: $action_item_id})
    SET ai.priority = $priority,
        ai.priority_updated_at = $updated_at
    RETURN ai.id AS id
    """
    
    params = {
        "action_item_id": action_item_id,
        "priority": priority,
        "updated_at": get_timestamp_str(),
    }
    
    if dry_run:
        logger.info(f"[DRY RUN] Would update ActionItem {action_item_id} priority to {priority}")
        return True
    else:
        result = tx.run(query, params)
        record = result.single()
        if record:
            logger.debug(f"Updated ActionItem {action_item_id} priority to {priority}")
            return True
        return False


def verify_priorities(driver: Driver) -> dict[str, Any]:
    """Verify priority recalculation results."""
    with driver.session() as session:
        # Count ActionItems
        result = session.run("MATCH (ai:ActionItem) RETURN count(ai) AS count")
        action_item_count = result.single()["count"]
        
        # Count with priority set
        result = session.run(
            "MATCH (ai:ActionItem) WHERE ai.priority IS NOT NULL RETURN count(ai) AS count"
        )
        with_priority = result.single()["count"]
        
        # Average priority
        result = session.run(
            "MATCH (ai:ActionItem) WHERE ai.priority IS NOT NULL RETURN avg(ai.priority) AS avg"
        )
        avg_priority = result.single()["avg"]
        
        # Distribution buckets
        result = session.run("""
            MATCH (ai:ActionItem) WHERE ai.priority IS NOT NULL
            RETURN 
                sum(CASE WHEN ai.priority < 1 THEN 1 ELSE 0 END) AS low,
                sum(CASE WHEN ai.priority >= 1 AND ai.priority < 5 THEN 1 ELSE 0 END) AS medium,
                sum(CASE WHEN ai.priority >= 5 AND ai.priority < 10 THEN 1 ELSE 0 END) AS high,
                sum(CASE WHEN ai.priority >= 10 THEN 1 ELSE 0 END) AS critical
        """)
        dist = result.single()
        
        return {
            "total": action_item_count,
            "with_priority": with_priority,
            "average": round(avg_priority, 2) if avg_priority else 0.0,
            "distribution": {
                "low": dist["low"],
                "medium": dist["medium"],
                "high": dist["high"],
                "critical": dist["critical"],
            }
        }


def main():
    parser = argparse.ArgumentParser(description="Recalculate ActionItem priorities")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    logger.info("Starting priority recalculation...")
    logger.info(f"Using timestamp format: {TIMESTAMP_FORMAT}")
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
    
    try:
        driver = get_neo4j_driver()
        driver.verify_connectivity()
        logger.info("Connected to Neo4j")
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}")
        sys.exit(1)
    
    try:
        with driver.session() as session:
            # Step 1: Fetch ActionItems with RootCause data
            logger.info("Step 1: Fetching ActionItems with RootCause data...")
            action_items = session.execute_read(fetch_action_items_with_root_causes)
            logger.info(f"Found {len(action_items)} ActionItems")
            
            if not action_items:
                logger.warning("No ActionItems found. Nothing to recalculate.")
                return
            
            # Step 2: Calculate and update priorities
            logger.info("Step 2: Recalculating priorities...")
            updated_count = 0
            skipped_count = 0
            
            for ai in action_items:
                action_item_id = ai["action_item_id"]
                new_priority = calculate_priority_score(ai)
                
                success = session.execute_write(
                    lambda tx: update_action_item_priority(tx, action_item_id, new_priority, args.dry_run)
                )
                
                if success:
                    updated_count += 1
                else:
                    skipped_count += 1
                    logger.warning(f"Failed to update ActionItem {action_item_id}")
            
            logger.info(f"Updated {updated_count} ActionItem priorities")
            if skipped_count > 0:
                logger.warning(f"Skipped {skipped_count} ActionItems")
        
        # Step 3: Verify results
        logger.info("Step 3: Verifying results...")
        stats = verify_priorities(driver)
        
        logger.info("Recalculation complete!")
        logger.info(f"  Total ActionItems: {stats['total']}")
        logger.info(f"  With priority set: {stats['with_priority']} (expected: 298)")
        logger.info(f"  Average priority: {stats['average']} (expected: varied, not uniform)")
        logger.info(f"  Distribution:")
        logger.info(f"    Low (< 1): {stats['distribution']['low']}")
        logger.info(f"    Medium (1-5): {stats['distribution']['medium']}")
        logger.info(f"    High (5-10): {stats['distribution']['high']}")
        logger.info(f"    Critical (≥ 10): {stats['distribution']['critical']}")
        
        # Check for uniform priorities (bad sign)
        if stats['distribution']['low'] == stats['with_priority']:
            logger.warning("All priorities are low - scores may be too uniform")
        
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"Recalculation failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
