#!/usr/bin/env python3
"""
Link Resolver Script

Maps relationships between GitHub issues:
- rca-discussed -> incident-reported (incident that triggered RCA)
- rca-discussed -> rca-action-item (actions from RCA)
- incident-reported -> rca-discussed (RCA created for incident)

Usage:
    python link_resolver.py --input github-cache/github_issues_*.jsonl
    python link_resolver.py --input github-cache/ --output links.json

The resolver uses multiple signals:
1. Explicit linked_issues from GitHub API timeline
2. Body text pattern matching ("Related to #123", "Fixes #456")
3. Milestone matching (same milestone = likely related)
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple


def extract_issue_references(text: str) -> Set[int]:
    """
    Extract issue number references from text.
    
    Matches patterns like:
    - #123
    - fixes #123
    - related to #123
    - closes #123
    - GH-123
    - resolves #123
    """
    if not text:
        return set()
    
    patterns = [
        r'#(\d+)',  # Simple #123
        r'(?:fixes|fix|closes|close|resolves|resolve|related to|refs|references?)\s*:?\s*#(\d+)',
        r'GH-(\d+)',
        r'github\.com/[^/]+/[^/]+/issues/(\d+)',
    ]
    
    refs = set()
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        refs.update(int(m) if isinstance(m, str) else int(m[0]) for m in matches)
    
    return refs


def find_rca_to_incident_links(issues: List[Dict]) -> List[Tuple[int, int]]:
    """
    Map RCA discussions to their source incidents.
    
    Returns list of (rca_issue_number, incident_issue_number) tuples.
    
    Signals:
    1. Explicit linked_issues in RCA pointing to incident
    2. Body text mentioning "Incident" followed by issue ref
    3. Same milestone + RCA created after incident
    """
    links = []
    
    # Build lookup maps
    rca_issues = {i["github_issue_number"]: i for i in issues 
                  if i.get("issue_type") == "rca"}
    incident_issues = {i["github_issue_number"]: i for i in issues 
                       if i.get("issue_type") == "incident"}
    
    for rca_num, rca in rca_issues.items():
        linked_incidents = set()
        
        # Signal 1: Explicit linked issues
        for linked_num in rca.get("linked_issues", []):
            if linked_num in incident_issues:
                linked_incidents.add(linked_num)
        
        # Signal 2: Body text patterns
        body = rca.get("body", "")
        refs = extract_issue_references(body)
        for ref in refs:
            if ref in incident_issues:
                linked_incidents.add(ref)
        
        # Signal 3: Title patterns like "RCA-XXX: Analysis of INCIDENT-YYY"
        title = rca.get("title", "")
        title_refs = extract_issue_references(title)
        for ref in title_refs:
            if ref in incident_issues and ref != rca_num:
                linked_incidents.add(ref)
        
        # Create links
        for incident_num in linked_incidents:
            links.append((rca_num, incident_num))
    
    return links


def find_rca_to_action_item_links(issues: List[Dict]) -> List[Tuple[int, int]]:
    """
    Map RCAs to their action items.
    
    Returns list of (rca_issue_number, action_item_issue_number) tuples.
    
    Signals:
    1. Explicit linked_issues in action item pointing to RCA
    2. Action item body mentioning RCA
    3. Same milestone + action item created after RCA
    4. Title pattern matching
    """
    links = []
    
    # Build lookup maps
    rca_issues = {i["github_issue_number"]: i for i in issues 
                  if i.get("issue_type") == "rca"}
    action_items = {i["github_issue_number"]: i for i in issues 
                    if i.get("issue_type") == "action_item"}
    
    for action_num, action in action_items.items():
        linked_rcas = set()
        
        # Signal 1: Explicit linked issues
        for linked_num in action.get("linked_issues", []):
            if linked_num in rca_issues:
                linked_rcas.add(linked_num)
        
        # Signal 2: Body text patterns
        body = action.get("body", "")
        refs = extract_issue_references(body)
        for ref in refs:
            if ref in rca_issues and ref != action_num:
                linked_rcas.add(ref)
        
        # Signal 3: Title patterns (e.g., "ACTION-001: Fix from RCA-XXX")
        title = action.get("title", "")
        title_refs = extract_issue_references(title)
        for ref in title_refs:
            if ref in rca_issues and ref != action_num:
                linked_rcas.add(ref)
        
        # Signal 4: Milestone matching (action item same milestone as RCA, created after)
        action_milestone = action.get("milestone")
        action_created = action.get("created_at", "")
        
        if action_milestone and not linked_rcas:
            for rca_num, rca in rca_issues.items():
                if (rca.get("milestone") == action_milestone and 
                    rca.get("created_at", "") < action_created and
                    rca_num != action_num):
                    # Weak signal - use only if no stronger signals
                    if not linked_rcas:
                        linked_rcas.add(rca_num)
        
        # Create links (reverse direction: RCA -> action item)
        for rca_num in linked_rcas:
            links.append((rca_num, action_num))
    
    return links


def find_incident_to_rca_links(issues: List[Dict]) -> List[Tuple[int, int]]:
    """
    Map incidents to RCAs created for them.
    
    This is essentially the inverse of rca_to_incident.
    """
    # Reuse rca_to_incident logic and invert
    rca_to_incident = find_rca_to_incident_links(issues)
    return [(incident, rca) for rca, incident in rca_to_incident]


def build_link_graph(issues: List[Dict]) -> Dict:
    """
    Build complete link graph between all issue types.
    
    Returns dict with:
    - rca_to_incident: RCA discussions -> source incidents
    - rca_to_action_item: RCAs -> action items
    - incident_to_rca: Incidents -> RCAs
    - unresolved_actions: Action items without RCA link
    - unmapped_incidents: Incidents without RCA
    """
    print("Building link graph...")
    
    # Find all link types
    rca_to_incident = find_rca_to_incident_links(issues)
    rca_to_action_item = find_rca_to_action_item_links(issues)
    incident_to_rca = find_incident_to_rca_links(issues)
    
    # Find unmapped items
    rca_nums = {i["github_issue_number"] for i in issues if i.get("issue_type") == "rca"}
    incident_nums = {i["github_issue_number"] for i in issues if i.get("issue_type") == "incident"}
    action_nums = {i["github_issue_number"] for i in issues if i.get("issue_type") == "action_item"}
    
    mapped_incidents = {link[1] for link in rca_to_incident}
    mapped_rcas = {link[0] for link in rca_to_incident}
    mapped_actions = {link[1] for link in rca_to_action_item}
    
    unmapped_incidents = list(incident_nums - mapped_incidents)
    unresolved_actions = list(action_nums - mapped_actions)
    unmapped_rcas = list(rca_nums - mapped_rcas)
    
    # Build detailed link info
    issue_map = {i["github_issue_number"]: i for i in issues}
    
    detailed_rca_to_incident = [
        {
            "rca_issue_number": rca,
            "rca_title": issue_map.get(rca, {}).get("title", "Unknown"),
            "incident_issue_number": incident,
            "incident_title": issue_map.get(incident, {}).get("title", "Unknown"),
        }
        for rca, incident in rca_to_incident
    ]
    
    detailed_rca_to_action = [
        {
            "rca_issue_number": rca,
            "rca_title": issue_map.get(rca, {}).get("title", "Unknown"),
            "action_item_number": action,
            "action_title": issue_map.get(action, {}).get("title", "Unknown"),
        }
        for rca, action in rca_to_action_item
    ]
    
    return {
        "summary": {
            "total_issues": len(issues),
            "rca_count": len(rca_nums),
            "incident_count": len(incident_nums),
            "action_item_count": len(action_nums),
            "rca_to_incident_links": len(rca_to_incident),
            "rca_to_action_item_links": len(rca_to_action_item),
            "unmapped_incidents": unmapped_incidents,
            "unmapped_rcas": unmapped_rcas,
            "unresolved_actions": unresolved_actions,
        },
        "rca_to_incident": detailed_rca_to_incident,
        "rca_to_action_item": detailed_rca_to_action,
        "incident_to_rca": [
            {
                "incident_issue_number": incident,
                "incident_title": issue_map.get(incident, {}).get("title", "Unknown"),
                "rca_issue_number": rca,
                "rca_title": issue_map.get(rca, {}).get("title", "Unknown"),
            }
            for incident, rca in incident_to_rca
        ],
    }


def load_issues_from_jsonl(files: List[Path]) -> List[Dict]:
    """Load issues from JSONL file(s)."""
    issues = []
    
    for filepath in files:
        print(f"Loading {filepath}...")
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        issue = json.loads(line)
                        issues.append(issue)
                    except json.JSONDecodeError as e:
                        print(f"  Warning: Invalid JSON: {e}")
    
    # Deduplicate by issue number
    seen = {}
    for issue in issues:
        num = issue.get("github_issue_number")
        if num and (num not in seen or issue.get("synced_at", "") > seen[num].get("synced_at", "")):
            seen[num] = issue
    
    return list(seen.values())


def find_jsonl_files(path: Path) -> List[Path]:
    """Find all JSONL files in directory or return single file."""
    if path.is_file():
        return [path]
    elif path.is_dir():
        return list(path.glob("*.jsonl"))
    else:
        # Try glob pattern
        return list(Path(".").glob(str(path)))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Resolve links between GitHub issues (RCA, incidents, action items)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python link_resolver.py --input github-cache/
  python link_resolver.py --input github-cache/github_issues_*.jsonl
  python link_resolver.py --input issues.jsonl --output links.json
        """
    )
    
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input JSONL file(s) or directory containing JSONL files"
    )
    parser.add_argument(
        "--output", "-o",
        default="links.json",
        help="Output JSON file for link graph (default: links.json)"
    )
    parser.add_argument(
        "--pretty", "-p",
        action="store_true",
        help="Pretty-print JSON output"
    )
    
    args = parser.parse_args()
    
    # Find input files
    input_path = Path(args.input)
    files = find_jsonl_files(input_path)
    
    if not files:
        print(f"Error: No JSONL files found at {args.input}")
        sys.exit(1)
    
    print(f"Found {len(files)} JSONL file(s)")
    
    # Load issues
    issues = load_issues_from_jsonl(files)
    print(f"Loaded {len(issues)} unique issues")
    
    if not issues:
        print("Error: No issues loaded")
        sys.exit(1)
    
    # Build link graph
    graph = build_link_graph(issues)
    
    # Print summary
    summary = graph["summary"]
    print("\n" + "="*50)
    print("LINK RESOLUTION SUMMARY")
    print("="*50)
    print(f"Total issues: {summary['total_issues']}")
    print(f"  - RCAs: {summary['rca_count']}")
    print(f"  - Incidents: {summary['incident_count']}")
    print(f"  - Action items: {summary['action_item_count']}")
    print()
    print(f"Links found:")
    print(f"  - RCA → Incident: {summary['rca_to_incident_links']}")
    print(f"  - RCA → Action Item: {summary['rca_to_action_item_links']}")
    print()
    
    if summary['unmapped_incidents']:
        print(f"⚠️  Unmapped incidents: {len(summary['unmapped_incidents'])}")
        for num in summary['unmapped_incidents'][:5]:
            issue = next((i for i in issues if i['github_issue_number'] == num), None)
            if issue:
                print(f"     #{num}: {issue.get('title', 'Unknown')[:60]}...")
        if len(summary['unmapped_incidents']) > 5:
            print(f"     ... and {len(summary['unmapped_incidents']) - 5} more")
    else:
        print("✓ All incidents mapped to RCAs")
    
    if summary['unresolved_actions']:
        print(f"⚠️  Action items without RCA: {len(summary['unresolved_actions'])}")
        for num in summary['unresolved_actions'][:5]:
            issue = next((i for i in issues if i['github_issue_number'] == num), None)
            if issue:
                print(f"     #{num}: {issue.get('title', 'Unknown')[:60]}...")
        if len(summary['unresolved_actions']) > 5:
            print(f"     ... and {len(summary['unresolved_actions']) - 5} more")
    else:
        print("✓ All action items linked to RCAs")
    
    # Save output
    output_path = Path(args.output)
    indent = 2 if args.pretty else None
    
    with open(output_path, "w") as f:
        json.dump(graph, f, indent=indent, separators=(",", ":") if not args.pretty else None)
    
    print(f"\nSaved link graph to: {output_path}")
    print(f"Output size: {output_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
