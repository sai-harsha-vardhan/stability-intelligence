#!/usr/bin/env python3
"""
Repository Clone and Sync Script

Manages the Hyperswitch repository:
- Clones repo if not present
- Pulls latest changes if repo exists
- Returns current commit hash
- Supports shallow clone for faster initial setup

Usage:
    python repo_clone.py clone          # Clone or update repo
    python repo_clone.py status         # Show repo status
    python repo_clone.py commit-hash    # Get current commit hash
    python repo_clone.py changes        # Get files changed since last sync

Environment:
    HYPERSWITCH_REPO_PATH - Local path for repo (default: /app/hyperswitch-repo)
    GITHUB_REPO - Repository to clone (default: juspay/hyperswitch)
    GIT_DEPTH - Shallow clone depth (default: 100, 0 for full)
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, List, Tuple


DEFAULT_REPO_PATH = "hyperswitch-repo"
DEFAULT_GITHUB_REPO = "juspay/hyperswitch"
DEFAULT_DEPTH = 100
STATE_FILE = ".repo_sync_state"


def get_repo_path() -> Path:
    """Get repository path from environment."""
    path = os.environ.get("HYPERSWITCH_REPO_PATH", DEFAULT_REPO_PATH)
    return Path(path)


def get_github_repo() -> str:
    """Get GitHub repository from environment."""
    return os.environ.get("GITHUB_REPO", DEFAULT_GITHUB_REPO)


def get_depth() -> int:
    """Get clone depth from environment."""
    depth_str = os.environ.get("GIT_DEPTH", str(DEFAULT_DEPTH))
    return int(depth_str)


def run_git_command(args: List[str], cwd: Optional[Path] = None, 
                    check: bool = True) -> Tuple[int, str, str]:
    """
    Run a git command and return (returncode, stdout, stderr).
    
    Args:
        args: Git command arguments
        cwd: Working directory (default: repo path)
        check: If True, raises exception on non-zero exit
    
    Returns:
        Tuple of (returncode, stdout, stderr)
    """
    if cwd is None:
        cwd = get_repo_path()
    
    cmd = ["git"] + args
    
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False
        )
        
        if check and result.returncode != 0:
            raise RuntimeError(
                f"Git command failed: {' '.join(cmd)}\n"
                f"Exit code: {result.returncode}\n"
                f"Stderr: {result.stderr}"
            )
        
        return result.returncode, result.stdout.strip(), result.stderr.strip()
        
    except FileNotFoundError:
        raise RuntimeError("Git not found in PATH. Please install git.")


def is_repo_present() -> bool:
    """Check if repository is already cloned."""
    repo_path = get_repo_path()
    git_dir = repo_path / ".git"
    return git_dir.exists() and git_dir.is_dir()


def clone_repo(shallow: bool = True) -> Path:
    """
    Clone the Hyperswitch repository.
    
    Args:
        shallow: If True, performs shallow clone with depth limit
    
    Returns:
        Path to cloned repository
    """
    repo_path = get_repo_path()
    github_repo = get_github_repo()
    
    if is_repo_present():
        print(f"Repository already exists at {repo_path}")
        return repo_path
    
    # Ensure parent directory exists
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Cloning {github_repo}...")
    print(f"Destination: {repo_path}")
    
    url = f"https://github.com/{github_repo}.git"
    
    if shallow:
        depth = get_depth()
        if depth > 0:
            print(f"Shallow clone with depth {depth}")
            run_git_command(
                ["clone", "--depth", str(depth), url, str(repo_path)],
                cwd=repo_path.parent,
                check=True
            )
        else:
            print("Full clone (depth=0)")
            run_git_command(
                ["clone", url, str(repo_path)],
                cwd=repo_path.parent,
                check=True
            )
    else:
        print("Full clone")
        run_git_command(
            ["clone", url, str(repo_path)],
            cwd=repo_path.parent,
            check=True
        )
    
    print(f"✓ Repository cloned successfully")
    
    # Save sync state
    save_sync_state({
        "cloned_at": get_current_timestamp(),
        "commit_hash": get_commit_hash(),
        "github_repo": github_repo,
    })
    
    return repo_path


def pull_updates() -> Tuple[bool, str]:
    """
    Pull latest changes from remote.
    
    Returns:
        Tuple of (success, message)
    """
    if not is_repo_present():
        return False, "Repository not found. Run clone first."
    
    repo_path = get_repo_path()
    print(f"Updating repository at {repo_path}")
    
    try:
        # Check if we can fast-forward
        _, local_hash, _ = run_git_command(["rev-parse", "HEAD"])
        
        # Fetch updates
        print("Fetching updates from remote...")
        run_git_command(["fetch", "origin"], check=True)
        
        # Get remote hash
        _, remote_hash, _ = run_git_command(["rev-parse", "origin/HEAD"])
        
        if local_hash == remote_hash:
            print("Already up to date")
            return True, "Already up to date"
        
        # Pull updates
        print(f"Pulling changes: {local_hash[:8]}..{remote_hash[:8]}")
        run_git_command(["pull", "--ff-only", "origin"], check=True)
        
        # Get new commit hash
        new_hash = get_commit_hash()
        
        # Save sync state
        save_sync_state({
            "last_pull": get_current_timestamp(),
            "commit_hash": new_hash,
            "previous_hash": local_hash,
        })
        
        print(f"✓ Updated to {new_hash[:8]}")
        return True, f"Updated to {new_hash}"
        
    except RuntimeError as e:
        print(f"✗ Pull failed: {e}")
        return False, str(e)


def get_commit_hash(short: bool = False) -> str:
    """
    Get current commit hash.
    
    Args:
        short: If True, returns short hash (8 chars)
    
    Returns:
        Commit hash string
    """
    args = ["rev-parse"]
    if short:
        args.append("--short")
    args.append("HEAD")
    
    _, stdout, _ = run_git_command(args, check=True)
    return stdout


def get_branch() -> str:
    """Get current branch name."""
    _, stdout, _ = run_git_command(["branch", "--show-current"], check=True)
    return stdout


def get_remote_url() -> str:
    """Get remote origin URL."""
    _, stdout, _ = run_git_command(["remote", "get-url", "origin"], check=True)
    return stdout


def get_last_commit_info() -> dict:
    """Get information about the last commit."""
    _, stdout, _ = run_git_command([
        "log", "-1", 
        "--format=%H|%an|%ae|%ad|%s",
        "--date=iso"
    ], check=True)
    
    parts = stdout.split("|", 4)
    return {
        "hash": parts[0],
        "author_name": parts[1],
        "author_email": parts[2],
        "date": parts[3],
        "subject": parts[4] if len(parts) > 4 else "",
    }


def get_changed_files(since_ref: Optional[str] = None) -> List[str]:
    """
    Get list of files changed since last sync or given ref.
    
    Args:
        since_ref: Git ref to compare against (default: last sync state)
    
    Returns:
        List of changed file paths
    """
    if since_ref is None:
        state = load_sync_state()
        since_ref = state.get("commit_hash")
    
    if not since_ref:
        # No previous state, return all tracked files
        _, stdout, _ = run_git_command([
            "ls-tree", "-r", "HEAD", "--name-only"
        ], check=True)
        return stdout.split("\n") if stdout else []
    
    # Get files changed between refs
    current = get_commit_hash()
    
    if current == since_ref:
        return []
    
    _, stdout, _ = run_git_command([
        "diff", "--name-only", f"{since_ref}..{current}"
    ], check=True)
    
    return stdout.split("\n") if stdout else []


def get_file_content(path: str, ref: str = "HEAD") -> str:
    """
    Get content of a file at specific ref.
    
    Args:
        path: File path relative to repo root
        ref: Git ref (default: HEAD)
    
    Returns:
        File content as string
    """
    _, stdout, _ = run_git_command([
        "show", f"{ref}:{path}"
    ], check=True)
    return stdout


def get_repo_status() -> dict:
    """Get comprehensive repository status."""
    if not is_repo_present():
        return {
            "present": False,
            "message": "Repository not found",
        }
    
    try:
        return {
            "present": True,
            "path": str(get_repo_path()),
            "remote": get_remote_url(),
            "branch": get_branch(),
            "commit_hash": get_commit_hash(),
            "commit_hash_short": get_commit_hash(short=True),
            "last_commit": get_last_commit_info(),
        }
    except RuntimeError as e:
        return {
            "present": True,
            "error": str(e),
        }


def save_sync_state(state: dict):
    """Save sync state to repo directory."""
    repo_path = get_repo_path()
    state_path = repo_path / STATE_FILE
    
    import json
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


def load_sync_state() -> dict:
    """Load sync state from repo directory."""
    repo_path = get_repo_path()
    state_path = repo_path / STATE_FILE
    
    if state_path.exists():
        import json
        with open(state_path, "r") as f:
            return json.load(f)
    return {}


def get_current_timestamp() -> str:
    """Get current ISO timestamp."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def clone_or_update() -> Tuple[Path, str]:
    """
    Clone repo if missing, or pull updates if present.
    
    Returns:
        Tuple of (repo_path, commit_hash)
    """
    if is_repo_present():
        success, message = pull_updates()
        if not success:
            print(f"Warning: {message}")
    else:
        clone_repo(shallow=True)
    
    return get_repo_path(), get_commit_hash()


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nUsage: python repo_clone.py <command>")
        print("Commands: clone, status, commit-hash, changes, pull")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    try:
        if command == "clone":
            clone_repo(shallow=True)
            print(f"\nCurrent commit: {get_commit_hash(short=True)}")
            
        elif command == "status":
            status = get_repo_status()
            
            if not status.get("present"):
                print(f"Repository not found at {get_repo_path()}")
                print("Run: python repo_clone.py clone")
                sys.exit(1)
            
            print("Repository Status")
            print("="*50)
            print(f"Path:   {status['path']}")
            print(f"Remote: {status['remote']}")
            print(f"Branch: {status['branch']}")
            print(f"Commit: {status['commit_hash_short']} ({status['commit_hash'][:16]}...)")
            
            if "last_commit" in status:
                commit = status["last_commit"]
                print(f"\nLast commit:")
                print(f"  Author: {commit['author_name']} <{commit['author_email']}>")
                print(f"  Date:   {commit['date']}")
                print(f"  Message: {commit['subject'][:60]}...")
            
            # Show sync state
            state = load_sync_state()
            if state:
                print(f"\nSync state:")
                if "cloned_at" in state:
                    print(f"  Cloned: {state['cloned_at']}")
                if "last_pull" in state:
                    print(f"  Last pull: {state['last_pull']}")
                    
        elif command == "commit-hash":
            if not is_repo_present():
                print("Repository not found")
                sys.exit(1)
            
            short = "--short" in sys.argv
            print(get_commit_hash(short=short))
            
        elif command == "changes":
            if not is_repo_present():
                print("Repository not found")
                sys.exit(1)
            
            state = load_sync_state()
            since = state.get("commit_hash") if state else None
            
            changed = get_changed_files(since)
            
            if changed:
                print(f"Files changed since {since[:8] if since else 'beginning'}:")
                for f in changed[:20]:
                    print(f"  - {f}")
                if len(changed) > 20:
                    print(f"  ... and {len(changed) - 20} more")
                print(f"\nTotal: {len(changed)} files")
            else:
                print("No files changed")
                
        elif command == "pull":
            if not is_repo_present():
                print("Repository not found. Run 'clone' first.")
                sys.exit(1)
            
            success, message = pull_updates()
            if success:
                print(message)
            else:
                print(f"Failed: {message}")
                sys.exit(1)
                
        else:
            print(f"Unknown command: {command}")
            print("Commands: clone, status, commit-hash, changes, pull")
            sys.exit(1)
            
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
