#!/usr/bin/env python3
"""
GitHub Issue to Neo4j Graph Transformation Pipeline

Transforms synced GitHub issues (JSONL files) into Neo4j graph nodes:
- Incident nodes for "incident-reported" labeled issues
- ActionItem nodes for "rca-action-item" labeled issues

Creates relationships between related issues based on linked_issues field.

Usage:
    python transform_issues_to_graph.py
"""

import sys
import logging
import uuid
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.github_sync import load_all_cached_issues
from graph.client import get_client

logger = logging.getLogger(__name__)


# Component extraction patterns
COMPONENT_PATTERNS = [
    r'crates/[a-z_]+',
    r'connector[s]?[:/\s]+(\w+)',
    r'payment[s]?',
    r'router',
    r'api',
    r'core',
    r'flows',
    r'database',
    r'redis',
    r'kafka',
]


def extract_severity(labels: List[str]) -> str:
    """
    Extract severity from labels.
    
    Maps:
    - SEV-1 or P0 -> critical
    - SEV-2 or P1 -> high
    - SEV-3 or P2 -> medium
    - Default -> low
    """
    labels_lower = [label.lower() for label in labels]
    
    if 'sev-1' in labels_lower or 'p0' in labels_lower:
        return 'critical'
    elif 'sev-2' in labels_lower or 'p1' in labels_lower:
        return 'high'
    elif 'sev-3' in labels_lower or 'p2' in labels_lower:
        return 'medium'
    else:
        return 'low'


def extract_status(labels: List[str]) -> str:
    """
    Extract status from labels for incidents.
    
    Maps:
    - "RCA Discussed" -> discussed
    - "RCA Prepared" -> prepared
    - "Incident Mitigated" -> mitigated
    - "Incident Completed" -> completed
    - Default -> reported
    """
    labels_lower = [label.lower() for label in labels]
    
    if 'incident completed' in labels_lower:
        return 'completed'
    elif 'incident mitigated' in labels_lower:
        return 'mitigated'
    elif 'rca prepared' in labels_lower:
        return 'prepared'
    elif 'rca discussed' in labels_lower:
        return 'discussed'
    else:
        return 'reported'


def extract_action_status(state: str) -> str:
    """
    Extract status for action items.
    
    Maps:
    - closed -> resolved
    - open -> open
    """
    return 'resolved' if state.lower() == 'closed' else 'open'


def extract_components(body: str) -> List[str]:
    """
    Extract affected components from issue body.
    
    Searches for patterns like:
    - crates/router
    - connector: stripe
    - payment gateway
    - etc.
    """
    if not body:
        return []
    
    components = set()
    body_lower = body.lower()
    
    for pattern in COMPONENT_PATTERNS:
        matches = re.findall(pattern, body_lower)
        components.update(matches)
    
    return sorted(list(components))


def create_incident_node(client, issue: Dict) -> bool:
    """
    Create an Incident node in Neo4j.
    
    Returns True if node was created/updated successfully.
    """
    try:
        incident_id = f"inc-{uuid.uuid4()}"
        github_number = issue['github_issue_number']
        
        # Extract properties
        severity = extract_severity(issue.get('labels', []))
        status = extract_status(issue.get('labels', []))
        components = extract_components(issue.get('body', ''))
        
        # Build Cypher MERGE query to avoid duplicates
        query = """
        MERGE (i:Incident {github_issue_number: $github_number})
        ON CREATE SET
            i.id = $id,
            i.created_at = datetime($created_at),
            i.severity = $severity,
            i.status = $status,
            i.title = $title,
            i.body = $body,
            i.labels = $labels,
            i.author = $author,
            i.affected_components = $components,
            i.updated_at = datetime($updated_at)
        ON MATCH SET
            i.updated_at = datetime($updated_at),
            i.severity = $severity,
            i.status = $status,
            i.title = $title,
            i.body = $body,
            i.labels = $labels,
            i.affected_components = $components
        RETURN i.id AS id
        """
        
        params = {
            'id': incident_id,
            'github_number': github_number,
            'title': issue.get('title', ''),
            'body': issue.get('body', ''),
            'severity': severity,
            'status': status,
            'created_at': issue.get('created_at', datetime.now().isoformat()),
            'updated_at': issue.get('updated_at', datetime.now().isoformat()),
            'labels': issue.get('labels', []),
            'author': issue.get('author', 'unknown'),
            'components': components,
        }
        
        result = client.write(query, params)
        logger.info(f"Created/updated Incident node for issue #{github_number}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create Incident node for issue #{issue.get('github_issue_number')}: {e}")
        return False


