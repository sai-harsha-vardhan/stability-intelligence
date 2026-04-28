#!/usr/bin/env python3
"""
Create PatternCluster nodes from existing incident data.

This script reads Incident nodes from Neo4j, groups them by extracted
pattern signatures from titles/descriptions, and creates PatternCluster
nodes for groups with 3+ incidents.
"""

import os
import re
import uuid
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Any, Set

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ensure Neo4j connection
os.environ.setdefault('NEO4J_URI', 'bolt://localhost:7687')
os.environ.setdefault('NEO4J_USER', 'neo4j')
os.environ.setdefault('NEO4J_PASSWORD', 'changeme_neo4j_pass123')

def extract_pattern_signature(incident: Dict[str, Any]) -> str:
    """
    Extract a pattern signature from incident title/description.
    
    Rules:
    1. Look for keywords indicating error types
    2. Extract affected components
    3. Combine into signature: <category>/<component>
    """
    title = incident.get('title', '').lower()
    body = incident.get('body', '').lower()
    combined = title + ' ' + body
    
    # Category detection rules
    categories = {
        'resource_exhaustion': ['timeout', 'memory', 'cpu', 'resource', 'exhausted', 'oom'],
        'config_drift': ['config', 'configuration', 'deployment', 'deploy', 'rollback'],
        'race_condition': ['race', 'deadlock', 'concurrency', 'sync', 'thread'],
        'backward_compat': ['breaking', 'backward', 'compat', 'deprecat', 'migration'],
        'infra_failure': ['infrastructure', 'network', 'dns', 'disk', 'server', 'vm'],
        'data_corruption': ['database', 'db', 'corrupt', 'data loss', 'sql'],
        'dependency_failure': ['dependency', 'third-party', 'external', 'vendor', 'api'],
        'auth_failure': ['auth', 'authentication', 'login', 'credential', 'jwt'],
        'validation_error': ['validation', 'schema', 'serialize', 'deserialize'],
        'performance_degradation': ['slow', 'latency', 'performance', 'degradation'],
    }
    
    # Component detection
    components = [
        'payment', 'redis', 'postgres', 'kafka', 'api', 'webhook', 
        'connector', 'sdk', 'router', 'scheduler', 'vault', 'kms',
        'notification', 'email', 'sms', 'analytics', 'logging',
        'queue', 'worker', 'background', 'frontend', 'backend',
        'gateway', 'load balancer', 'cache', 'storage', 'queue',
        'card', 'bank', 'wallet', 'upi', 'crypto', 'neural',
        'ml', 'ai', 'llm', 'database', 'migration', 'upgrade'
    ]
    
    # Detect category
    detected_category = 'general'
    for category, keywords in categories.items():
        if any(kw in combined for kw in keywords):
            detected_category = category
            break
    
    # Detect primary component
    detected_component = 'system'
    for component in sorted(components, key=len, reverse=True):
        if component in combined:
            detected_component = component.replace(' ', '_')
            break
    
    # Special cases for better grouping
    if 'payment' in combined and any(x in combined for x in ['fail', 'declined', 'reject']):
        detected_category = 'payment_processing_failure'
    if 'webhook' in combined:
        detected_component = 'webhook'
    if 'redis' in combined or 'cache' in combined:
        detected_component = 'redis'
    if 'postgres' in combined or 'database' in combined:
        detected_component = 'database'
    
    return f"{detected_category}/{detected_component}"


def get_all_incidents() -> List[Dict[str, Any]]:
    """Fetch all incidents from Neo4j."""
    # Import here to allow env vars to be set first
    import sys
    sys.path.insert(0, '/home/sai_harsha/stability/rca-intelligence-system/stability-intelligence')
    from graph.client import get_client
    
    client = get_client()
    
    query = """
    MATCH (i:Incident)
    RETURN i.id AS id,
           i.title AS title,
           i.body AS body,
           i.occurred_at AS occurred_at,
           i.created_at AS created_at,
           i.severity AS severity,
           i.affected_flows AS affected_flows
    ORDER BY i.created_at DESC
    """
    
    return client.read(query)


def group_incidents_by_pattern(incidents: List[Dict[str, Any]]) -> Dict[str, List[Dict]]:
    """Group incidents by extracted pattern signatures."""
    groups = defaultdict(list)
    
    for incident in incidents:
        sig = extract_pattern_signature(incident)
        groups[sig].append(incident)
    
    return dict(groups)


