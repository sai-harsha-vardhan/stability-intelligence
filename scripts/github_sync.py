#!/usr/bin/env python3
"""
GitHub Issue Sync Script

Provides bulk and incremental sync of GitHub issues with specific labels:
- rca-discussed
- rca-action-item  
- incident-reported

Usage:
    python github_sync.py bulk          # Full sync
    python github_sync.py incremental   # Sync since last run
    python github_sync.py load          # Load cached issues

Environment:
    GITHUB_TOKEN - GitHub personal access token
    GITHUB_REPO - Repository (default: juspay/hyperswitch)
    GITHUB_LABELS - Comma-separated labels to sync
    GITHUB_CACHE_DIR - Cache directory (default: /app/github-cache)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import urllib.request
import urllib.error


DEFAULT_REPO = "juspay/hyperswitch"
DEFAULT_LABELS = "rca-discussed,rca-action-item,incident-reported"
DEFAULT_CACHE_DIR = "github-cache"
STATE_FILE = "sync_state.json"


def get_env_var(name: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable with optional default."""
    return os.environ.get(name, default)


def get_github_token() -> Optional[str]:
    """Get GitHub token from environment."""
    return get_env_var("GITHUB_TOKEN")


def get_repo() -> str:
    """Get target repository from environment."""
    return get_env_var("GITHUB_REPO", DEFAULT_REPO)


def get_labels() -> List[str]:
    """Get labels to sync from environment."""
    labels_str = get_env_var("GITHUB_LABELS", DEFAULT_LABELS)
    return [label.strip() for label in labels_str.split(",")]