def create_action_item_node(client, issue: Dict) -> bool:
    """
    Create an ActionItem node in Neo4j.
    
    Returns True if node was created/updated successfully.
    """
    try:
        action_id = f"action-{uuid.uuid4()}"
        github_number = issue['github_issue_number']
        
        # Extract properties
        status = extract_action_status(issue.get('state', 'open'))
        
        # Build Cypher MERGE query to avoid duplicates
        query = """
        MERGE (a:ActionItem {github_issue_number: $github_number})
        ON CREATE SET
            a.id = $id,
            a.created_at = datetime($created_at),
            a.status = $status,
            a.title = $title,
            a.body = $body,
            a.labels = $labels,
            a.updated_at = datetime($updated_at)
        ON MATCH SET
            a.updated_at = datetime($updated_at),
            a.status = $status,
            a.title = $title,
            a.body = $body,
            a.labels = $labels
        RETURN a.id AS id
        """
        
        params = {
            'id': action_id,
            'github_number': github_number,
            'title': issue.get('title', ''),
            'body': issue.get('body', ''),
            'status': status,
            'created_at': issue.get('created_at', datetime.now().isoformat()),
            'updated_at': issue.get('updated_at', datetime.now().isoformat()),
            'labels': issue.get('labels', []),
        }
        
        result = client.write(query, params)
        logger.info(f"Created/updated ActionItem node for issue #{github_number}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create ActionItem node for issue #{issue.get('github_issue_number')}: {e}")
        return False


def create_relationships(client, issues: List[Dict]) -> int:
    """
    Create relationships between nodes based on linked_issues.
    
    Relationships:
    - (Incident)-[:HAS_ANALYSIS]->(Incident) - when incident links to RCA discussion
    - (ActionItem)-[:IMPLEMENTS]->(Incident) - when action implements fix for incident
    - (ActionItem)-[:ADDRESSES]->(Incident) - when action addresses RCA
    
    Returns count of relationships created.
    """
    relationships_created = 0
    
    # Build mapping of issue_number -> issue_type
    issue_type_map = {}
    for issue in issues:
        number = issue['github_issue_number']
        # Normalize labels: lowercase and replace spaces with dashes
        labels = [l.lower().replace(' ', '-') for l in issue.get('labels', [])]
        
        if 'incident-reported' in labels:
            issue_type_map[number] = 'incident'
        elif 'rca-action-item' in labels or 'rca-action' in labels:
            issue_type_map[number] = 'action'
        elif 'rca-discussed' in labels:
            issue_type_map[number] = 'rca'
    
    # Create relationships
    for issue in issues:
        source_number = issue['github_issue_number']
        source_type = issue_type_map.get(source_number)
        
        if not source_type:
            continue
        
        linked_issues = issue.get('linked_issues', [])
        
        for target_number in linked_issues:
            target_type = issue_type_map.get(target_number)
            
            if not target_type:
                continue
            
            # Determine relationship type
            relationship_type = None
            
            if source_type == 'incident' and target_type == 'rca':
                relationship_type = 'HAS_ANALYSIS'
            elif source_type == 'action' and target_type == 'incident':
                relationship_type = 'IMPLEMENTS'
            elif source_type == 'action' and target_type == 'rca':
                relationship_type = 'ADDRESSES'
            
            if not relationship_type:
                continue
            
            try:
                # Create relationship based on types
                if source_type == 'incident':
                    source_label = 'Incident'
                elif source_type == 'action':
                    source_label = 'ActionItem'
                else:
                    source_label = 'Incident'  # RCA is also incident
                
                if target_type == 'incident' or target_type == 'rca':
                    target_label = 'Incident'
                else:
                    target_label = 'ActionItem'
                
                query = f"""
                MATCH (s:{source_label} {{github_issue_number: $source}})
                MATCH (t:{target_label} {{github_issue_number: $target}})
                MERGE (s)-[r:{relationship_type}]->(t)
                RETURN r
                """
                
                params = {
                    'source': source_number,
                    'target': target_number,
                }
                
                result = client.write(query, params)
                if result:
                    relationships_created += 1
                    logger.info(f"Created {relationship_type} relationship: #{source_number} -> #{target_number}")
                    
            except Exception as e:
                logger.error(f"Failed to create relationship {source_number} -> {target_number}: {e}")
    
    return relationships_created


