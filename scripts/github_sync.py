#!/usr/bin/env python3
"""
GitHub Issue Sync Script - GitHub CLI Edition

Provides bulk and incremental sync of GitHub issues with specific labels:
- rca-discussed
- rca-action-item  
- incident-reported

Uses GitHub CLI (gh) for all API operations.

Usage:
    python github_sync.py bulk          # Full sync
    python github_sync.py incremental   # Sync since last run
    python github_sync.py load          # Load cached issues

Environment:
    GITHUB_REPO - Repository (default: juspay/hyperswitch)
    GITHUB_LABELS - Comma-separated labels to sync
    GITHUB_CACHE_DIR - Cache directory (default: /app/github-cache)
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_REPO = "juspay/hyperswitch-cloud"
DEFAULT_LABELS = "Incident Reported,RCA-Action,RCA Discussed,RCA Prepared,Incident Mitigated"
DEFAULT_CACHE_DIR = "github-cache"
STATE_FILE = "sync_state.json"


def get_env_var(name: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable with optional default."""
    return os.environ.get(name, default)


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


def run_gh_command(args: List[str], repo: str) -> Dict:
    """Execute a gh CLI command and return JSON output."""
    # gh api doesn't support --repo flag, only gh issue/pr commands do
    if args[0] == "api":
        cmd = ["gh"] + args
    else:
        cmd = ["gh"] + args + ["--repo", repo]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=True
        )
        return json.loads(result.stdout) if result.stdout else {}
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"gh command timed out: {' '.join(cmd)}")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.lower() if e.stderr else ""
        if "401" in error_msg or "authentication" in error_msg:
            raise PermissionError("GitHub authentication failed. Run 'gh auth login'")
        elif "404" in error_msg:
            raise FileNotFoundError(f"Resource not found in {repo}")
        else:
            raise RuntimeError(f"gh command failed: {e.stderr or e.stdout}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse gh output as JSON: {e}")


def fetch_issues(repo: str, labels: List[str],
                 since: Optional[str] = None, state: str = "all") -> List[Dict]:
    """Fetch issues from GitHub using gh CLI with pagination.
    
    Fetches issues for EACH label separately (OR logic) and deduplicates by issue number.
    """
    # Dictionary to store unique issues by issue number
    unique_issues = {}
    
    # gh issue list only supports open/closed, not "all"
    # We'll fetch both and combine
    states_to_fetch = ["open", "closed"] if state == "all" else [state]
    
    # Fetch issues for EACH label separately (OR logic)
    for label in labels:
        print(f"\nFetching issues with label: {label}", flush=True)
        
        for issue_state in states_to_fetch:
            print(f"  Fetching {issue_state} issues...", flush=True)
            
            # Build gh issue list command with SINGLE label
            # Note: gh CLI --limit only sets max results, not pagination
            # We use a high limit to get all issues at once (max is 1000)
            args = [
                "issue", "list",
                "--state", issue_state,
                "--label", label,  # Single label for OR logic
                "--limit", "1000",  # Maximum allowed by gh CLI
                "--json", "number,title,body,state,createdAt,updatedAt,closedAt,labels,author,assignees,milestone,comments"
            ]
            
            try:
                page_issues = run_gh_command(args, repo)
                
                # Ensure we got a list
                if not isinstance(page_issues, list):
                    print(f"  Warning: Expected list but got {type(page_issues)}", flush=True)
                    page_issues = []
                    
            except RuntimeError as e:
                if "no issues" in str(e).lower() or "not found" in str(e).lower():
                    page_issues = []
                else:
                    raise
            
            print(f"  Fetched {len(page_issues)} {issue_state} issues", flush=True)
            
            # Convert gh CLI field names to match old API format
            for issue in page_issues:
                issue_number = issue["number"]
                
                converted = {
                    "number": issue_number,
                    "title": issue["title"],
                    "body": issue.get("body", ""),
                    "state": issue["state"],
                    "created_at": issue["createdAt"],
                    "updated_at": issue["updatedAt"],
                    "closed_at": issue.get("closedAt"),
                    "labels": [{"name": lbl["name"]} for lbl in issue.get("labels", [])],
                    "user": issue.get("author", {}),
                    "assignees": issue.get("assignees", []),
                    "milestone": issue.get("milestone"),
                    "comments": issue.get("comments", 0),
                }
                
                # Filter by since date if provided
                if since:
                    issue_updated = datetime.fromisoformat(converted["updated_at"].replace("Z", "+00:00"))
                    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                    if issue_updated < since_dt:
                        continue
                
                # Store in unique_issues dict (deduplicate by issue number)
                if issue_number not in unique_issues:
                    unique_issues[issue_number] = converted
        
        print(f"  Total unique issues so far: {len(unique_issues)}", flush=True)
    
    issues = list(unique_issues.values())
    print(f"\nTotal unique issues found: {len(issues)}", flush=True)
    
    return issues