def create_pattern_cluster(
    pattern_signature: str,
    incidents: List[Dict],
    client
) -> str:
    """Create a PatternCluster node with incident relationships."""
    cluster_id = f"pc-{uuid.uuid4().hex[:12]}"
    
    # Parse category and component from signature
    parts = pattern_signature.split('/', 1)
    category = parts[0]
    component = parts[1] if len(parts) > 1 else 'unknown'
    
    # Extract dates
    dates = []
    for inc in incidents:
        for date_field in ['occurred_at', 'created_at']:
            date_val = inc.get(date_field)
            if date_val:
                if isinstance(date_val, str):
                    try:
                        date_val = datetime.fromisoformat(date_val.replace('Z', '+00:00'))
                    except:
                        continue
                dates.append(date_val)
                break
    
    first_occurrence = min(dates) if dates else datetime.now(timezone.utc)
    last_occurrence = max(dates) if dates else datetime.now(timezone.utc)
    
    # Build name and description
    category_display = category.replace('_', ' ').title()
    component_display = component.replace('_', ' ').title()
    name = f"{category_display}: {component_display}"
    description = f"Pattern affecting {component_display} - {len(incidents)} incidents detected"
    
    # Collect affected components
    affected_components = list(set([
        comp for inc in incidents 
        for comp in (inc.get('affected_flows') or [component])
    ]))
    
    # Calculate trend based on dates
    now = datetime.now(timezone.utc)
    last_month = [d for d in dates if (now - d).days <= 30]
    prev_month = [d for d in dates if 30 < (now - d).days <= 60]
    
    if len(last_month) > len(prev_month):
        trend = 'worsening'
    elif len(last_month) < len(prev_month):
        trend = 'improving'
    else:
        trend = 'stable'
    
    # Create PatternCluster node
    cypher = """
    CREATE (pc:PatternCluster {
        id: $id,
        pattern_signature: $pattern_signature,
        name: $name,
        description: $description,
        frequency: $frequency,
        trend: $trend,
        root_cause_category: $category,
        affected_components: $affected_components,
        first_occurrence: $first_occurrence,
        last_occurrence: $last_occurrence,
        created_at: datetime(),
        updated_at: datetime()
    })
    RETURN pc.id
    """
    
    result = client.write(cypher, {
        'id': cluster_id,
        'pattern_signature': pattern_signature,
        'name': name,
        'description': description,
        'frequency': len(incidents),
        'trend': trend,
        'category': category,
        'affected_components': affected_components[:5],  # Limit to 5
        'first_occurrence': first_occurrence,
        'last_occurrence': last_occurrence,
    })
    
    # Create EXHIBITS relationships
    for incident in incidents:
        rel_cypher = """
        MATCH (i:Incident {id: $incident_id})
        MATCH (pc:PatternCluster {id: $cluster_id})
        CREATE (i)-[:EXHIBITS]->(pc)
        """
        try:
            client.write(rel_cypher, {
                'incident_id': incident['id'],
                'cluster_id': cluster_id,
            })
        except Exception as e:
            logger.warning(f"Failed to create relationship for {incident['id']}: {e}")
    
    logger.info(f"Created PatternCluster {cluster_id}: {name} ({len(incidents)} incidents, {trend})")
    return cluster_id


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("Creating Pattern Clusters from Incidents")
    logger.info("=" * 60)
    
    try:
        # Fetch all incidents
        logger.info("Fetching incidents from Neo4j...")
        incidents = get_all_incidents()
        logger.info(f"Found {len(incidents)} incidents")
        
        if not incidents:
            logger.error("No incidents found!")
            return 1
        
        # Group by pattern signature
        logger.info("Grouping incidents by pattern signatures...")
        groups = group_incidents_by_pattern(incidents)
        logger.info(f"Found {len(groups)} unique patterns")
        
        # Filter for patterns with 3+ incidents
        qualifying_groups = {
            sig: incs for sig, incs in groups.items() 
            if len(incs) >= 3
        }
        logger.info(f"Patterns with 3+ incidents: {len(qualifying_groups)}")
        
        # Show top patterns
        sorted_patterns = sorted(
            qualifying_groups.items(), 
            key=lambda x: len(x[1]), 
            reverse=True
        )
        logger.info("\nTop patterns:")
        for sig, incs in sorted_patterns[:15]:
            logger.info(f"  {sig}: {len(incs)} incidents")
        
        # Import client for writes
        import sys
        sys.path.insert(0, '/home/sai_harsha/stability/rca-intelligence-system/stability-intelligence')
        from graph.client import get_client
        client = get_client()
        
        # Check for existing PatternClusters
        existing = client.read("MATCH (pc:PatternCluster) RETURN pc.pattern_signature as sig")
        existing_sigs = {r['sig'] for r in existing if r.get('sig')}
        logger.info(f"\nExisting pattern clusters: {len(existing_sigs)}")
        
        # Create PatternClusters
        created_count = 0
        for pattern_sig, incidents_list in qualifying_groups.items():
            if pattern_sig in existing_sigs:
                logger.info(f"Skipping {pattern_sig} - already exists")
                continue
            
            try:
                create_pattern_cluster(pattern_sig, incidents_list, client)
                created_count += 1
            except Exception as e:
                logger.error(f"Failed to create cluster for {pattern_sig}: {e}")
        
        logger.info("\n" + "=" * 60)
        logger.info(f"Created {created_count} new PatternCluster nodes")
        logger.info("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