def get_cache_dir() -> Path:
    """Get cache directory from environment."""
    cache_dir = get_env_var("GITHUB_CACHE_DIR", DEFAULT_CACHE_DIR)
    path = Path(cache_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_state_file_path() -> Path:
    """Get path to sync state file."""
    return get_cache_dir() / STATE_FILE


def load_sync_state() -> Dict:
    """Load sync state from disk."""
    state_path = get_state_file_path()
    if state_path.exists():
        with open(state_path, "r") as f:
            return json.load(f)
    return {"last_sync": None, "repos": {}}


def save_sync_state(state: Dict) -> None:
    """Save sync state to disk."""
    state_path = get_state_file_path()
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


def github_api_request(url: str, token: Optional[str] = None) -> Dict:
    """Make authenticated GitHub API request."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise PermissionError("Invalid GitHub token")
        elif e.code == 404:
            raise FileNotFoundError(f"Resource not found: {url}")
        else:
            raise RuntimeError(f"GitHub API error: {e.code} - {e.reason}")
    except urllib.error.URLError as e:
        raise ConnectionError(f"Failed to connect to GitHub: {e.reason}")


def fetch_issues(repo: str, labels: List[str], token: Optional[str] = None, 
                 since: Optional[str] = None, state: str = "all") -> List[Dict]:
    """Fetch issues from GitHub API with pagination."""
    issues = []
    page = 1
    per_page = 100
    
    labels_param = ",".join(labels)
    base_url = f"https://api.github.com/repos/{repo}/issues"
    
    while True:
        params = [
            f"state={state}",
            f"labels={labels_param}",
            f"per_page={per_page}",
            f"page={page}",
        ]
        if since:
            params.append(f"since={since}")
        
        url = f"{base_url}?{'&'.join(params)}"
        
        print(f"Fetching page {page}...")
        page_issues = github_api_request(url, token)
        
        if not page_issues:
            break
        
        issues.extend(page_issues)
        
        if len(page_issues) < per_page:
            break
        
        page += 1
        
        if page > 100:  # Safety limit
            print(f"Warning: Reached safety limit at {len(issues)} issues")
            break
    
    return issues


def fetch_issue_comments(repo: str, issue_number: int, 
                         token: Optional[str] = None) -> List[Dict]:
    """Fetch comments for a specific issue."""
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    
    try:
        return github_api_request(url, token)
    except Exception as e:
        print(f"Warning: Failed to fetch comments for issue #{issue_number}: {e}")
        return []


def fetch_linked_issues(repo: str, issue_number: int,
                        token: Optional[str] = None) -> List[int]:
    """
    Fetch linked issues using timeline API.
    Returns list of linked issue numbers.
    """
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/timeline"
    
    try:
        events = github_api_request(url, token)
        linked = []
        for event in events:
            if event.get("event") in ["cross-referenced", "connected"]:
                if "source" in event and "issue" in event["source"]:
                    linked.append(event["source"]["issue"]["number"])
                elif "issue" in event:
                    linked.append(event["issue"]["number"])
        return linked
    except Exception as e:
        print(f"Warning: Failed to fetch timeline for issue #{issue_number}: {e}")
        return []


def transform_issue(issue: Dict, comments: List[Dict], linked_issues: List[int]) -> Dict:
    """Transform GitHub issue into internal format."""
    labels = [label["name"] for label in issue.get("labels", [])]
    
    transformed = {
        "github_issue_number": issue["number"],
        "title": issue["title"],
        "body": issue["body"] or "",
        "state": issue["state"],
        "created_at": issue["created_at"],
        "updated_at": issue["updated_at"],
        "closed_at": issue.get("closed_at"),
        "labels": labels,
        "author": issue["user"]["login"] if issue.get("user") else None,
        "assignees": [u["login"] for u in issue.get("assignees", [])],
        "milestone": issue["milestone"]["title"] if issue.get("milestone") else None,
        "comments_count": issue.get("comments", 0),
        "comments": [
            {
                "id": c["id"],
                "author": c["user"]["login"] if c.get("user") else None,
                "body": c["body"] or "",
                "created_at": c["created_at"],
            }
            for c in comments
        ],
        "linked_issues": linked_issues,
        "issue_type": infer_issue_type(labels),
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }
    
    return transformed


def infer_issue_type(labels: List[str]) -> str:
    """Infer issue type from labels."""
    if "incident-reported" in labels:
        return "incident"
    elif "rca-discussed" in labels:
        return "rca"
    elif "rca-action-item" in labels:
        return "action_item"
    else:
        return "unknown"


def generate_mock_issues() -> List[Dict]:
    """Generate sample mock issues for testing without GitHub token."""
    now = datetime.now(timezone.utc).isoformat()
    yesterday = datetime.now(timezone.utc).isoformat()
    
    mock_issues = [
        {
            "github_issue_number": 501,
            "title": "INCIDENT-001: Payment gateway timeout causing checkout failures",
            "body": """## Incident Report

**Date:** 2024-01-15
**Severity:** P0
**Affected Flows:** payments, checkout
**Merchant Impact:** 15 merchants affected, $50K GMV at risk

**Description:**
Payment gateway timeouts observed between 14:00-14:45 UTC. Customers unable to complete checkout.

**Resolution:**
Increased timeout from 30s to 60s and added circuit breaker.

**Linked RCA:** #502
            """,
            "state": "closed",
            "created_at": "2024-01-15T14:00:00Z",
            "updated_at": yesterday,
            "closed_at": yesterday,
            "labels": ["incident-reported", "P0", "payment-gateway"],
            "author": "oncall-engineer",
            "assignees": ["sre-lead"],
            "milestone": "Sprint-2024-Q1-3",
            "comments_count": 5,
            "comments": [
                {
                    "id": 1001,
                    "author": "sre-lead",
                    "body": "Circuit breaker implemented and deployed",
                    "created_at": "2024-01-15T15:30:00Z",
                }
            ],
            "linked_issues": [502],
            "issue_type": "incident",
            "synced_at": now,
        },
        {
            "github_issue_number": 502,
            "title": "RCA-001: Root cause analysis for payment gateway timeout",
            "body": """## Root Cause Analysis

**Incident:** INCIDENT-001 (#501)

**Root Cause:**
Payment gateway client's default timeout of 30s was insufficient for peak traffic conditions. Under load, gateway responses exceeded 30s causing cascading failures.

**Category:** timeout | connector_response_drift

**Components Affected:**
- crates/router/src/connector/stripe.rs
- crates/router/src/core/payments.rs

**Action Items:**
- [ ] Increase timeout to 60s (tracking: #503)
- [ ] Implement adaptive timeout based on p99 latency
- [ ] Add circuit breaker pattern

**Learnings:**
Default timeouts should account for peak traffic + 2x safety margin.
            """,
            "state": "closed",
            "created_at": "2024-01-16T09:00:00Z",
            "updated_at": yesterday,
            "closed_at": yesterday,
            "labels": ["rca-discussed", "analysis"],
            "author": "stability-team",
            "assignees": ["architect-lead"],
            "milestone": "Sprint-2024-Q1-3",
            "comments_count": 3,
            "comments": [],
            "linked_issues": [501, 503],
            "issue_type": "rca",
            "synced_at": now,
        },
        {
            "github_issue_number": 503,
            "title": "ACTION-001: Increase payment gateway timeout from 30s to 60s",
            "body": """## Action Item

**Source RCA:** RCA-001 (#502)
**Source Incident:** INCIDENT-001 (#501)

**Description:**
Increase the default timeout for Stripe connector from 30s to 60s to prevent timeout cascades during peak traffic.

**Implementation Details:**
File: `crates/router/src/connector/stripe.rs`
Line: ~145 (timeout constant)

**Complexity:** Low
**Backward Compat Risk:** Low (timeout increase is safe)
**Stagger Safe:** Yes

**Verification:**
- [ ] Unit tests pass
- [ ] Load test confirms no timeout under 2x traffic
            """,
            "state": "open",
            "created_at": "2024-01-16T10:00:00Z",
            "updated_at": yesterday,
            "closed_at": None,
            "labels": ["rca-action-item", "stripe", "timeout"],
            "author": "stability-team",
            "assignees": ["backend-dev-1"],
            "milestone": "Sprint-2024-Q1-4",
            "comments_count": 1,
            "comments": [
                {
                    "id": 1002,
                    "author": "backend-dev-1",
                    "body": "PR opened: #504 - increased timeout and added tests",
                    "created_at": "2024-01-17T11:00:00Z",
                }
            ],
            "linked_issues": [501, 502],
            "issue_type": "action_item",
            "synced_at": now,
        },
    ]
    
    return mock_issues


def save_issues_jsonl(issues: List[Dict], cache_dir: Path, suffix: str = "") -> Path:
    """Save issues to JSONL file."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"github_issues_{timestamp}{suffix}.jsonl"
    filepath = cache_dir / filename
    
    with open(filepath, "w") as f:
        for issue in issues:
            f.write(json.dumps(issue, separators=(",", ":")) + "\n")
    
    return filepath


def bulk_sync(token: Optional[str] = None) -> List[Dict]:
    """
    Perform bulk sync of all GitHub issues with target labels.
    
    Fetches all issues, comments, and linked issues. Saves to JSONL.
    
    Returns:
        List of transformed issues
    """
    repo = get_repo()
    labels = get_labels()
    cache_dir = get_cache_dir()
    
    print(f"Starting bulk sync for {repo}")
    print(f"Target labels: {labels}")
    
    if not token:
        print("WARNING: No GITHUB_TOKEN found. Using mock data.")
        issues = generate_mock_issues()
        
        # Group by label for reporting
        label_counts = {}
        for issue in issues:
            for label in issue["labels"]:
                if label in labels:
                    label_counts[label] = label_counts.get(label, 0) + 1
        
        print(f"\nMock issues generated: {len(issues)}")
        for label, count in label_counts.items():
            print(f"  - {label}: {count}")
        
        filepath = save_issues_jsonl(issues, cache_dir, "_mock")
        print(f"Saved to: {filepath}")
        
        # Update sync state
        state = load_sync_state()
        state["last_sync"] = datetime.now(timezone.utc).isoformat()
        state["repos"][repo] = {
            "last_full_sync": state["last_sync"],
            "issue_count": len(issues),
            "mock": True,
        }
        save_sync_state(state)
        
        return issues
    
    # Real GitHub API sync
    print("Fetching issues from GitHub API...")
    raw_issues = fetch_issues(repo, labels, token)
    print(f"Fetched {len(raw_issues)} issues")
    
    transformed_issues = []
    
    for i, issue in enumerate(raw_issues):
        issue_num = issue["number"]
        print(f"Processing issue #{issue_num} ({i+1}/{len(raw_issues)})...")
        
        # Fetch comments
        comments = fetch_issue_comments(repo, issue_num, token)
        
        # Fetch linked issues
        linked = fetch_linked_issues(repo, issue_num, token)
        
        # Transform
        transformed = transform_issue(issue, comments, linked)
        transformed_issues.append(transformed)
    
    # Save to JSONL
    filepath = save_issues_jsonl(transformed_issues, cache_dir)
    print(f"\nSaved {len(transformed_issues)} issues to: {filepath}")
    
    # Group by label for reporting
    label_counts = {}
    for issue in transformed_issues:
        for label in issue["labels"]:
            if label in labels:
                label_counts[label] = label_counts.get(label, 0) + 1
    
    print("\nIssues per label:")
    for label in labels:
        print(f"  - {label}: {label_counts.get(label, 0)}")
    
    # Update sync state
    state = load_sync_state()
    state["last_sync"] = datetime.now(timezone.utc).isoformat()
    state["repos"][repo] = {
        "last_full_sync": state["last_sync"],
        "issue_count": len(transformed_issues),
        "mock": False,
    }
    save_sync_state(state)
    
    return transformed_issues


def incremental_sync(token: Optional[str] = None) -> List[Dict]:
    """
    Perform incremental sync since last sync timestamp.
    
    Fetches only issues updated since the last sync. Merges with existing cache.
    
    Returns:
        List of newly synced issues
    """
    repo = get_repo()
    labels = get_labels()
    cache_dir = get_cache_dir()
    state = load_sync_state()
    
    last_sync = state.get("last_sync")
    
    print(f"Starting incremental sync for {repo}")
    print(f"Last sync: {last_sync or 'Never'}")
    
    if not token:
        print("WARNING: No GITHUB_TOKEN found. Cannot perform incremental sync.")
        print("Run 'bulk' sync to generate mock data.")
        return []
    
    if not last_sync:
        print("No previous sync found. Run bulk sync first.")
        return []
    
    # Fetch issues updated since last sync
    print(f"Fetching issues updated since {last_sync}...")
    raw_issues = fetch_issues(repo, labels, token, since=last_sync)
    print(f"Fetched {len(raw_issues)} updated issues")
    
    if not raw_issues:
        print("No new or updated issues found.")
        state["last_sync"] = datetime.now(timezone.utc).isoformat()
        save_sync_state(state)
        return []
    
    transformed_issues = []
    
    for i, issue in enumerate(raw_issues):
        issue_num = issue["number"]
        print(f"Processing issue #{issue_num} ({i+1}/{len(raw_issues)})...")
        
        comments = fetch_issue_comments(repo, issue_num, token)
        linked = fetch_linked_issues(repo, issue_num, token)
        transformed = transform_issue(issue, comments, linked)
        transformed_issues.append(transformed)
    
    # Save incremental batch
    filepath = save_issues_jsonl(transformed_issues, cache_dir, "_incremental")
    print(f"\nSaved {len(transformed_issues)} issues to: {filepath}")
    
    # Update sync state
    state["last_sync"] = datetime.now(timezone.utc).isoformat()
    if repo in state["repos"]:
        state["repos"][repo]["last_incremental_sync"] = state["last_sync"]
        state["repos"][repo]["incremental_count"] = (
            state["repos"][repo].get("incremental_count", 0) + len(transformed_issues)
        )
    save_sync_state(state)
    
    return transformed_issues


def load_all_cached_issues() -> List[Dict]:
    """
    Load all cached issues from JSONL files.
    
    Returns:
        Combined list of all issues from all cache files
    """
    cache_dir = get_cache_dir()
    
    print(f"Loading cached issues from {cache_dir}")
    
    all_issues = []
    jsonl_files = sorted(cache_dir.glob("*.jsonl"))
    
    if not jsonl_files:
        print("No cached JSONL files found.")
        return []
    
    for filepath in jsonl_files:
        print(f"Loading {filepath.name}...")
        count = 0
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        issue = json.loads(line)
                        all_issues.append(issue)
                        count += 1
                    except json.JSONDecodeError as e:
                        print(f"  Warning: Invalid JSON in {filepath.name}: {e}")
        print(f"  Loaded {count} issues")
    
    # Deduplicate by issue number (keep most recent)
    seen = {}
    for issue in all_issues:
        num = issue["github_issue_number"]
        if num not in seen:
            seen[num] = issue
        else:
            # Keep the one with later synced_at
            if issue["synced_at"] > seen[num]["synced_at"]:
                seen[num] = issue
    
    deduped = list(seen.values())
    print(f"\nTotal unique issues: {len(deduped)} (from {len(all_issues)} total)")
    
    return deduped


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nUsage: python github_sync.py <command>")
        print("Commands: bulk, incremental, load")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    token = get_github_token()
    
    if command == "bulk":
        issues = bulk_sync(token)
        print(f"\nSync complete. Total issues: {len(issues)}")
        
    elif command == "incremental":
        issues = incremental_sync(token)
        print(f"\nIncremental sync complete. New/updated issues: {len(issues)}")
        
    elif command == "load":
        issues = load_all_cached_issues()
        
        # Print summary
        by_type = {}
        for issue in issues:
            t = issue.get("issue_type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        
        print("\nSummary by type:")
        for t, count in sorted(by_type.items()):
            print(f"  - {t}: {count}")
            
    else:
        print(f"Unknown command: {command}")
        print("Commands: bulk, incremental, load")
        sys.exit(1)


if __name__ == "__main__":
    main()
