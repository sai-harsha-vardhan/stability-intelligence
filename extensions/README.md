# Extensions

API extensions and server for the Paperclip governance board.

## Structure

```
extensions/
├── api/
│   ├── __init__.py          # FastAPI router aggregation
│   ├── config.py            # Shared config (API base from env)
│   ├── models.py            # Pydantic models for API responses
│   ├── status_validator.py  # Declarative state machine for issue status transitions
│   ├── execution_alerts.py  # Monitors routine failures, alerts on stale executions
│   ├── dashboard_filters.py # Pre-built API query endpoints (wave, status, labels, parent)
│   └── issue_tree.py        # Issue dependency graph / parent-child visualization
├── schemas/
│   └── state-machine.yaml   # Declarative allowed transitions for all statuses
├── server/
│   ├── __init__.py
│   ├── app.py               # FastAPI server hosting the extension APIs
│   └── static/
│       └── index.html       # Dashboard HTML with Kanban board
```

## Running the Extensions Server

```bash
pip install -r extensions/requirements.txt
PAPERCLIP_COMPANY_ID=<your-company-uuid> \
  PAPERCLIP_API_BASE=http://localhost:3100 \
  uvicorn extensions.server.app:app --host 0.0.0.0 --port 3103 --reload
```

Open `http://localhost:3103` for the dashboard.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PAPERCLIP_COMPANY_ID` | **Yes** | — | Your Paperclip company UUID |
| `PAPERCLIP_API_BASE` | No | `http://localhost:3100` | Paperclip instance API URL |
| `PAPERCLIP_API_TOKEN` | No | — | Bearer token (only needed if Paperclip runs in authenticated mode) |
| `DIGEST_ISSUE_ID` | No | — | UUID of the Daily Digest tracking issue (enables digest panel in `/api/board`) |
| `MERGE_QUEUE_ISSUE_ID` | No | — | UUID of the Merge Queue tracking issue (enables escalations panel in `/api/board`) |

`DIGEST_ISSUE_ID` and `MERGE_QUEUE_ISSUE_ID` are optional. If unset, `/api/board` still works but returns empty strings for `daily_digest` and `escalations`. Set them after creating the tracking issues in Paperclip — find the UUID in the issue URL or via the API.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Dashboard HTML (Kanban board) |
| `GET` | `/health` | Service liveness check |
| `GET` | `/api/issues/filter` | Filter issues by wave / status / label / parent (AND logic) |
| `GET` | `/api/issues/tree` | Parent–child issue hierarchy |
| `GET` | `/api/routines/alerts` | Execution health alerts (JSON) |
| `GET` | `/api/routines/alerts/report` | Markdown-formatted alert report |
| `POST` | `/api/status/validate` | Validate a single status transition |
| `GET` | `/api/status/violations` | Live status audit (JSON) |
| `GET` | `/api/status/violations/report` | Markdown violation report |
| `GET` | `/api/board` | Board digest: action-required issues, escalations, daily digest |

The `/api/board` endpoint powers the Board Digest view in the optional Paperclip fork patches. See [`paperclip-fork/README.md`](../paperclip-fork/README.md).

## Status Validator

The status validator enforces a declarative state machine defined in `schemas/state-machine.yaml`. It prevents invalid status transitions via the Paperclip API extension endpoint.

Example valid transitions:
- `backlog` → `todo`
- `todo` → `in_progress`
- `in_progress` → `in_review`
- `in_review` → `merge-ready`

See `schemas/state-machine.yaml` for the full transition table.
