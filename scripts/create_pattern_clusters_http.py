#!/usr/bin/env python3
"""
Create PatternCluster nodes using Neo4j HTTP API.
Works around bolt connection issues.
"""

import os
import sys
import uuid
import json
import re
from collections import defaultdict
from datetime import datetime, timezone

# Neo4j HTTP API config
NEO4J_URL = "http://localhost:9474"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "changeme_neo4j_pass123"

def query_neo4j(cypher, params=None):
    """Execute Cypher query via Neo4j HTTP API."""
    import base64
    import urllib.request
    import urllib.error
    
    auth_str = base64.b64encode(f"{NEO4J_USER}:{NEO4J_PASSWORD}".encode()).decode()
    
    payload = {
        "statements": [{
            "statement": cypher,
            "parameters": params or {}
        }]
    }
    
    req = urllib.request.Request(
        f"{NEO4J_URL}/db/neo4j/tx/commit",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth_str}"
        },
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            
        if result.get("errors"):
            print(f"Errors: {result['errors']}")
            return []
        
        data = result["results"][0]["data"] if result["results"] else []
        return [row["row"] for row in data]
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode()}")
        return []
    except Exception as e:
        print(f"Error: {e}")
        return []


def extract_signature(title: str, body: str = "") -> str:
    """Extract pattern signature from incident text."""
    combined = (title + " " + body).lower()
    
    cats = {
        'resource_exhaustion': ['timeout', 'memory', 'cpu', 'oom'],
        'config_drift': ['config', 'deploy', 'rollback'],
        'race_condition': ['race', 'deadlock', 'concurrency'],
        'backward_compat': ['breaking', 'backward', 'compat'],
        'infra_failure': ['infrastructure', 'network', 'dns'],
        'data_corruption': ['database', 'corrupt'],
        'dependency_failure': ['dependency', 'external'],
        'auth_failure': ['auth', 'login', 'credential'],
        'payment_failure': ['payment', 'transaction'],
        'webhook_failure': ['webhook', 'callback'],
    }
    
    comps = [
        'payment', 'redis', 'postgres', 'kafka', 'api', 'webhook', 
        'connector', 'sdk', 'router', 'scheduler', 'vault',
        'notification', 'email', 'analytics', 'logging',
        'queue', 'worker', 'frontend', 'backend', 'gateway',
        'cache', 'storage', 'database', 'migration'
    ]
    
    # Detect category
    cat = next((c for c, kws in cats.items() if any(kw in combined for kw in kws)), 'general')
    
    # Detect component
    comp = next((c for c in sorted(comps, key=len, reverse=True) if c in combined), 'system')
    
    return f"{cat}/{comp}"


def parse_datetime(dt):
    """Parse datetime from various formats, ensuring timezone awareness."""
    if dt is None:
        return None
    
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    
    if isinstance(dt, str):
        try:
            # Try parsing ISO format
            dt_str = dt.replace('Z', '+00:00')
            parsed = datetime.fromisoformat(dt_str)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except:
            try:
                # Try other formats
                import re
                match = re.match(r'(\d{4}-\d{2}-\d{2})[T ]?(\d{2}:\d{2}:\d{2})', dt_str)
                if match:
                    dt_str = f"{match.group(1)}T{match.group(2)}"
                    parsed = datetime.fromisoformat(dt_str)
                    return parsed.replace(tzinfo=timezone.utc)
            except:
                pass
    return None


