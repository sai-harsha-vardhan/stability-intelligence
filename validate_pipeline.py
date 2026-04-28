#!/usr/bin/env python3
"""Pipeline validation script for RCA-57.

Validates Phase 5-6 requirements:
- 168 RootCause nodes exist
- 15-30 PatternCluster nodes
- Proper graph relationships
- Varied priority scores (not all 0.15)
- Dashboard endpoints functional
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graph.client import get_client, query
from graph.queries import GET_PATTERN_CLUSTERS, GET_TOP_ACTION_ITEMS


def count_nodes(label: str) -> int:
    """Count nodes by label."""
    result = query(f"MATCH (n:{label}) RETURN count(n) AS count")
    return result[0]["count"] if result else 0


def count_relationships(rel_type: str) -> int:
    """Count relationships by type."""
    result = query(f"MATCH ()-[r:{rel_type}]->() RETURN count(r) AS count")
    return result[0]["count"] if result else 0


def get_priority_score_distribution() -> dict:
    """Analyze priority score distribution."""
    result = query("""
        MATCH (ai:ActionItem)
        WHERE ai.priority_score IS NOT NULL
        RETURN 
            count(ai) AS total,
            min(ai.priority_score) AS min_score,
            max(ai.priority_score) AS max_score,
            avg(ai.priority_score) AS avg_score
    """)
    return result[0] if result else {}


def get_score_variety() -> dict:
    """Get variety of priority scores (unique count)."""
    result = query("""
        MATCH (ai:ActionItem)
        WHERE ai.priority_score IS NOT NULL
        RETURN collect(DISTINCT ai.priority_score) AS unique_scores
    """)
    if result and result[0].get("unique_scores"):
        scores = result[0]["unique_scores"]
        return {
            "unique_count": len(scores),
            "scores": sorted(scores)[:10]  # First 10 for brevity
        }
    return {"unique_count": 0, "scores": []}


def validate_root_causes(expected: int = 168) -> dict:
    """Validate RootCause nodes."""
    count = count_nodes("RootCause")
    return {
        "expected": expected,
        "actual": count,
        "status": "PASS" if count >= expected else "FAIL",
        "message": f"Expected {expected}+ RootCause nodes, found {count}"
    }


def validate_pattern_clusters(min_expected: int = 15, max_expected: int = 30) -> dict:
    """Validate PatternCluster nodes."""
    count = count_nodes("PatternCluster")
    return {
        "expected_range": f"{min_expected}-{max_expected}",
        "actual": count,
        "status": "PASS" if min_expected <= count <= max_expected else "WARNING",
        "message": f"Expected {min_expected}-{max_expected} PatternClusters, found {count}"
    }


def validate_relationships() -> dict:
    """Validate graph relationships."""
    rel_counts = {}
    critical_rels = ["ROOT_CAUSE_OF", "BELONGS_TO_CLUSTER", "HAS_ROOT_CAUSE", 
                     "AFFECTS_PATTERN", "BLOCKS_PATTERN", "ADDRESSES_PATTERN"]
    
    for rel in critical_rels:
        rel_counts[rel] = count_relationships(rel)
    
    total_rels = sum(rel_counts.values())
    
    return {
        "counts": rel_counts,
        "total": total_rels,
        "status": "PASS" if total_rels > 0 else "FAIL",
        "message": f"Total relationships: {total_rels}"
    }


def validate_priority_scores() -> dict:
    """Validate priority scores are varied and not all 0.15."""
    dist = get_priority_score_distribution()
    variety = get_score_variety()
    
    status = "PASS"
    messages = []
    
    if dist.get("total", 0) == 0:
        status = "FAIL"
        messages.append("No ActionItems with priority_score found")
    else:
        # Check for variety
        if variety.get("unique_count", 0) < 5:
            status = "FAIL"
            messages.append(f"Not enough score variety: only {variety['unique_count']} unique values")
        
        # Check min/max spread
        min_score = dist.get("min_score", 0)
        max_score = dist.get("max_score", 0)
        if max_score - min_score < 1.0:
            status = "FAIL"
            messages.append(f"Score range too narrow: {min_score:.2f} - {max_score:.2f}")
        
        # Check if all are 0.15 (the old uniform value)
        if variety.get("unique_count", 0) == 1 and abs(min_score - 0.15) < 0.01:
            status = "FAIL"
            messages.append("All scores are uniformly 0.15 - recalculation needed")
    
    if not messages:
        messages.append(f"Good score distribution: {variety['unique_count']} unique values, range {min_score:.2f}-{max_score:.2f}")
    
    return {
        "distribution": dist,
        "variety": variety,
        "status": status,
        "message": "; ".join(messages)
    }


def validate_dashboard_endpoints() -> dict:
    """Test dashboard query endpoints."""
    tests = []
    
    # Test GET_PATTERN_CLUSTERS
    try:
        result = query(GET_PATTERN_CLUSTERS)
        tests.append({
            "endpoint": "GET_PATTERN_CLUSTERS",
            "status": "PASS",
            "records": len(result)
        })
    except Exception as e:
        tests.append({
            "endpoint": "GET_PATTERN_CLUSTERS",
            "status": "FAIL",
            "error": str(e)
        })
    
    # Test GET_TOP_ACTION_ITEMS
    try:
        result = query(GET_TOP_ACTION_ITEMS.replace("$limit", "10"))
        tests.append({
            "endpoint": "GET_TOP_ACTION_ITEMS",
            "status": "PASS", 
            "records": len(result)
        })
    except Exception as e:
        tests.append({
            "endpoint": "GET_TOP_ACTION_ITEMS",
            "status": "FAIL",
            "error": str(e)
        })
    
    all_pass = all(t["status"] == "PASS" for t in tests)
    return {
        "tests": tests,
        "status": "PASS" if all_pass else "FAIL",
        "message": f"{sum(1 for t in tests if t['status'] == 'PASS')}/{len(tests)} endpoints working"
    }


def run_validation():
    """Run full pipeline validation."""
    print("=" * 60)
    print("RCA PIPELINE VALIDATION - Phase 5-6")
    print("=" * 60)
    
    # Test connection first
    client = get_client()
    health = client.health_check()
    if health["status"] != "healthy":
        print(f"ERROR: Neo4j connection failed: {health}")
        sys.exit(1)
    
    print(f"Neo4j connected: {health['components'][0]['name']}\n")
    
    results = []
    
    # 1. RootCause nodes
    print("\n1. ROOT CAUSE NODES")
    print("-" * 40)
    rc_result = validate_root_causes()
    print(f"Status: {rc_result['status']}")
    print(f"Message: {rc_result['message']}")
    results.append(("RootCause Count", rc_result))
    
    # 2. PatternCluster nodes
    print("\n2. PATTERN CLUSTER NODES")
    print("-" * 40)
    pc_result = validate_pattern_clusters()
    print(f"Status: {pc_result['status']}")
    print(f"Message: {pc_result['message']}")
    results.append(("PatternCluster Count", pc_result))
    
    # 3. Graph relationships
    print("\n3. GRAPH RELATIONSHIPS")
    print("-" * 40)
    rel_result = validate_relationships()
    print(f"Status: {rel_result['status']}")
    print(f"Message: {rel_result['message']}")
    print(f"  Details: {rel_result['counts']}")
    results.append(("Relationships", rel_result))
    
    # 4. Priority scores
    print("\n4. PRIORITY SCORE DISTRIBUTION")
    print("-" * 40)
    ps_result = validate_priority_scores()
    print(f"Status: {ps_result['status']}")
    print(f"Message: {ps_result['message']}")
    if ps_result['distribution']:
        dist = ps_result['distribution']
        print(f"  Total ActionItems: {dist.get('total', 0)}")
        print(f"  Min: {dist.get('min_score', 0):.2f}, Max: {dist.get('max_score', 0):.2f}")
        print(f"  Avg: {dist.get('avg_score', 0):.2f}")
    results.append(("Priority Scores", ps_result))
    
    # 5. Dashboard endpoints
    print("\n5. DASHBOARD ENDPOINTS")
    print("-" * 40)
    dash_result = validate_dashboard_endpoints()
    print(f"Status: {dash_result['status']}")
    print(f"Message: {dash_result['message']}")
    for test in dash_result['tests']:
        print(f"  - {test['endpoint']}: {test['status']} ({test.get('records', 'N/A')} records)")
    results.append(("Dashboard", dash_result))
    
    # Summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r['status'] == 'PASS')
    warnings = sum(1 for _, r in results if r['status'] == 'WARNING')
    failed = sum(1 for _, r in results if r['status'] == 'FAIL')
    
    print(f"PASSED: {passed}")
    print(f"WARNINGS: {warnings}")
    print(f"FAILED: {failed}")
    print(f"TOTAL: {len(results)}")
    
    if failed == 0:
        print("\n✓ OVERALL: PASS - Pipeline validation successful")
        return 0
    else:
        print("\n✗ OVERALL: FAIL - Some validations failed")
        return 1


if __name__ == "__main__":
    exit_code = run_validation()
    sys.exit(exit_code)
