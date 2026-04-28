"""
Link PatternCluster nodes to RootCause nodes.

Phase 3 of the RCA Intelligence Pipeline.
Creates relationships between detected patterns and their underlying root causes.

Usage:
    python scripts/link_patterns_to_root_causes.py [--dry-run] [--verbose]

Verification:
    docker exec stability-neo4j cypher-shell -u neo4j -p changeme_neo4j_pass123 \
        "MATCH ()-[r:MANIFESTS_AS]->() RETURN count(r);"
    # Expected: 100-200

    curl -s http://localhost:8000/patterns/root-cause-links | jq .links | length
    # Expected: 100-200
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from neo4j import Driver, GraphDatabase

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_neo4j_driver() -> Driver:
    """Create Neo4j driver from environment variables."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "changeme_neo4j_pass123")
    return GraphDatabase.driver(uri, auth=(user, password))


def fetch_pattern_clusters(tx) -> list[dict[str, Any]]:
    """Fetch all PatternCluster nodes from Neo4j."""
    query = """
    MATCH (pc:PatternCluster)
    RETURN pc.id AS id,
           pc.signature AS signature,
           pc.category AS category,
           pc.severity AS severity,
           pc.keywords AS keywords
    """
    result = tx.run(query)
    return [
        {
            "id": record["id"],
            "signature": record["signature"],
            "category": record["category"],
            "severity": record["severity"],
            "keywords": record["keywords"] or [],
        }
        for record in result
    ]


def fetch_root_causes(tx) -> list[dict[str, Any]]:
    """Fetch all RootCause nodes from Neo4j."""
    query = """
    MATCH (rc:RootCause)
    RETURN rc.id AS id,
           rc.description AS description,
           rc.category AS category,
           rc.mechanism AS mechanism,
           rc.confidence AS confidence
    """
    result = tx.run(query)
    return [
        {
            "id": record["id"],
            "description": record["description"],
            "category": record["category"],
            "mechanism": record["mechanism"],
            "confidence": record["confidence"] or 0.8,
        }
        for record in result
    ]


def find_linked_incidents(tx, pattern_cluster_id: str, root_cause_id: str) -> list[str]:
    """Find incidents that exhibit both the pattern and have the root cause."""
    query = """
    MATCH (i:Incident)-[:EXHIBITS]->(pc:PatternCluster {id: $pattern_id})
    MATCH (i)-[:HAS_ROOT_CAUSE]->(rc:RootCause {id: $root_cause_id})
    RETURN i.id AS incident_id
    """
    result = tx.run(query, {"pattern_id": pattern_cluster_id, "root_cause_id": root_cause_id})
    return [record["incident_id"] for record in result]


def calculate_link_strength(
    pattern_cluster: dict[str, Any],
    root_cause: dict[str, Any],
    shared_incident_ids: list[str],
) -> float:
    """Calculate the strength of the link between a pattern and root cause.

    Factors:
    - Category match: 0.4 points
    - Shared incidents: 0.3 points per incident (max 0.6)
    - Keyword overlap in root cause description: 0.1 points
    """
    strength = 0.0

    # Category match (primary factor)
    pc_category = pattern_cluster.get("category", "").lower()
    rc_category = root_cause.get("category", "").lower()

    if pc_category and rc_category and pc_category == rc_category:
        strength += 0.4

    # Shared incidents (evidence factor)
    shared_count = len(shared_incident_ids)
    strength += min(shared_count * 0.15, 0.6)

    # Keyword overlap in description (semantic factor)
    keywords = set(kw.lower() for kw in pattern_cluster.get("keywords", []))
    description = root_cause.get("description", "").lower()

    if keywords and description:
        matching_keywords = keywords.intersection(set(description.split()))
        if matching_keywords:
            strength += 0.1

    return round(min(strength, 1.0), 2)


