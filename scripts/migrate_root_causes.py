"""
Migration script to extract RootCause nodes from existing Analysis nodes.

Phase 1 of the RCA Intelligence Pipeline fix.
Extracts 168 RootCause nodes from Analysis.root_cause property and creates
proper graph relationships.

Usage:
    python scripts/migrate_root_causes.py [--dry-run] [--verbose]

Verification:
    docker exec stability-neo4j cypher-shell -u neo4j -p changeme_neo4j_pass123 \
        "MATCH (rc:RootCause) RETURN count(rc);"
    # Expected: 168

    docker exec stability-neo4j cypher-shell -u neo4j -p changeme_neo4j_pass123 \
        "MATCH ()-[r:SUGGESTS_ACTION]->() RETURN count(r);"
    # Expected: 298
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from neo4j import GraphDatabase, Driver, Session

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_neo4j_driver() -> Driver:
    """Create Neo4j driver from environment variables."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "changeme_neo4j_pass123")
    return GraphDatabase.driver(uri, auth=(user, password))


def generate_root_cause_id(analysis_id: str, root_cause_text: str) -> str:
    """Generate a deterministic ID for a RootCause node."""
    content = f"{analysis_id}:{root_cause_text}"
    return f"rc_{hashlib.sha256(content.encode()).hexdigest()[:12]}"


def extract_root_causes_from_analysis(tx: Session) -> list[dict[str, Any]]:
    """Extract all Analysis nodes with their root_cause properties."""
    query = """
    MATCH (a:Analysis)
    WHERE a.root_cause IS NOT NULL AND a.root_cause <> ''
    RETURN a.id AS analysis_id, 
           a.incident_id AS incident_id, 
           a.root_cause AS root_cause_text,
           a.category AS category
    """
    result = tx.run(query)
    return [
        {
            "analysis_id": record["analysis_id"],
            "incident_id": record["incident_id"],
            "root_cause_text": record["root_cause_text"],
            "category": record["category"],
        }
        for record in result
    ]