def main():
    print("=" * 60)
    print("Creating Pattern Clusters via HTTP API")
    print("=" * 60)
    
    # Test connection
    print("\nTesting Neo4j connection...")
    test = query_neo4j("RETURN 1 as n")
    if not test:
        print("ERROR: Cannot connect to Neo4j HTTP API")
        return 1
    print("Connected successfully")
    
    # Fetch incidents
    print("\nFetching incidents...")
    incidents = query_neo4j("""
        MATCH (i:Incident)
        RETURN i.id AS id, 
               i.title AS title, 
               i.body AS body,
               i.occurred_at AS occurred_at, 
               i.created_at AS created_at,
               i.affected_flows AS affected_flows
        ORDER BY i.created_at DESC
    """)
    
    print(f"Found {len(incidents)} incidents")
    
    if not incidents:
        print("ERROR: No incidents found")
        return 1
    
    # Group by pattern signature
    print("\nExtracting pattern signatures...")
    groups = defaultdict(list)
    for inc in incidents:
        if len(inc) >= 2:
            sig = extract_signature(inc[1] or "", inc[2] or "")
            groups[sig].append({
                'id': inc[0],
                'title': inc[1],
                'body': inc[2],
                'occurred_at': inc[3],
                'created_at': inc[4],
                'affected_flows': inc[5]
            })
    
    print(f"Found {len(groups)} unique pattern signatures")
    
    # Check existing
    existing = query_neo4j("MATCH (pc:PatternCluster) RETURN pc.pattern_signature AS sig")
    existing_sigs = {r[0] for r in existing if r}
    print(f"Existing PatternClusters: {len(existing_sigs)}")
    
    # Create clusters
    created = 0
    skipped = 0
    
    # Count qualifying groups
    qualifying = [(sig, incs) for sig, incs in groups.items() if len(incs) >= 2]
    print(f"\n{len(qualifying)} patterns have 2+ incidents")
    
    for sig, incs in qualifying:
        if sig in existing_sigs:
            skipped += 1
            continue
        
        parts = sig.split('/', 1)
        cluster_id = f"pc-{uuid.uuid4().hex[:12]}"
        
        # Calculate dates
        dates = []
        for inc in incs:
            dt = parse_datetime(inc.get('occurred_at')) or parse_datetime(inc.get('created_at'))
            if dt:
                dates.append(dt)
        
        now = datetime.now(timezone.utc)
        first = min(dates) if dates else now
        last = max(dates) if dates else now
        
        # Calculate trend
        if dates:
            recent = len([d for d in dates if (now - d).days <= 30])
            prev = len([d for d in dates if 30 < (now - d).days <= 60])
            trend = 'worsening' if recent > prev else 'improving' if recent < prev else 'stable'
        else:
            trend = 'stable'
        
        # Collect affected components
        all_comps = []
        for inc in incs:
            comps = inc.get('affected_flows') or []
            if isinstance(comps, list):
                all_comps.extend(comps)
            elif isinstance(comps, str):
                all_comps.append(comps)
        
        affected_comps = list(set(all_comps))[:5]
        
        # Create PatternCluster
        name = f"{parts[0].replace('_', ' ').title()}: {parts[1].replace('_', ' ').title()}"
        desc = f"Pattern affecting {parts[1]} - {len(incs)} incidents"
        
        query_neo4j("""
            CREATE (pc:PatternCluster {
                id: $id,
                pattern_signature: $sig,
                name: $name,
                description: $desc,
                frequency: $freq,
                trend: $trend,
                root_cause_category: $cat,
                affected_components: $comps,
                first_occurrence: datetime($first),
                last_occurrence: datetime($last),
                created_at: datetime(),
                updated_at: datetime()
            })
        """, {
            'id': cluster_id,
            'sig': sig,
            'name': name,
            'desc': desc,
            'freq': len(incs),
            'trend': trend,
            'cat': parts[0],
            'comps': affected_comps or ['system'],
            'first': first.isoformat() if hasattr(first, 'isoformat') else str(first),
            'last': last.isoformat() if hasattr(last, 'isoformat') else str(last)
        })
        
        # Create EXHIBITS relationships
        for inc in incs:
            query_neo4j("""
                MATCH (i:Incident {id: $iid})
                MATCH (pc:PatternCluster {id: $cid})
                CREATE (i)-[:EXHIBITS]->(pc)
            """, {'iid': inc['id'], 'cid': cluster_id})
        
        created += 1
        print(f"Created: {sig} ({len(incs)} incidents, {trend})")
    
    print("\n" + "=" * 60)
    print(f"SUMMARY: Created {created} PatternClusters, Skipped {skipped}")
    print("=" * 60)
    
    # Verify
    verify = query_neo4j("MATCH (pc:PatternCluster) RETURN count(pc) AS cnt")
    if verify:
        print(f"\nVerification: {verify[0][0]} PatternClusters now exist")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
