"""
Link RootCause and ActionItem nodes to PatternCluster nodes.

Phase 4 of the RCA Intelligence Pipeline fix.
Creates graph relationships clustering root causes into patterns and linking
action items to the patterns they address.

Relationships created:
- (RootCause)-[:CLUSTERED_INTO]->(PatternCluster) - Root cause belongs to pattern
- (ActionItem)-[:ADDRESSES_PATTERN]->(PatternCluster) - Action item addresses pattern

Usage:
    python scripts/link_patterns.py [--dry-run] [--verbose] [--threshold N]

Verification:
    docker exec stability-neo4j cypher-shell -u neo4j -p changeme_neo4j_pass123 \
        "MATCH ()-[r:CLUSTERED_INTO]->() RETURN count(r);"
    # Expected: 50-150 (root causes clustered into patterns)

    docker exec stability-neo4j cypher-shell -u neo4j -p changeme_neo4j_pass123 \
        "MATCH ()-[r:ADDRESSES_PATTERN]->() RETURN count(r);"
    # Expected: 100-250 (action items addressing patterns)
"""

import argparse
import hashlib
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from neo4j import Driver, GraphDatabase, Session

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_neo4j_driver() -> Driver:
    """Create Neo4j driver from environment variables."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "changeme_neo4j_pass123")
    return GraphDatabase.driver(uri, auth=(user, password))


def normalize_text_for_matching(text: str) -> set[str]:
    """Normalize text to create a set of searchable keywords."""
    if not text:
        return set()
    
    # Convert to lowercase and split
    text = text.lower()
    
    # Extract meaningful keywords (filter out common words)
    filler_words = {'the', 'a', 'an', 'is', 'was', 'are', 'were', 'in', 'on', 
                    'at', 'to', 'of', 'and', 'or', 'but', 'for', 'with', 'as',
                    'by', 'from', 'that', 'this', 'these', 'those'}
    
    words = text.split()
    keywords = {w.strip('.,;:!?()[]{}') for w in words if w not in filler_words and len(w) > 2}
    
    return keywords


def fetch_all_pattern_clusters(tx: Session) -> list[dict[str, Any]]:
    """Fetch all PatternCluster nodes."""
    query = """
    MATCH (pc:PatternCluster)
    RETURN pc.id AS cluster_id,
           pc.signature AS signature,
           pc.category AS category,
           pc.mechanism AS mechanism,
           pc.description AS description,
           pc.frequency AS frequency
    ORDER BY pc.frequency DESC
    """
    result = tx.run(query)
    return [
        {
            "cluster_id": record["cluster_id"],
            "signature": record["signature"],
            "category": record["category"] or "uncategorized",
            "mechanism": record["mechanism"] or "unknown",
            "description": record["description"] or "",
            "frequency": record["frequency"] or 0,
        }
        for record in result
    ]


def fetch_all_root_causes(tx: Session) -> list[dict[str, Any]]:
    """Fetch all RootCause nodes with their incident associations."""
    query = """
    MATCH (rc:RootCause)
    OPTIONAL MATCH (rc)<-[:HAS_ROOT_CAUSE]-(i:Incident)
    RETURN rc.id AS root_cause_id,
           rc.category AS category,
           rc.mechanism AS mechanism,
           rc.description AS description,
           rc.confidence AS confidence,
           collect(DISTINCT i.id) AS incident_ids
    ORDER BY rc.created_at DESC
    """
    result = tx.run(query)
    return [
        {
            "root_cause_id": record["root_cause_id"],
            "category": record["category"] or "uncategorized",
            "mechanism": record["mechanism"] or "unknown",
            "description": record["description"] or "",
            "confidence": record["confidence"] or 0.8,
            "incident_ids": [iid for iid in record["incident_ids"] if iid],
        }
        for record in result
    ]


def fetch_all_action_items(tx: Session) -> list[dict[str, Any]]:
    """Fetch all ActionItem nodes with their associated RootCauses and Patterns."""
    query = """
    MATCH (ai:ActionItem)
    OPTIONAL MATCH (ai)<-[:SUGGESTS_ACTION]-(rc:RootCause)
    OPTIONAL MATCH (ai)<-[:ADDRESSES_PATTERN]-(pc:PatternCluster)
    RETURN ai.id AS action_item_id,
           ai.description AS description,
           ai.category AS category,
           ai.status AS status,
           ai.priority AS priority,
           collect(DISTINCT rc.id) AS linked_root_cause_ids,
           collect(DISTINCT rc.category) AS linked_rc_categories
    ORDER BY ai.created_at DESC
    """
    result = tx.run(query)
    return [
        {
            "action_item_id": record["action_item_id"],
            "description": record["description"] or "",
            "category": record["category"] or "uncategorized",
            "status": record["status"],
            "priority": record["priority"] or 0.0,
            "linked_root_cause_ids": [rc_id for rc_id in record["linked_root_cause_ids"] if rc_id],
            "linked_rc_categories": [cat for cat in record["linked_rc_categories"] if cat],
        }
        for record in result
    ]


def calculate_category_match_score(
    pc_category: str, pc_mechanism: str, rc_category: str, rc_mechanism: str
) -> float:
    """Calculate a match score based on category alignment."""
    score = 0.0
    
    # Direct category match
    if pc_category.lower() == rc_category.lower():
        score += 0.5
    
    # Mechanism match (stronger indicator)
    if pc_mechanism.lower() == rc_mechanism.lower():
        score += 0.3
    
    # Related category mapping
    category_relations = {
        "performance": ["timeout", "cpu", "memory", "slow", "latency"],
        "capacity": ["rate_limit", "quota", "throttle", "limit"],
        "network": ["connection", "connectivity", "dns", "timeout"],
        "security": ["authentication", "auth", "unauthorized", "permission", "access"],
        "error_handling": ["exception", "error", "crash", "failure"],
        "database": ["sql", "query", "transaction", "lock"],
        "configuration": ["config", "setting", "parameter"],
        "dependency": ["service", "api", "endpoint", "dependency"],
    }
    
    pc_cat_lower = pc_category.lower()
    rc_cat_lower = rc_category.lower()
    
    # Check if categories are related
    for base_cat, related in category_relations.items():
        pc_matches = pc_cat_lower in related or any(r in pc_cat_lower for r in related)
        rc_matches = rc_cat_lower in related or any(r in rc_cat_lower for r in related)
        if pc_matches and rc_matches:
            score += 0.2
            break
    
    return min(score, 1.0)


def calculate_text_similarity_score(text1: str, text2: str) -> float:
    """Calculate a simple keyword overlap score between two texts."""
    keywords1 = normalize_text_for_matching(text1)
    keywords2 = normalize_text_for_matching(text2)
    
    if not keywords1 or not keywords2:
        return 0.0
    
    # Calculate Jaccard similarity
    intersection = len(keywords1 & keywords2)
    union = len(keywords1 | keywords2)
    
    if union == 0:
        return 0.0
    
    return intersection / union


def find_matching_pattern_clusters(
    root_cause: dict[str, Any],
    pattern_clusters: list[dict[str, Any]],
    threshold: float = 0.4
) -> list[tuple[str, float]]:
    """Find PatternCluster nodes that match a RootCause."""
    matches = []
    
    for pc in pattern_clusters:
        # Category-based score
        category_score = calculate_category_match_score(
            pc["category"],
            pc["mechanism"],
            root_cause["category"],
            root_cause["mechanism"]
        )
        
        # Text similarity score
        text_score = calculate_text_similarity_score(
            pc["description"],
            root_cause["description"]
        )
        
        # Combined score (weighted)
        total_score = (category_score * 0.6) + (text_score * 0.4)
        
        if total_score >= threshold:
            matches.append((pc["cluster_id"], total_score))
    
    # Sort by score descending and return top matches
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[:3]  # Limit to top 3 clusters per root cause


def create_clustered_into_relationships(
    tx: Session,
    matches: list[tuple[str, str, float]],  # (root_cause_id, cluster_id, score)
    dry_run: bool = False
) -> int:
    """Create (RootCause)-[:CLUSTERED_INTO]->(PatternCluster) relationships."""
    rel_count = 0
    
    for root_cause_id, cluster_id, score in matches:
        query = """
        MATCH (rc:RootCause {id: $root_cause_id})
        MATCH (pc:PatternCluster {id: $cluster_id})
        MERGE (rc)-[r:CLUSTERED_INTO]->(pc)
        ON CREATE SET
            r.cluster_confidence = $score,
            r.created_at = $created_at
        ON MATCH SET
            r.cluster_confidence = $score
        RETURN count(r) AS rel_count
        """
        
        params = {
            "root_cause_id": root_cause_id,
            "cluster_id": cluster_id,
            "score": round(score, 3),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        if dry_run:
            logger.debug(f"[DRY RUN] Would create CLUSTERED_INTO: {root_cause_id[:20]}... -> {cluster_id[:20]}...")
            rel_count += 1
        else:
            try:
                result = tx.run(query, params)
                record = result.single()
                if record:
                    rel_count += record["rel_count"]
            except Exception as e:
                logger.warning(f"Failed to create CLUSTERED_INTO relationship: {e}")
    
    return rel_count


def find_patterns_addressed_by_action_item(
    action_item: dict[str, Any],
    pattern_clusters: list[dict[str, Any]],
    clustered_into_pairs: list[tuple[str, str, float]]  # (root_cause_id, cluster_id, score)
) -> list[tuple[str, float]]:
    """Find PatternCluster nodes addressed by an ActionItem."""
    addressed = []
    
    # Get pattern clusters this action item's root causes are clustered into
    ai_root_cause_ids = set(action_item["linked_root_cause_ids"])
    related_cluster_ids = {
        cluster_id for rc_id, cluster_id, _ in clustered_into_pairs
        if rc_id in ai_root_cause_ids
    }
    
    for pc in pattern_clusters:
        score = 0.0
        
        # Direct link: ActionItem linked to RootCause that is clustered into this Pattern
        if pc["cluster_id"] in related_cluster_ids:
            score += 0.6  # Strong link via shared root cause
        
        # Category match between action item and pattern
        ai_categories = set(cat.lower() for cat in action_item["linked_rc_categories"] if cat)
        if pc["category"].lower() in ai_categories:
            score += 0.25
        
        # Text similarity between pattern and action item description
        text_score = calculate_text_similarity_score(
            pc["description"],
            action_item["description"]
        )
        score += text_score * 0.15
        
        # Boost score for high priority action items
        if action_item.get("priority", 0) > 5.0:
            score += 0.1
        
        if score >= 0.3:  # Threshold for addressing relationship
            addressed.append((pc["cluster_id"], min(score, 1.0)))
    
    # Sort by score and return top matches
    addressed.sort(key=lambda x: x[1], reverse=True)
    return addressed[:5]  # Limit to top 5 patterns per action item


def create_addresses_pattern_relationships(
    tx: Session,
    matches: list[tuple[str, str, float]],  # (action_item_id, cluster_id, score)
    dry_run: bool = False
) -> int:
    """Create (ActionItem)-[:ADDRESSES_PATTERN]->(PatternCluster) relationships."""
    rel_count = 0
    
    for action_item_id, cluster_id, score in matches:
        query = """
        MATCH (ai:ActionItem {id: $action_item_id})
        MATCH (pc:PatternCluster {id: $cluster_id})
        MERGE (ai)-[r:ADDRESSES_PATTERN]->(pc)
        ON CREATE SET
            r.address_score = $score,
            r.created_at = $created_at
        ON MATCH SET
            r.address_score = $score
        RETURN count(r) AS rel_count
        """
        
        params = {
            "action_item_id": action_item_id,
            "cluster_id": cluster_id,
            "score": round(score, 3),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        if dry_run:
            logger.debug(f"[DRY RUN] Would create ADDRESSES_PATTERN: {action_item_id[:20]}... -> {cluster_id[:20]}...")
            rel_count += 1
        else:
            try:
                result = tx.run(query, params)
                record = result.single()
                if record:
                    rel_count += record["rel_count"]
            except Exception as e:
                logger.warning(f"Failed to create ADDRESSES_PATTERN relationship: {e}")
    
    return rel_count


def verify_pattern_links(driver: Driver) -> dict[str, Any]:
    """Verify pattern linking results."""
    with driver.session() as session:
        # Count PatternCluster nodes
        result = session.run("MATCH (pc:PatternCluster) RETURN count(pc) AS count")
        cluster_count = result.single()["count"]
        
        # Count RootCause nodes
        result = session.run("MATCH (rc:RootCause) RETURN count(rc) AS count")
        root_cause_count = result.single()["count"]
        
        # Count ActionItem nodes
        result = session.run("MATCH (ai:ActionItem) RETURN count(ai) AS count")
        action_item_count = result.single()["count"]
        
        # Count CLUSTERED_INTO relationships
        result = session.run("MATCH ()-[r:CLUSTERED_INTO]->() RETURN count(r) AS count")
        clustered_into_count = result.single()["count"]
        
        # Count ADDRESSES_PATTERN relationships
        result = session.run("MATCH ()-[r:ADDRESSES_PATTERN]->() RETURN count(r) AS count")
        addresses_pattern_count = result.single()["count"]
        
        # Get PatternClusters with no incoming links (orphaned)
        result = session.run("""
            MATCH (pc:PatternCluster)
            WHERE NOT ()-[:CLUSTERED_INTO|ADDRESSES_PATTERN]->(pc)
            RETURN count(pc) AS count
        """)
        orphaned_count = result.single()["count"]
        
        # Get average cluster confidence scores
        result = session.run("""
            MATCH ()-[r:CLUSTERED_INTO]->()
            RETURN avg(r.cluster_confidence) AS avg_score
        """)
        avg_cluster_score = result.single()["avg_score"] or 0.0
        
        result = session.run("""
            MATCH ()-[r:ADDRESSES_PATTERN]->()
            RETURN avg(r.address_score) AS avg_score
        """)
        avg_address_score = result.single()["avg_score"] or 0.0
        
        # Get percentage of root causes clustered
        result = session.run("""
            MATCH (rc:RootCause)
            OPTIONAL MATCH (rc)-[r:CLUSTERED_INTO]->(:PatternCluster)
            RETURN count(DISTINCT rc) AS total, 
                   count(DISTINCT CASE WHEN r IS NOT NULL THEN rc END) AS clustered
        """)
        stats = result.single()
        coverage_pct = (stats["clustered"] / stats["total"] * 100) if stats["total"] > 0 else 0
        
        return {
            "pattern_clusters": cluster_count,
            "root_causes": root_cause_count,
            "action_items": action_item_count,
            "clustered_into": clustered_into_count,
            "addresses_pattern": addresses_pattern_count,
            "orphaned_clusters": orphaned_count,
            "cluster_coverage_pct": round(coverage_pct, 1),
            "avg_cluster_score": round(avg_cluster_score, 3),
            "avg_address_score": round(avg_address_score, 3),
        }


def main():
    parser = argparse.ArgumentParser(
        description="Link RootCause and ActionItem nodes to PatternCluster nodes"
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--threshold", type=float, default=0.4, help="Match threshold (0.0-1.0, default: 0.4)")
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    logger.info("Starting pattern linking...")
    logger.info(f"Configuration: threshold={args.threshold}")
    
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
            # Step 1: Fetch all entities
            logger.info("Step 1: Fetching PatternClusters...")
            pattern_clusters = session.execute_read(fetch_all_pattern_clusters)
            logger.info(f"Found {len(pattern_clusters)} PatternClusters")
            
            logger.info("Step 2: Fetching RootCauses...")
            root_causes = session.execute_read(fetch_all_root_causes)
            logger.info(f"Found {len(root_causes)} RootCauses")
            
            logger.info("Step 3: Fetching ActionItems...")
            action_items = session.execute_read(fetch_all_action_items)
            logger.info(f"Found {len(action_items)} ActionItems")
            
            if not pattern_clusters:
                logger.warning("No PatternClusters found. Cannot create links.")
                return
            
            if not root_causes:
                logger.warning("No RootCauses found. Cannot create CLUSTERED_INTO links.")
            
            # Step 4: Match RootCauses to PatternClusters
            logger.info("Step 4: Matching RootCauses to PatternClusters...")
            clustered_into_pairs = []  # (root_cause_id, cluster_id, score)
            
            for rc in root_causes:
                matches = find_matching_pattern_clusters(rc, pattern_clusters, threshold=args.threshold)
                for cluster_id, score in matches:
                    clustered_into_pairs.append((rc["root_cause_id"], cluster_id, score))
            
            logger.info(f"Found {len(clustered_into_pairs)} RootCause->PatternCluster matches")
            
            # Step 5: Create CLUSTERED_INTO relationships
            logger.info("Step 5: Creating (RootCause)-[:CLUSTERED_INTO]->(PatternCluster) relationships...")
            clustered_count = session.execute_write(
                lambda tx: create_clustered_into_relationships(tx, clustered_into_pairs, args.dry_run)
            )
            logger.info(f"Created/updated {clustered_count} CLUSTERED_INTO relationships")
            
            # Step 6: Match ActionItems to PatternClusters
            logger.info("Step 6: Matching ActionItems to PatternClusters...")
            addresses_pairs = []  # (action_item_id, cluster_id, score)
            
            for ai in action_items:
                addressed = find_patterns_addressed_by_action_item(
                    ai, pattern_clusters, clustered_into_pairs
                )
                for cluster_id, score in addressed:
                    addresses_pairs.append((ai["action_item_id"], cluster_id, score))
            
            logger.info(f"Found {len(addresses_pairs)} ActionItem->PatternCluster relationships")
            
            # Step 7: Create ADDRESSES_PATTERN relationships
            logger.info("Step 7: Creating (ActionItem)-[:ADDRESSES_PATTERN]->(PatternCluster) relationships...")
            addresses_count = session.execute_write(
                lambda tx: create_addresses_pattern_relationships(tx, addresses_pairs, args.dry_run)
            )
            logger.info(f"Created/updated {addresses_count} ADDRESSES_PATTERN relationships")
        
        # Step 8: Verify results
        if not args.dry_run:
            logger.info("Step 8: Verifying pattern links...")
            stats = verify_pattern_links(driver)
            
            logger.info("Pattern linking complete!")
            logger.info(f"  PatternCluster nodes: {stats['pattern_clusters']}")
            logger.info(f"  RootCause nodes: {stats['root_causes']}")
            logger.info(f"  ActionItem nodes: {stats['action_items']}")
            logger.info(f"  CLUSTERED_INTO relationships: {stats['clustered_into']} (target: 50-150)")
            logger.info(f"  ADDRESSES_PATTERN relationships: {stats['addresses_pattern']} (target: 100-250)")
            logger.info(f"  Cluster coverage: {stats['cluster_coverage_pct']}% of root causes")
            logger.info(f"  Orphaned PatternClusters: {stats['orphaned_clusters']}")
            logger.info(f"  Avg CLUSTERED_INTO score: {stats['avg_cluster_score']}")
            logger.info(f"  Avg ADDRESSES_PATTERN score: {stats['avg_address_score']}")
            
            # Validate results
            success = True
            if stats['clustered_into'] < 40:
                logger.warning(f"Low CLUSTERED_INTO count: {stats['clustered_into']} (expected 50-150)")
                success = False
            
            if stats['addresses_pattern'] < 80:
                logger.warning(f"Low ADDRESSES_PATTERN count: {stats['addresses_pattern']} (expected 100-250)")
                success = False
            
            if stats['cluster_coverage_pct'] < 50:
                logger.warning(f"Low cluster coverage: {stats['cluster_coverage_pct']}% (expected >50%)")
                success = False
            
            if success:
                logger.info("Pattern linking completed successfully!")
                sys.exit(0)
            else:
                logger.warning("Some validation warnings. Review the output above.")
                sys.exit(1)
        else:
            logger.info("Dry run complete. Use without --dry-run to apply changes.")
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"Pattern linking failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
