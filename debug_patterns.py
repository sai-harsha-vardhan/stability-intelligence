#!/usr/bin/env python3
"""Debug script to check pattern detection data in Neo4j."""

import os
import sys

# Add project to path
sys.path.insert(0, '/home/sai_harsha/stability/rca-intelligence-system/stability-intelligence')

# Set Neo4j connection - try localhost first (container might expose port)
os.environ.setdefault('NEO4J_URI', 'bolt://localhost:7687')
os.environ.setdefault('NEO4J_USER', 'neo4j')
os.environ.setdefault('NEO4J_PASSWORD', 'changeme_neo4j_pass123')

from graph.client import get_client

def main():
    print("=" * 60)
    print("Pattern Detection Debug Script")
    print("=" * 60)
    
    try:
        client = get_client()
        
        # 1. Check total incidents
        result = client.read("MATCH (i:Incident) RETURN count(i) as count")
        total_incidents = result[0]['count'] if result else 0
        print(f"\n1. Total Incidents: {total_incidents}")
        
        # 2. Check incidents with Analysis nodes
        result = client.read("""
            MATCH (i:Incident)-[:HAS_ANALYSIS]->(a:Analysis)
            RETURN count(DISTINCT i) as count
        """)
        incidents_with_analysis = result[0]['count'] if result else 0
        print(f"2. Incidents with Analysis: {incidents_with_analysis}")
        
        # 3. Check Analysis nodes with pattern signatures
        result = client.read("""
            MATCH (a:Analysis)
            WHERE a.pattern_signature IS NOT NULL
            RETURN count(a) as count
        """)
        analyses_with_sig = result[0]['count'] if result else 0
        print(f"3. Analyses with pattern_signature: {analyses_with_sig}")
        
        # 4. Check unique pattern signatures (excluding 'unanalyzed')
        result = client.read("""
            MATCH (a:Analysis)
            WHERE a.pattern_signature IS NOT NULL 
              AND a.pattern_signature <> 'unanalyzed'
            RETURN a.pattern_signature as sig, count(*) as freq
            ORDER BY freq DESC
            LIMIT 30
        """)
        print(f"\n4. Top Pattern Signatures (found {len(result)}):")
        for row in result:
            print(f"   - {row['sig']}: {row['freq']} incidents")
        
        # 5. Check existing PatternClusters
        result = client.read("MATCH (pc:PatternCluster) RETURN count(pc) as count")
        existing_clusters = result[0]['count'] if result else 0
        print(f"\n5. Existing PatternClusters: {existing_clusters}")
        
        # 6. Check sample incident data
        result = client.read("""
            MATCH (i:Incident)-[:HAS_ANALYSIS]->(a:Analysis)
            WHERE a.pattern_signature IS NOT NULL 
              AND a.pattern_signature <> 'unanalyzed'
            RETURN i.id, i.title, a.pattern_signature, a.category
            LIMIT 5
        """)
        print(f"\n6. Sample Incidents with Pattern Signatures:")
        for row in result:
            print(f"   - {row['i.id']}: {row['a.pattern_signature']}")
        
        # 7. Check if _group_incidents_by_pattern would return data
        result = client.read("""
            MATCH (i:Incident)-[:HAS_ANALYSIS]->(a:Analysis)
            WHERE a.pattern_signature IS NOT NULL
              AND a.pattern_signature <> 'unanalyzed'
            OPTIONAL MATCH (a)-[:HAS_ROOT_CAUSE]->(rc:RootCause)
            RETURN i.id AS incident_id,
                   i.title AS title,
                   i.occurred_at AS occurred_at,
                   i.created_at AS created_at,
                   a.pattern_signature AS pattern_signature,
                   a.category AS category,
                   COALESCE(rc.description, 'Unknown') AS root_cause,
                   a.affected_components AS affected_components
            ORDER BY a.pattern_signature, i.occurred_at
            LIMIT 10
        """)
        print(f"\n7. Query used by detect_patterns() returned {len(result)} rows")
        
        # 8. Group by pattern to see frequencies
        result = client.read("""
            MATCH (i:Incident)-[:HAS_ANALYSIS]->(a:Analysis)
            WHERE a.pattern_signature IS NOT NULL
              AND a.pattern_signature <> 'unanalyzed'
            WITH a.pattern_signature AS sig, count(i) AS freq
            WHERE freq >= 3
            RETURN sig, freq
            ORDER BY freq DESC
        """)
        print(f"\n8. Pattern signatures with >= 3 incidents ({len(result)} found):")
        for row in result:
            print(f"   - {row['sig']}: {row['freq']} incidents")
        
        print("\n" + "=" * 60)
        print("Summary:")
        print(f"  - Total incidents: {total_incidents}")
        print(f"  - With Analysis: {incidents_with_analysis}")
        print(f"  - With valid pattern_signature: {analyses_with_sig}")
        print(f"  - Existing PatternClusters: {existing_clusters}")
        print(f"  - Patterns with >= 3 incidents: {len(result)}")
        print("=" * 60)
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