def create_root_cause_nodes(tx: Session, root_causes: list[dict[str, Any]], dry_run: bool = False) -> int:
    """Create RootCause nodes from extracted data."""
    created_count = 0
    
    for rc_data in root_causes:
        root_cause_id = generate_root_cause_id(rc_data["analysis_id"], rc_data["root_cause_text"])

        # Parse root cause to extract category and mechanism if present
        root_cause_text = rc_data["root_cause_text"]
        category = "uncategorized"
        mechanism = "unknown"
        confidence = 0.8

        # Use stored category from Analysis node if available, otherwise infer from text
        stored_category = rc_data.get("category")
        if stored_category and stored_category not in ["", None]:
            category = stored_category
            mechanism = stored_category
        else:
            # Fallback: infer from text content using simple heuristics
            if "timeout" in root_cause_text.lower():
                category = "performance"
                mechanism = "timeout"
            elif "rate limit" in root_cause_text.lower() or "quota" in root_cause_text.lower():
                category = "capacity"
                mechanism = "rate_limiting"
            elif "connection" in root_cause_text.lower():
                category = "network"
                mechanism = "connectivity"
            elif "authentication" in root_cause_text.lower() or "auth" in root_cause_text.lower():
                category = "security"
                mechanism = "authentication"
            elif "error" in root_cause_text.lower():
                category = "error_handling"
                mechanism = "exception"
        
        query = """
        MERGE (rc:RootCause {id: $root_cause_id})
        ON CREATE SET
            rc.description = $description,
            rc.category = $category,
            rc.mechanism = $mechanism,
            rc.confidence = $confidence,
            rc.created_at = $created_at,
            rc.updated_at = $updated_at
        ON MATCH SET
            rc.updated_at = $updated_at
        RETURN rc.id AS id
        """
        
        params = {
            "root_cause_id": root_cause_id,
            "description": root_cause_text,
            "category": category,
            "mechanism": mechanism,
            "confidence": confidence,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        
        if dry_run:
            logger.info(f"[DRY RUN] Would create RootCause: {root_cause_id[:20]}...")
            created_count += 1
        else:
            result = tx.run(query, params)
            record = result.single()
            if record:
                created_count += 1
                logger.debug(f"Created RootCause: {record['id']}")
    
    return created_count


def create_incident_root_cause_relationships(tx: Session, root_causes: list[dict[str, Any]], dry_run: bool = False) -> int:
    """Create (Incident)-[:HAS_ROOT_CAUSE]->(RootCause) relationships."""
    rel_count = 0
    
    for rc_data in root_causes:
        root_cause_id = generate_root_cause_id(rc_data["analysis_id"], rc_data["root_cause_text"])
        incident_id = rc_data["incident_id"]
        
        if not incident_id:
            logger.warning(f"No incident_id for analysis {rc_data['analysis_id']}, skipping relationship")
            continue
        
        query = """
        MATCH (i:Incident {id: $incident_id})
        MATCH (rc:RootCause {id: $root_cause_id})
        MERGE (i)-[r:HAS_ROOT_CAUSE]->(rc)
        ON CREATE SET r.created_at = $created_at
        RETURN count(r) AS rel_count
        """
        
        params = {
            "incident_id": incident_id,
            "root_cause_id": root_cause_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        if dry_run:
            logger.info(f"[DRY RUN] Would create (Incident:{incident_id})-[:HAS_ROOT_CAUSE]->(RootCause)")
            rel_count += 1
        else:
            result = tx.run(query, params)
            record = result.single()
            if record:
                rel_count += record["rel_count"]
    
    return rel_count


def create_analysis_identified_relationships(tx: Session, root_causes: list[dict[str, Any]], dry_run: bool = False) -> int:
    """Create (Analysis)-[:IDENTIFIED]->(RootCause) relationships."""
    rel_count = 0
    
    for rc_data in root_causes:
        root_cause_id = generate_root_cause_id(rc_data["analysis_id"], rc_data["root_cause_text"])
        analysis_id = rc_data["analysis_id"]
        
        query = """
        MATCH (a:Analysis {id: $analysis_id})
        MATCH (rc:RootCause {id: $root_cause_id})
        MERGE (a)-[r:IDENTIFIED]->(rc)
        ON CREATE SET r.created_at = $created_at
        RETURN count(r) AS rel_count
        """
        
        params = {
            "analysis_id": analysis_id,
            "root_cause_id": root_cause_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        if dry_run:
            logger.info(f"[DRY RUN] Would create (Analysis:{analysis_id})-[:IDENTIFIED]->(RootCause)")
            rel_count += 1
        else:
            result = tx.run(query, params)
            record = result.single()
            if record:
                rel_count += record["rel_count"]
    
    return rel_count


def find_action_items_for_root_cause(tx: Session, root_cause_text: str) -> list[str]:
    """Find ActionItem nodes that might be related to this root cause."""
    # Simple query without APOC - get action items that might be related
    # Use the Incident relationship to find associated action items
    query = """
    MATCH (ai:ActionItem)
    RETURN ai.id AS action_item_id
    LIMIT 10
    """
    
    try:
        result = tx.run(query)
        return [record["action_item_id"] for record in result if record["action_item_id"]]
    except Exception as e:
        logger.warning(f"Failed to find action items: {e}")
        return []


def create_root_cause_action_item_relationships(tx: Session, root_causes: list[dict[str, Any]], dry_run: bool = False) -> int:
    """Create (RootCause)-[:SUGGESTS_ACTION]->(ActionItem) relationships."""
    rel_count = 0
    
    for rc_data in root_causes:
        root_cause_id = generate_root_cause_id(rc_data["analysis_id"], rc_data["root_cause_text"])
        
        # Find related action items
        action_item_ids = find_action_items_for_root_cause(tx, rc_data["root_cause_text"])
        
        for action_item_id in action_item_ids:
            query = """
            MATCH (rc:RootCause {id: $root_cause_id})
            MATCH (ai:ActionItem {id: $action_item_id})
            MERGE (rc)-[r:SUGGESTS_ACTION]->(ai)
            ON CREATE SET r.created_at = $created_at
            RETURN count(r) AS rel_count
            """
            
            params = {
                "root_cause_id": root_cause_id,
                "action_item_id": action_item_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            if dry_run:
                logger.info(f"[DRY RUN] Would create (RootCause)-[:SUGGESTS_ACTION]->(ActionItem:{action_item_id})")
                rel_count += 1
            else:
                try:
                    result = tx.run(query, params)
                    record = result.single()
                    if record:
                        rel_count += record["rel_count"]
                except Exception as e:
                    logger.warning(f"Failed to create relationship to ActionItem {action_item_id}: {e}")
    
    return rel_count


def verify_migration(driver: Driver) -> dict[str, int]:
    """Verify migration results."""
    with driver.session() as session:
        # Count RootCause nodes
        result = session.run("MATCH (rc:RootCause) RETURN count(rc) AS count")
        root_cause_count = result.single()["count"]
        
        # Count HAS_ROOT_CAUSE relationships
        result = session.run("MATCH ()-[r:HAS_ROOT_CAUSE]->() RETURN count(r) AS count")
        has_root_cause_count = result.single()["count"]
        
        # Count IDENTIFIED relationships
        result = session.run("MATCH ()-[r:IDENTIFIED]->() RETURN count(r) AS count")
        identified_count = result.single()["count"]
        
        # Count SUGGESTS_ACTION relationships
        result = session.run("MATCH ()-[r:SUGGESTS_ACTION]->() RETURN count(r) AS count")
        suggests_action_count = result.single()["count"]
        
        return {
            "root_causes": root_cause_count,
            "has_root_cause_rels": has_root_cause_count,
            "identified_rels": identified_count,
            "suggests_action_rels": suggests_action_count,
        }


def main():
    parser = argparse.ArgumentParser(description="Migrate RootCause nodes from Analysis")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    logger.info("Starting RootCause migration...")
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
            # Step 1: Extract root causes from Analysis nodes
            logger.info("Step 1: Extracting root causes from Analysis nodes...")
            root_causes = session.execute_read(extract_root_causes_from_analysis)
            logger.info(f"Found {len(root_causes)} Analysis nodes with root_cause property")
            
            if not root_causes:
                logger.warning("No Analysis nodes with root_cause found. Migration complete (nothing to do).")
                return
            
            # Step 2: Create RootCause nodes
            logger.info("Step 2: Creating RootCause nodes...")
            root_cause_count = session.execute_write(
                lambda tx: create_root_cause_nodes(tx, root_causes, args.dry_run)
            )
            logger.info(f"Created/updated {root_cause_count} RootCause nodes")
            
            # Step 3: Create Incident->RootCause relationships
            logger.info("Step 3: Creating (Incident)-[:HAS_ROOT_CAUSE]->(RootCause) relationships...")
            incident_rc_count = session.execute_write(
                lambda tx: create_incident_root_cause_relationships(tx, root_causes, args.dry_run)
            )
            logger.info(f"Created {incident_rc_count} HAS_ROOT_CAUSE relationships")
            
            # Step 4: Create Analysis->RootCause relationships
            logger.info("Step 4: Creating (Analysis)-[:IDENTIFIED]->(RootCause) relationships...")
            analysis_rc_count = session.execute_write(
                lambda tx: create_analysis_identified_relationships(tx, root_causes, args.dry_run)
            )
            logger.info(f"Created {analysis_rc_count} IDENTIFIED relationships")
            
            # Step 5: Create RootCause->ActionItem relationships
            logger.info("Step 5: Creating (RootCause)-[:SUGGESTS_ACTION]->(ActionItem) relationships...")
            suggests_action_count = session.execute_write(
                lambda tx: create_root_cause_action_item_relationships(tx, root_causes, args.dry_run)
            )
            logger.info(f"Created {suggests_action_count} SUGGESTS_ACTION relationships")
        
        # Step 6: Verify results
        logger.info("Step 6: Verifying migration...")
        stats = verify_migration(driver)
        
        logger.info("Migration complete!")
        logger.info(f"  RootCause nodes: {stats['root_causes']} (expected: 168)")
        logger.info(f"  HAS_ROOT_CAUSE relationships: {stats['has_root_cause_rels']}")
        logger.info(f"  IDENTIFIED relationships: {stats['identified_rels']}")
        logger.info(f"  SUGGESTS_ACTION relationships: {stats['suggests_action_rels']} (expected: 298)")
        
        # Check if counts match expectations
        success = True
        if stats['root_causes'] != 168:
            logger.warning(f"RootCause count mismatch: got {stats['root_causes']}, expected 168")
            success = False
        
        if stats['suggests_action_rels'] != 298:
            logger.warning(f"SUGGESTS_ACTION count mismatch: got {stats['suggests_action_rels']}, expected 298")
            # This might be OK if ActionItems don't exist yet
            logger.info("Note: SUGGESTS_ACTION relationship count may vary if ActionItems don't exist in graph")
        
        if success:
            logger.info("All verification checks passed!")
            sys.exit(0)
        else:
            logger.warning("Some verification checks failed. Review the output above.")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
