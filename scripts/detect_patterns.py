"""
Pattern detection script for RCA Intelligence Pipeline.

Phase 2 of the RCA Intelligence Pipeline fix.
Detects patterns in incidents and creates PatternCluster nodes.

Usage:
    python scripts/detect_patterns.py [--dry-run] [--verbose] [--min-frequency N]

Verification:
    docker exec stability-neo4j cypher-shell -u neo4j -p changeme_neo4j_pass123 \
        "MATCH (pc:PatternCluster) RETURN count(pc);"
    # Expected: 15-30

    docker exec stability-neo4j cypher-shell -u neo4j -p changeme_neo4j_pass123 \
        "MATCH ()-[r:EXHIBITS]->() RETURN count(r);"
    # Expected: Count of incident-pattern relationships
"""

import argparse
import hashlib
import logging
import os
import re
import sys
from collections import defaultdict
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


def normalize_pattern_key(text: str) -> str:
    """Normalize text to create consistent pattern keys."""
    if not text:
        return "unknown"
    # Convert to lowercase
    text = text.lower()
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove common filler words
    filler_words = ['the', 'a', 'an', 'is', 'was', 'are', 'were', 'in', 'on', 'at', 'to', 'of']
    words = text.split()
    words = [w for w in words if w not in filler_words]
    # Take first 10 significant words as key
    return ' '.join(words[:10])


def extract_pattern_signature(root_cause_text: str, category: str) -> str:
    """Extract a signature for grouping similar root causes."""
    normalized = normalize_pattern_key(root_cause_text)
    
    # Extract key patterns based on common error types
    patterns = []
    
    # Check for specific error patterns
    if 'timeout' in normalized or 'timed out' in normalized:
        patterns.append('timeout')
    if 'rate limit' in normalized or 'rate limiting' in normalized or 'quota' in normalized:
        patterns.append('rate_limit')
    if 'connection' in normalized or 'connect' in normalized:
        patterns.append('connection')
    if 'authentication' in normalized or 'auth' in normalized or 'unauthorized' in normalized:
        patterns.append('authentication')
    if 'permission' in normalized or 'access denied' in normalized:
        patterns.append('permission')
    if 'memory' in normalized or 'oom' in normalized:
        patterns.append('memory')
    if 'cpu' in normalized or 'processing' in normalized:
        patterns.append('cpu')
    if 'database' in normalized or 'sql' in normalized or 'query' in normalized:
        patterns.append('database')
    if 'api' in normalized or 'endpoint' in normalized:
        patterns.append('api_error')
    if 'crash' in normalized or 'exception' in normalized or 'error' in normalized:
        patterns.append('runtime_error')
    if 'configuration' in normalized or 'config' in normalized:
        patterns.append('configuration')
    if 'dependency' in normalized or 'service' in normalized:
        patterns.append('dependency_failure')
    
    # If no specific patterns found, use category + first words
    if not patterns:
        patterns.append(category.lower().replace(' ', '_') if category else 'general')
        patterns.append(normalized[:50].replace(' ', '_'))
    
    # Create deterministic signature
    signature = '_'.join(sorted(set(patterns)))
    return signature


def fetch_all_incidents_with_root_causes(tx: Session) -> list[dict[str, Any]]:
    """Fetch all Incidents and their associated RootCauses."""
    query = """
    MATCH (i:Incident)-[:HAS_ROOT_CAUSE]->(rc:RootCause)
    RETURN i.id AS incident_id,
           i.title AS title,
           i.severity AS severity,
           i.status AS status,
           i.source AS source,
           rc.id AS root_cause_id,
           rc.description AS root_cause_description,
           rc.category AS category,
           rc.mechanism AS mechanism,
           rc.confidence AS confidence
    ORDER BY i.id
    """
    result = tx.run(query)
    return [
        {
            "incident_id": record["incident_id"],
            "title": record["title"],
            "severity": record["severity"],
            "status": record["status"],
            "source": record["source"],
            "root_cause_id": record["root_cause_id"],
            "root_cause_description": record["root_cause_description"],
            "category": record["category"],
            "mechanism": record["mechanism"],
            "confidence": record["confidence"],
        }
        for record in result
    ]


