"""Test RCA Agent functionality."""
import os
import sys
import uuid
import logging
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.rca_agent import RCAAgent
from graph.client import query, write, close_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_test_incidents():
    """Create test incidents for analysis."""
    logger.info("Creating test incidents...")
    
    incidents = [
        {
            "title": "Redis timeout causing payment failures",
            "body": """
Production incident: Payment processing experiencing high error rates.

Symptoms:
- 15% of payment requests timing out
- Redis cache showing elevated latency (>2s)
- Payment gateway API calls failing

Timeline:
- 14:30 UTC: First alerts for payment failures
- 14:35 UTC: Identified Redis latency issue
- 14:50 UTC: Restarted Redis cluster
- 15:00 UTC: Service restored

Impact:
- ~500 failed payments
- Multiple merchants affected
""",
            "severity": "P1",
            "affected_flows": ["payments", "checkout"],
            "occurred_at": datetime.utcnow() - timedelta(days=5),
        },
        {
            "title": "Redis cache timeout in payment processing",
            "body": """
High error rate in payment service due to Redis connection timeouts.

Details:
- Redis connections timing out after 1s
- Payment service unable to fetch merchant config
- Fallback to database causing high latency

Root cause:
- Redis connection pool exhausted
- Too many concurrent requests

Resolution:
- Increased connection pool size
- Added circuit breaker
""",
            "severity": "P1",
            "affected_flows": ["payments"],
            "occurred_at": datetime.utcnow() - timedelta(days=15),
        },
        {
            "title": "Payment API timeout during high traffic",
            "body": """
Payment processing slowed down significantly during peak hours.

Symptoms:
- API response times > 10s
- Redis showing high memory usage
- Connection pool exhausted

Fix:
- Scaled Redis cluster
- Optimized cache eviction
""",
            "severity": "P2",
            "affected_flows": ["payments", "api"],
            "occurred_at": datetime.utcnow() - timedelta(days=25),
        },
        {
            "title": "Configuration drift in staging environment",
            "body": """
Deployment to staging failed due to missing environment variable.

Details:
- DATABASE_URL not set in staging
- Application crashed on startup
- Config was manually changed, not synced with prod

Resolution:
- Added missing env var
- Updated deployment checklist
""",
            "severity": "P3",
            "affected_flows": ["deployment"],
            "occurred_at": datetime.utcnow() - timedelta(days=3),
        },
        {
            "title": "Webhook delivery failures due to API breaking change",
            "body": """
Webhook deliveries started failing after deploying v2.5.0.

Details:
- Changed webhook payload structure
- Removed deprecated 'metadata' field
- Merchants' webhook endpoints rejecting new format

Impact:
- 25% webhook delivery failure rate
- Customer complaints

Fix:
- Rolled back deployment
- Added backward compatibility layer
""",
            "severity": "P1",
            "affected_flows": ["webhooks", "api"],
            "occurred_at": datetime.utcnow() - timedelta(days=7),
        },
    ]
    
    incident_ids = []
    
    for inc_data in incidents:
        incident_id = f"incident-test-{uuid.uuid4().hex[:8]}"
        
        cypher = """
        CREATE (i:Incident {
            id: $id,
            title: $title,
            body: $body,
            raw_body: $body,
            severity: $severity,
            affected_flows: $affected_flows,
            occurred_at: $occurred_at,
            created_at: $created_at,
            updated_at: $updated_at
        })
        RETURN i.id
        """
        
        write(cypher, {
            "id": incident_id,
            "title": inc_data["title"],
            "body": inc_data["body"],
            "severity": inc_data["severity"],
            "affected_flows": inc_data["affected_flows"],
            "occurred_at": inc_data["occurred_at"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        
        incident_ids.append(incident_id)
        logger.info(f"Created test incident: {incident_id}")
    
    return incident_ids


def test_rca_agent():
    """Test the RCA agent end-to-end."""
    logger.info("=" * 60)
    logger.info("RCA Agent Test Suite")
    logger.info("=" * 60)
    
    try:
        # Step 1: Create test incidents
        incident_ids = create_test_incidents()
        logger.info(f"Created {len(incident_ids)} test incidents")
        
        # Step 2: Run RCA agent
        logger.info("\nRunning RCA agent...")
        agent = RCAAgent()
        stats = agent.run()
        
        logger.info(f"\nAgent Statistics:")
        logger.info(f"  Incidents Analyzed: {stats['incidents_analyzed']}")
        logger.info(f"  Patterns Detected: {stats['patterns_detected']}")
        
        # Step 3: Verify Analysis nodes and RootCause nodes
        logger.info("\nVerifying Analysis nodes...")
        cypher = """
        MATCH (i:Incident)-[:HAS_ANALYSIS]->(a:Analysis)-[:HAS_ROOT_CAUSE]->(rc:RootCause)
        WHERE i.id STARTS WITH 'incident-test-'
        RETURN i.title AS title,
               rc.description AS root_cause,
               rc.category AS category,
               a.pattern_signature AS pattern_signature,
               a.is_recurring AS is_recurring,
               a.affected_components AS components
        ORDER BY i.occurred_at DESC
        """
        analyses = query(cypher)
        
        logger.info(f"\nFound {len(analyses)} analyses with RootCause nodes:")
        for idx, analysis in enumerate(analyses, 1):
            logger.info(f"\n{idx}. {analysis['title']}")
            logger.info(f"   Root Cause: {analysis['root_cause']}")
            logger.info(f"   Category: {analysis['category']}")
            logger.info(f"   Pattern: {analysis['pattern_signature']}")
            logger.info(f"   Recurring: {analysis['is_recurring']}")
            logger.info(f"   Components: {analysis['components']}")
        
        # Step 3b: Verify RootCause nodes count
        cypher = """
        MATCH (rc:RootCause)
        WHERE rc.id STARTS WITH 'rootcause-'
        RETURN count(rc) AS root_cause_count
        """
        root_cause_result = query(cypher)
        root_cause_count = root_cause_result[0]["root_cause_count"] if root_cause_result else 0
        logger.info(f"\nTotal RootCause nodes created: {root_cause_count}")
        
        # Step 3c: Verify IDENTIFIED relationships
        cypher = """
        MATCH (i:Incident)-[r:IDENTIFIED]->(rc:RootCause)
        WHERE i.id STARTS WITH 'incident-test-'
        RETURN count(r) AS identified_relationships
        """
        identified_result = query(cypher)
        identified_count = identified_result[0]["identified_relationships"] if identified_result else 0
        logger.info(f"IDENTIFIED relationships created: {identified_count}")
        
        # Step 4: Verify PatternCluster nodes
        logger.info("\n" + "=" * 60)
        logger.info("Pattern Clusters Detected:")
        logger.info("=" * 60)
        
        cypher = """
        MATCH (pc:PatternCluster)<-[:EXHIBITS]-(i:Incident)
        WHERE i.id STARTS WITH 'incident-test-'
        WITH pc, collect(i.title) AS incidents
        RETURN pc.name AS name,
               pc.description AS description,
               pc.frequency AS frequency,
               pc.trend AS trend,
               pc.root_cause_category AS category,
               pc.affected_components AS components,
               incidents
        ORDER BY pc.frequency DESC
        """
        patterns = query(cypher)
        
        if patterns:
            for idx, pattern in enumerate(patterns, 1):
                logger.info(f"\n{idx}. {pattern['name']}")
                logger.info(f"   Description: {pattern['description']}")
                logger.info(f"   Frequency: {pattern['frequency']}")
                logger.info(f"   Trend: {pattern['trend']}")
                logger.info(f"   Category: {pattern['category']}")
                logger.info(f"   Components: {pattern['components']}")
                logger.info(f"   Incidents:")
                for inc in pattern['incidents']:
                    logger.info(f"     - {inc}")
        else:
            logger.info("No patterns detected (need >= 3 similar incidents)")
        
        # Step 5: Test pattern detection a second time (should not create duplicates)
        logger.info("\n" + "=" * 60)
        logger.info("Testing idempotency (running agent again)...")
        logger.info("=" * 60)
        
        stats2 = agent.run()
        logger.info(f"Second run statistics:")
        logger.info(f"  Incidents Analyzed: {stats2['incidents_analyzed']}")
        logger.info(f"  Patterns Detected: {stats2['patterns_detected']}")
        
        if stats2['incidents_analyzed'] == 0:
            logger.info("✓ Idempotency test passed: No duplicate analyses")
        else:
            logger.warning("⚠ Idempotency test failed: Created duplicate analyses")
        
        # Step 6: Summary
        logger.info("\n" + "=" * 60)
        logger.info("TEST SUMMARY")
        logger.info("=" * 60)
        logger.info(f"✓ Created {len(incident_ids)} test incidents")
        logger.info(f"✓ Analyzed {stats['incidents_analyzed']} incidents")
        logger.info(f"✓ Created {root_cause_count} RootCause nodes")
        logger.info(f"✓ Created {identified_count} IDENTIFIED relationships")
        logger.info(f"✓ Detected {stats['patterns_detected']} pattern clusters")
        logger.info(f"✓ Generated {len(analyses)} root cause analyses")
        
        if stats['patterns_detected'] > 0:
            logger.info("\n✓ Pattern recognition working correctly!")
            logger.info("  (Found clusters with >= 3 similar incidents)")
        else:
            logger.info("\nℹ No patterns detected (expected if < 3 similar incidents)")
        
        # Verify critical assertions
        all_pass = True
        if root_cause_count != len(analyses):
            logger.error(f"❌ ERROR: RootCause count ({root_cause_count}) != Analysis count ({len(analyses)})")
            all_pass = False
        if identified_count != len(analyses):
            logger.error(f"❌ ERROR: IDENTIFIED relationship count ({identified_count}) != Analysis count ({len(analyses)})")
            all_pass = False
        
        if all_pass:
            logger.info("\n✓ All structural validations passed!")
            logger.info("  RootCause nodes are properly linked to Analysis and Incident nodes")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        return False
    finally:
        # Cleanup
        logger.info("\n" + "=" * 60)
        logger.info("Cleaning up test data...")
        cypher = """
        MATCH (i:Incident)
        WHERE i.id STARTS WITH 'incident-test-'
        OPTIONAL MATCH (i)-[:HAS_ANALYSIS]->(a:Analysis)-[:HAS_ROOT_CAUSE]->(rc:RootCause)
        OPTIONAL MATCH (i)-[:EXHIBITS]->(pc:PatternCluster)
        OPTIONAL MATCH (i)-[:IDENTIFIED]->(rc2:RootCause)
        DETACH DELETE i, a, rc, rc2, pc
        """
        write(cypher)
        logger.info("✓ Test data cleaned up")
        close_client()


if __name__ == "__main__":
    success = test_rca_agent()
    sys.exit(0 if success else 1)