def transform_issues_to_graph() -> Dict[str, int]:
    """
    Main transformation function.
    
    Loads cached issues and transforms them into Neo4j graph nodes.
    
    Returns:
        Dictionary with statistics: {
            'incidents_created': int,
            'actions_created': int,
            'relationships_created': int,
        }
    """
    logger.info("Starting issue transformation to graph...")
    
    # Load cached issues
    logger.info("Loading cached issues...")
    issues = load_all_cached_issues()
    
    if not issues:
        logger.warning("No cached issues found. Run github_sync first.")
        return {
            'incidents_created': 0,
            'actions_created': 0,
            'relationships_created': 0,
        }
    
    logger.info(f"Loaded {len(issues)} cached issues")
    
    # Get Neo4j client
    client = get_client()
    
    # Track statistics
    incidents_created = 0
    actions_created = 0
    
    # Transform each issue
    for issue in issues:
        # Normalize labels: lowercase and replace spaces with dashes
        labels = [label.lower().replace(' ', '-') for label in issue.get('labels', [])]
        
        # Create Incident nodes
        if 'incident-reported' in labels or 'rca-discussed' in labels:
            if create_incident_node(client, issue):
                incidents_created += 1
        
        # Create ActionItem nodes
        elif 'rca-action-item' in labels or 'rca-action' in labels:
            if create_action_item_node(client, issue):
                actions_created += 1
    
    # Create relationships
    logger.info("Creating relationships between nodes...")
    relationships_created = create_relationships(client, issues)
    
    # Update SyncMetadata node to track sync timestamp
    logger.info("Updating sync metadata...")
    try:
        sync_metadata_query = """
        MERGE (sm:SyncMetadata {id: 'sync_metadata'})
        SET sm.last_sync_at = datetime(),
            sm.last_transform_at = datetime(),
            sm.total_incidents = $incidents,
            sm.total_actions = $actions,
            sm.total_relationships = $relationships,
            sm.total_issues_processed = $total_issues,
            sm.sync_source = 'github_sync',
            sm.updated_at = datetime()
        RETURN sm.id AS id
        """
        
        client.write(sync_metadata_query, {
            'incidents': incidents_created,
            'actions': actions_created,
            'relationships': relationships_created,
            'total_issues': len(issues),
        })
        logger.info("Sync metadata updated successfully")
    except Exception as e:
        logger.error(f"Failed to update sync metadata: {e}")
    
    stats = {
        'incidents_created': incidents_created,
        'actions_created': actions_created,
        'relationships_created': relationships_created,
    }
    
    logger.info(f"Transformation complete: {stats}")
    return stats


def main():
    """Main entry point for CLI usage."""
    # Setup logging
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    
    try:
        stats = transform_issues_to_graph()
        
        print("\n" + "=" * 60)
        print("GitHub Issue Transformation Complete")
        print("=" * 60)
        print(f"Incidents created/updated: {stats['incidents_created']}")
        print(f"Action items created/updated: {stats['actions_created']}")
        print(f"Relationships created: {stats['relationships_created']}")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"Transformation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