def group_incidents_by_pattern(incidents: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group incidents by their root cause patterns."""
    pattern_groups = defaultdict(lambda: {
        "incidents": [],
        "categories": set(),
        "mechanisms": set(),
        "descriptions": [],
        "severities": [],
        "sources": set(),
    })
    
    for incident in incidents:
        # Generate pattern signature
        signature = extract_pattern_signature(
            incident["root_cause_description"] or "",
            incident["category"] or "uncategorized"
        )
        
        # Group by signature
        group = pattern_groups[signature]
        group["incidents"].append(incident)
        group["categories"].add(incident["category"] or "uncategorized")
        group["mechanisms"].add(incident["mechanism"] or "unknown")
        group["descriptions"].append(incident["root_cause_description"] or "")
        group["severities"].append(incident["severity"] or "medium")
        if incident["source"]:
            group["sources"].add(incident["source"])
    
    return dict(pattern_groups)


def generate_pattern_cluster_id(signature: str) -> str:
    """Generate a deterministic ID for a PatternCluster."""
    return f"pc_{hashlib.sha256(signature.encode()).hexdigest()[:12]}"


def create_pattern_clusters(
    tx: Session,
    pattern_groups: dict[str, dict[str, Any]],
    min_frequency: int = 3,
    dry_run: bool = False
) -> tuple[int, list[str]]:
    """Create PatternCluster nodes for patterns meeting the frequency threshold."""
    created_count = 0
    cluster_ids = []
    
    for signature, group in pattern_groups.items():
        frequency = len(group["incidents"])
        
        # Only create clusters for patterns with sufficient frequency
        if frequency < min_frequency:
            logger.debug(f"Skipping pattern '{signature[:40]}...' - frequency {frequency} < {min_frequency}")
            continue
        
        cluster_id = generate_pattern_cluster_id(signature)
        cluster_ids.append(cluster_id)
        
        # Determine primary category (most common)
        primary_category = max(group["categories"], key=lambda c: sum(1 for i in group["incidents"] if i["category"] == c))
        
        # Determine primary mechanism
        primary_mechanism = max(group["mechanisms"], key=lambda m: sum(1 for i in group["incidents"] if i["mechanism"] == m))
        
        # Calculate average severity
        severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        avg_severity_num = sum(severity_order.get(s, 2) for s in group["severities"]) / len(group["severities"])
        avg_severity = {4: "critical", 3: "high", 2: "medium", 1: "low"}.get(round(avg_severity_num), "medium")
        
        # Build description from most common elements
        # Find representative description (shortest non-empty one)
        representative_desc = min(
            (d for d in group["descriptions"] if d),
            key=len,
            default="Multiple incidents with similar characteristics"
        )
        
        query = """
        MERGE (pc:PatternCluster {id: $cluster_id})
        ON CREATE SET
            pc.signature = $signature,
            pc.frequency = $frequency,
            pc.category = $category,
            pc.mechanism = $mechanism,
            pc.description = $description,
            pc.avg_severity = $avg_severity,
            pc.sources = $sources,
            pc.created_at = $created_at,
            pc.updated_at = $updated_at
        ON MATCH SET
            pc.frequency = $frequency,
            pc.updated_at = $updated_at
        RETURN pc.id AS id
        """
        
        params = {
            "cluster_id": cluster_id,
            "signature": signature,
            "frequency": frequency,
            "category": primary_category,
            "mechanism": primary_mechanism,
            "description": representative_desc[:500],  # Limit length
            "avg_severity": avg_severity,
            "sources": list(group["sources"]),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        
        if dry_run:
            logger.info(f"[DRY RUN] Would create PatternCluster: {cluster_id[:25]}... "
                       f"(signature: {signature[:40]}..., frequency: {frequency})")
            created_count += 1
        else:
            result = tx.run(query, params)
            record = result.single()
            if record:
                created_count += 1
                logger.debug(f"Created/updated PatternCluster: {record['id']}")
    
    return created_count, cluster_ids


def create_exhibits_relationships(
    tx: Session,
    pattern_groups: dict[str, dict[str, Any]],
    min_frequency: int = 3,
    dry_run: bool = False
) -> int:
    """Create (Incident)-[:EXHIBITS]->(PatternCluster) relationships."""
    rel_count = 0
    
    for signature, group in pattern_groups.items():
        frequency = len(group["incidents"])
        
        if frequency < min_frequency:
            continue
        
        cluster_id = generate_pattern_cluster_id(signature)
        
        for incident in group["incidents"]:
            incident_id = incident["incident_id"]
            confidence = incident["confidence"] or 0.8
            
            query = """
            MATCH (i:Incident {id: $incident_id})
            MATCH (pc:PatternCluster {id: $cluster_id})
            MERGE (i)-[r:EXHIBITS]->(pc)
            ON CREATE SET
                r.confidence = $confidence,
                r.created_at = $created_at
            ON MATCH SET
                r.confidence = $confidence
            RETURN count(r) AS rel_count
            """
            
            params = {
                "incident_id": incident_id,
                "cluster_id": cluster_id,
                "confidence": confidence,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            
            if dry_run:
                logger.debug(f"[DRY RUN] Would create (Incident:{incident_id})-[:EXHIBITS]->(PatternCluster)")
                rel_count += 1
            else:
                try:
                    result = tx.run(query, params)
                    record = result.single()
                    if record:
                        rel_count += record["rel_count"]
                except Exception as e:
                    logger.warning(f"Failed to create EXHIBITS relationship for incident {incident_id}: {e}")
    
    return rel_count


def verify_patterns(driver: Driver) -> dict[str, int]:
    """Verify pattern detection results."""
    with driver.session() as session:
        # Count PatternCluster nodes
        result = session.run("MATCH (pc:PatternCluster) RETURN count(pc) AS count")
        cluster_count = result.single()["count"]
        
        # Count EXHIBITS relationships
        result = session.run("MATCH ()-[r:EXHIBITS]->() RETURN count(r) AS count")
        exhibits_count = result.single()["count"]
        
        # Get distribution by frequency
        result = session.run("""
            MATCH (pc:PatternCluster)
            RETURN pc.frequency AS freq, count(pc) AS count
            ORDER BY freq DESC
        """)
        freq_distribution = {record["freq"]: record["count"] for record in result}
        
        # Count unique incidents involved
        result = session.run("""
            MATCH (i:Incident)-[:EXHIBITS]->(pc:PatternCluster)
            RETURN count(DISTINCT i) AS count
        """)
        unique_incidents = result.single()["count"]
        
        return {
            "clusters": cluster_count,
            "exhibits_rels": exhibits_count,
            "unique_incidents": unique_incidents,
            "freq_distribution": freq_distribution,
        }


def main():
    parser = argparse.ArgumentParser(description="Detect patterns in incidents and create PatternCluster nodes")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--min-frequency", type=int, default=3, help="Minimum incident count to form a cluster (default: 3)")
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    logger.info("Starting pattern detection...")
    logger.info(f"Configuration: min_frequency={args.min_frequency}")
    
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
            # Step 1: Fetch all incidents with their root causes
            logger.info("Step 1: Fetching incidents with root causes...")
            incidents = session.execute_read(fetch_all_incidents_with_root_causes)
            logger.info(f"Found {len(incidents)} incident-root_cause associations")
            
            if not incidents:
                logger.warning("No incidents with root causes found. Nothing to analyze.")
                return
            
            # Step 2: Group incidents by pattern
            logger.info("Step 2: Grouping incidents by pattern signatures...")
            pattern_groups = group_incidents_by_pattern(incidents)
            logger.info(f"Identified {len(pattern_groups)} unique patterns")
            
            # Show distribution
            freq_dist = defaultdict(int)
            for sig, group in pattern_groups.items():
                freq_dist[len(group["incidents"])] += 1
            logger.info(f"Pattern frequency distribution: {dict(sorted(freq_dist.items(), reverse=True))}")
            
            # Step 3: Create PatternCluster nodes
            logger.info(f"Step 3: Creating PatternCluster nodes (min_frequency={args.min_frequency})...")
            cluster_count, cluster_ids = session.execute_write(
                lambda tx: create_pattern_clusters(tx, pattern_groups, args.min_frequency, args.dry_run)
            )
            logger.info(f"Created/updated {cluster_count} PatternCluster nodes")
            
            # Step 4: Create EXHIBITS relationships
            logger.info("Step 4: Creating (Incident)-[:EXHIBITS]->(PatternCluster) relationships...")
            exhibits_count = session.execute_write(
                lambda tx: create_exhibits_relationships(tx, pattern_groups, args.min_frequency, args.dry_run)
            )
            logger.info(f"Created {exhibits_count} EXHIBITS relationships")
        
        # Step 5: Verify results
        if not args.dry_run:
            logger.info("Step 5: Verifying pattern detection...")
            stats = verify_patterns(driver)
            
            logger.info("Pattern detection complete!")
            logger.info(f"  PatternCluster nodes: {stats['clusters']} (target: 15-30)")
            logger.info(f"  EXHIBITS relationships: {stats['exhibits_rels']}")
            logger.info(f"  Unique incidents in clusters: {stats['unique_incidents']}")
            logger.info(f"  Frequency distribution: {stats['freq_distribution']}")
            
            # Validate against target
            success = True
            if stats['clusters'] < 15:
                logger.warning(f"PatternCluster count below target: got {stats['clusters']}, expected 15-30")
                success = False
            elif stats['clusters'] > 30:
                logger.warning(f"PatternCluster count above target: got {stats['clusters']}, expected 15-30")
                # This isn't necessarily bad, just noteworthy
            
            if stats['clusters'] == 0:
                logger.error("No PatternClusters created! Check min_frequency threshold.")
                success = False
            
            if success:
                logger.info("Pattern detection completed successfully!")
                sys.exit(0)
            else:
                logger.warning("Some validation warnings. Review the output above.")
                sys.exit(1)
        else:
            logger.info("Dry run complete. Use without --dry-run to apply changes.")
            sys.exit(0)
            
    except Exception as e:
        logger.error(f"Pattern detection failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