def fetch_issue_comments(repo: str, issue_number: int) -> List[Dict]:
    """Fetch comments for a specific issue using gh CLI."""
    try:
        args = [
            "api",
            f"repos/{repo}/issues/{issue_number}/comments",
            "--paginate"
        ]
        comments = run_gh_command(args, repo)
        
        if not isinstance(comments, list):
            return []
        
        # Normalize field names
        return [{
            "id": c["id"],
            "body": c.get("body", ""),
            "user": c.get("user", {}),
            "created_at": c["created_at"],
        } for c in comments]
    except Exception as e:
        print(f"Warning: Failed to fetch comments for issue #{issue_number}: {e}")
        return []


def fetch_linked_issues(repo: str, issue_number: int) -> List[int]:
    """
    Fetch linked issues using timeline API via gh CLI.
    Returns list of linked issue numbers.
    """
    try:
        args = [
            "api",
            f"repos/{repo}/issues/{issue_number}/timeline",
            "--paginate"
        ]
        events = run_gh_command(args, repo)
        
        if not isinstance(events, list):
            return []
        
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
    
    user = issue.get("user", {}) or {}
    assignees = issue.get("assignees", []) or []
    milestone = issue.get("milestone")
    
    transformed = {
        "github_issue_number": issue["number"],
        "title": issue["title"],
        "body": issue["body"] or "",
        "state": issue["state"],
        "created_at": issue["created_at"],
        "updated_at": issue["updated_at"],
        "closed_at": issue.get("closed_at"),
        "labels": labels,
        "author": user.get("login") if user else None,
        "assignees": [u.get("login") for u in assignees if u],
        "milestone": milestone.get("title") if isinstance(milestone, dict) else milestone,
        "comments_count": issue.get("comments", 0),
        "comments": [
            {
                "id": c["id"],
                "author": c.get("user", {}).get("login") if c.get("user") else None,
                "body": c.get("body", "") or "",
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
    # Convert to lowercase for case-insensitive matching
    labels_lower = [label.lower() for label in labels]
    
    if "incident reported" in labels_lower or "incident-reported" in labels_lower:
        return "incident"
    elif "rca discussed" in labels_lower or "rca-discussed" in labels_lower:
        return "rca"
    elif "rca prepared" in labels_lower or "rca-prepared" in labels_lower:
        return "rca"
    elif "rca-action" in labels_lower or "rca-action-item" in labels_lower:
        return "action_item"
    elif "incident mitigated" in labels_lower or "incident-mitigated" in labels_lower:
        return "incident"
    else:
        return "unknown"


def generate_mock_issues() -> List[Dict]:
    """Generate sample mock issues for testing without GitHub access."""
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


def check_gh_installed() -> bool:
    """Check if gh CLI is installed and accessible."""
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def check_gh_authenticated() -> bool:
    """Check if gh CLI is authenticated."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0 and "Logged in" in result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def bulk_sync() -> List[Dict]:
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
    
    # Check gh CLI availability
    if not check_gh_installed():
        print("WARNING: gh CLI not found. Using mock data.")
        print("Install gh CLI: https://cli.github.com/")
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
    
    if not check_gh_authenticated():
        print("WARNING: gh CLI not authenticated. Using mock data.")
        print("Authenticate with: gh auth login")
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
    
    # Real GitHub sync via gh CLI
    print("Fetching issues from GitHub using gh CLI...")
    raw_issues = fetch_issues(repo, labels)
    print(f"Fetched {len(raw_issues)} issues")
    
    transformed_issues = []
    
    for i, issue in enumerate(raw_issues):
        issue_num = issue["number"]
        print(f"Processing issue #{issue_num} ({i+1}/{len(raw_issues)})...")
        
        # Fetch comments
        comments = fetch_issue_comments(repo, issue_num)
        
        # Fetch linked issues
        linked = fetch_linked_issues(repo, issue_num)
        
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


def incremental_sync() -> List[Dict]:
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
    
    # Check gh CLI availability
    if not check_gh_installed():
        print("WARNING: gh CLI not found. Cannot perform incremental sync.")
        print("Run 'bulk' sync to generate mock data.")
        return []
    
    if not check_gh_authenticated():
        print("WARNING: gh CLI not authenticated. Cannot perform incremental sync.")
        print("Authenticate with: gh auth login")
        return []
    
    if not last_sync:
        print("No previous sync found. Run bulk sync first.")
        return []
    
    # Fetch issues updated since last sync
    print(f"Fetching issues updated since {last_sync}...")
    raw_issues = fetch_issues(repo, labels, since=last_sync)
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
        
        comments = fetch_issue_comments(repo, issue_num)
        linked = fetch_linked_issues(repo, issue_num)
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
    
    if command == "bulk":
        issues = bulk_sync()
        print(f"\nSync complete. Total issues: {len(issues)}")
        
    elif command == "incremental":
        issues = incremental_sync()
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