def link_patterns_to_root_causes(
    tx,
    pattern_clusters: list[dict[str, Any]],
    root_causes: list[dict[str, Any]],
    min_strength: float = 0.3,
    dry_run: bool = False,
) -> int:
    """Create (PatternCluster)-[:MANIFESTS_AS]->(RootCause) relationships."""
    rel_count = 0

    for pattern_cluster in pattern_clusters:
        pc_id = pattern_cluster["id"]

        for root_cause in root_causes:
            rc_id = root_cause["id"]

            # Find incidents that link both entities (skip in dry-run mode)
            if dry_run:
                # In dry-run, estimate shared incidents from categories
                shared_incidents = []
            else:
                shared_incidents = find_linked_incidents(tx, pc_id, rc_id)

            # Calculate link strength
            strength = calculate_link_strength(pattern_cluster, root_cause, shared_incidents)

            if strength < min_strength:
                continue

            # Create relationship with metadata
            query = """
            MATCH (pc:PatternCluster {id: $pc_id})
            MATCH (rc:RootCause {id: $rc_id})
            MERGE (pc)-[r:MANIFESTS_AS]->(rc)
            ON CREATE SET
                r.strength = $strength,
                r.shared_incident_count = $shared_count,
                r.created_at = $created_at
            ON MATCH SET
                r.strength = $strength,
                r.shared_incident_count = $shared_count,
                r.updated_at = $updated_at
            RETURN count(r) AS rel_count
            """

            params = {
                "pc_id": pc_id,
                "rc_id": rc_id,
                "strength": strength,
                "shared_count": len(shared_incidents),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            if dry_run:
                logger.info(
                    f"[DRY RUN] Would link {pattern_cluster['signature']} -> {rc_id[:20]}... "
                    f"(strength: {strength}, incidents: {len(shared_incidents)})"
                )
                rel_count += 1
            else:
                try:
                    result = tx.run(query, params)
                    record = result.single()
                    if record:
                        rel_count += record["rel_count"]
                        logger.debug(
                            f"Linked {pattern_cluster['signature']} -> {rc_id[:20]}... "
                            f"(strength: {strength})"
                        )
                except Exception as e:
                    logger.warning(f"Failed to create relationship {pc_id} -> {rc_id}: {e}")

    return rel_count


def verify_link_integrity(driver: Driver) -> dict[str, Any]:
    """Verify the integrity of pattern-root cause links."""
    with driver.session() as session:
        # Count MANIFESTS_AS relationships
        result = session.run("MATCH ()-[r:MANIFESTS_AS]->() RETURN count(r) AS count")
        manifests_as_count = result.single()["count"]

        # Get average link strength
        result = session.run("""
            MATCH ()-[r:MANIFESTS_AS]->()
            RETURN avg(r.strength) AS avg_strength, min(r.strength) AS min_strength
        """)
        stats = result.single()
        avg_strength = stats["avg_strength"] or 0.0
        min_strength = stats["min_strength"] or 0.0

        # Count patterns without any root cause links
        result = session.run("""
            MATCH (pc:PatternCluster)
            WHERE NOT (pc)-[:MANIFESTS_AS]->(:RootCause)
            RETURN count(pc) AS count
        """)
        orphaned_patterns = result.single()["count"]

        # Count root causes without any pattern links
        result = session.run("""
            MATCH (rc:RootCause)
            WHERE NOT (:PatternCluster)-[:MANIFESTS_AS]->(rc)
            RETURN count(rc) AS count
        """)
        unlinked_root_causes = result.single()["count"]

        # Get links grouped by strength threshold
        result = session.run("""
            MATCH ()-[r:MANIFESTS_AS]->()
            RETURN
                count(CASE WHEN r.strength >= 0.7 THEN 1 END) AS strong,
                count(CASE WHEN r.strength >= 0.4 AND r.strength < 0.7 THEN 1 END) AS medium,
                count(CASE WHEN r.strength < 0.4 THEN 1 END) AS weak
        """)
        strength_dist = result.single()

        return {
            "manifests_as_relationships": manifests_as_count,
            "average_strength": round(avg_strength, 2),
            "minimum_strength": round(min_strength, 2),
            "orphaned_patterns": orphaned_patterns,
            "unlinked_root_causes": unlinked_root_causes,
            "strong_links": strength_dist["strong"],
            "medium_links": strength_dist["medium"],
            "weak_links": strength_dist["weak"],
        }


def main():
    parser = argparse.ArgumentParser(description="Link PatternCluster nodes to RootCause nodes")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--min-strength",
        type=float,
        default=0.3,
        help="Minimum link strength threshold (0.0-1.0, default: 0.3)",
    )
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    logger.info("Starting pattern-to-root-cause linking...")
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
            # Step 1: Fetch PatternCluster nodes
            logger.info("Step 1: Fetching PatternCluster nodes...")
            pattern_clusters = session.execute_read(fetch_pattern_clusters)
            logger.info(f"Found {len(pattern_clusters)} PatternCluster nodes")

            if not pattern_clusters:
                logger.warning("No PatternCluster nodes found. Run detect_patterns.py first.")
                return

            # Step 2: Fetch RootCause nodes
            logger.info("Step 2: Fetching RootCause nodes...")
            root_causes = session.execute_read(fetch_root_causes)
            logger.info(f"Found {len(root_causes)} RootCause nodes")

            if not root_causes:
                logger.warning("No RootCause nodes found. Run migrate_root_causes.py first.")
                return

            # Step 3: Create links
            logger.info(f"Step 3: Creating links (min strength: {args.min_strength})...")
            link_count = session.execute_write(
                lambda tx: link_patterns_to_root_causes(
                    tx, pattern_clusters, root_causes, args.min_strength, args.dry_run
                )
            )
            logger.info(f"Created/updated {link_count} MANIFESTS_AS relationships")

        # Step 4: Verify link integrity
        logger.info("Step 4: Verifying link integrity...")
        stats = verify_link_integrity(driver)

        logger.info("Link Integrity Report:")
        logger.info(f"  MANIFESTS_AS relationships: {stats['manifests_as_relationships']} (target: 100-200)")
        logger.info(f"  Average link strength: {stats['average_strength']}")
        logger.info(f"  Strong links (≥0.7): {stats['strong_links']}")
        logger.info(f"  Medium links (0.4-0.7): {stats['medium_links']}")
        logger.info(f"  Weak links (<0.4): {stats['weak_links']}")
        logger.info(f"  Orphaned patterns: {stats['orphaned_patterns']}")
        logger.info(f"  Unlinked root causes: {stats['unlinked_root_causes']}")

        # Validate criteria
        success = True
        if stats["manifests_as_relationships"] < 100:
            logger.warning(f"Link count {stats['manifests_as_relationships']} is below target (100-200)")
            success = False

        if stats["orphaned_patterns"] > len(pattern_clusters) * 0.3:
            logger.warning(f"Too many orphaned patterns: {stats['orphaned_patterns']}")
            success = False

        if success:
            logger.info("✅ Pattern-to-root-cause linking completed successfully!")
            sys.exit(0)
        else:
            logger.warning("⚠️  Some criteria not met. Review the output above.")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Linking failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
