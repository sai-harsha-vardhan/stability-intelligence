#!/usr/bin/env python3
"""
Neo4j Ingestion Script

Reads GitHub issues from JSONL cache and upserts them into Neo4j as typed nodes:
- Incident   (issue_type == "incident")
- RCA        (issue_type == "rca")
- ActionItem (issue_type == "action_item")

Key fix: extracts `assignees[0]` from the cached issue and stores it as the
`assignee` property on ActionItem nodes so the dashboard can display who owns
each action item.

Usage:
    python neo4j_ingestion.py          # Ingest all cached JSONL files
    python neo4j_ingestion.py --dry-run  # Print what would be ingested

Environment:
    NEO4J_URI      - Neo4j connection URI  (default: bolt://neo4j:7687)
    NEO4J_USER     - Neo4j username        (default: neo4j)
    NEO4J_PASSWORD - Neo4j password        (default: password)
    GITHUB_CACHE_DIR - JSONL cache dir     (default: github-cache)
"""

import argparse
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional

# Allow running from project root or scripts/ directory
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

# Module-level alias for neo4j write — overridden by tests via patch.object
try:
    from graph.client import write as neo4j_write
except ImportError:  # graph.client not available in test isolation
    neo4j_write = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_assignee(issue: Dict) -> str:
    """Return the first GitHub login from the `assignees` list, or empty string."""
    assignees = issue.get("assignees", [])
    if isinstance(assignees, list) and assignees:
        first = assignees[0]
        # Assignees may be stored as strings (login) or dicts ({"login": ...})
        if isinstance(first, dict):
            return first.get("login", "")
        return str(first)
    return ""


def _stable_id(prefix: str, github_number: int) -> str:
    """Generate a stable deterministic ID from issue number."""
    namespace = uuid.NAMESPACE_DNS
    return f"{prefix}-{uuid.uuid5(namespace, str(github_number)).hex[:12]}"


# ---------------------------------------------------------------------------
# Cypher templates
# ---------------------------------------------------------------------------

UPSERT_ACTION_ITEM = """
MERGE (ai:ActionItem {github_number: $github_number})
SET ai.id            = coalesce(ai.id, $id),
    ai.title         = $title,
    ai.description   = $description,
    ai.status        = $status,
    ai.assignee      = $assignee,
    ai.labels        = $labels,
    ai.author        = $author,
    ai.synced_at     = $synced_at,
    ai.updated_at    = datetime()
RETURN ai.id AS id, ai.assignee AS assignee
"""

UPSERT_INCIDENT = """
MERGE (i:Incident {github_number: $github_number})
SET i.id          = coalesce(i.id, $id),
    i.title       = $title,
    i.body        = $body,
    i.status      = $status,
    i.labels      = $labels,
    i.author      = $author,
    i.synced_at   = $synced_at,
    i.updated_at  = datetime()
RETURN i.id AS id
"""

UPSERT_RCA = """
MERGE (r:RCA {github_number: $github_number})
SET r.id          = coalesce(r.id, $id),
    r.title       = $title,
    r.body        = $body,
    r.status      = $status,
    r.labels      = $labels,
    r.author      = $author,
    r.synced_at   = $synced_at,
    r.updated_at  = datetime()
RETURN r.id AS id
"""


# ---------------------------------------------------------------------------
# Ingestion logic
# ---------------------------------------------------------------------------

def ingest_issues(issues: List[Dict], dry_run: bool = False) -> Dict[str, int]:
    """
    Upsert a list of transformed GitHub issues into Neo4j.

    Returns a summary dict with counts per node type.
    """
    if not issues:
        logger.info("No issues to ingest.")
        return {"action_item": 0, "incident": 0, "rca": 0, "skipped": 0}

    counts: Dict[str, int] = {"action_item": 0, "incident": 0, "rca": 0, "skipped": 0}

    for issue in issues:
        issue_type = issue.get("issue_type", "unknown")
        github_number = issue.get("github_issue_number")

        if not github_number:
            logger.warning("Issue missing github_issue_number, skipping: %s", issue.get("title"))
            counts["skipped"] += 1
            continue

        if issue_type == "action_item":
            assignee = _extract_assignee(issue)
            params = {
                "github_number": github_number,
                "id": _stable_id("ai", github_number),
                "title": issue.get("title", ""),
                "description": issue.get("body", ""),
                "status": "resolved" if issue.get("state") == "closed" else "open",
                "assignee": assignee,
                "labels": issue.get("labels", []),
                "author": issue.get("author", ""),
                "synced_at": issue.get("synced_at", ""),
            }
            if dry_run:
                logger.info(
                    "[DRY-RUN] ActionItem #%s  assignee=%r  title=%r",
                    github_number, assignee, params["title"],
                )
            else:
                result = neo4j_write(UPSERT_ACTION_ITEM, params)
                stored_assignee = result[0].get("assignee", "") if result else ""
                logger.debug(
                    "Upserted ActionItem #%s  assignee=%r", github_number, stored_assignee
                )
            counts["action_item"] += 1

        elif issue_type == "incident":
            params = {
                "github_number": github_number,
                "id": _stable_id("inc", github_number),
                "title": issue.get("title", ""),
                "body": issue.get("body", ""),
                "status": issue.get("state", "open"),
                "labels": issue.get("labels", []),
                "author": issue.get("author", ""),
                "synced_at": issue.get("synced_at", ""),
            }
            if dry_run:
                logger.info("[DRY-RUN] Incident #%s  title=%r", github_number, params["title"])
            else:
                neo4j_write(UPSERT_INCIDENT, params)
                logger.debug("Upserted Incident #%s", github_number)
            counts["incident"] += 1

        elif issue_type == "rca":
            params = {
                "github_number": github_number,
                "id": _stable_id("rca", github_number),
                "title": issue.get("title", ""),
                "body": issue.get("body", ""),
                "status": issue.get("state", "open"),
                "labels": issue.get("labels", []),
                "author": issue.get("author", ""),
                "synced_at": issue.get("synced_at", ""),
            }
            if dry_run:
                logger.info("[DRY-RUN] RCA #%s  title=%r", github_number, params["title"])
            else:
                neo4j_write(UPSERT_RCA, params)
                logger.debug("Upserted RCA #%s", github_number)
            counts["rca"] += 1

        else:
            logger.debug("Skipping unknown issue_type=%r for #%s", issue_type, github_number)
            counts["skipped"] += 1

    return counts


def run_ingestion(dry_run: bool = False) -> Dict[str, int]:
    """
    Load all cached JSONL issues and ingest them into Neo4j.

    Returns ingestion summary counts.
    """
    # Import here to keep the module importable without graph deps when testing
    sys.path.insert(0, str(Path(__file__).parent))
    from github_sync import load_all_cached_issues

    logger.info("Loading cached issues...")
    issues = load_all_cached_issues()
    logger.info("Loaded %d unique issues from cache", len(issues))

    counts = ingest_issues(issues, dry_run=dry_run)

    logger.info(
        "Ingestion complete: %d action_items (with assignee), %d incidents, %d RCAs, %d skipped",
        counts["action_item"], counts["incident"], counts["rca"], counts["skipped"],
    )
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    parser = argparse.ArgumentParser(description="Ingest GitHub JSONL cache into Neo4j")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be ingested without writing to Neo4j",
    )
    args = parser.parse_args()

    counts = run_ingestion(dry_run=args.dry_run)
    print(
        f"\nDone: action_items={counts['action_item']}, "
        f"incidents={counts['incident']}, rcas={counts['rca']}, "
        f"skipped={counts['skipped']}"
    )


if __name__ == "__main__":
    main()
