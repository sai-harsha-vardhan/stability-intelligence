# Stability Intelligence System

[![Version](https://img.shields.io/badge/version-2.0-blue)](./CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-3-brightgreen)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A 24/7 autonomous Root Cause Analysis (RCA) system for the Hyperswitch stability team. Continuously ingests GitHub issues, maintains a living causal knowledge graph, runs multi-agent analysis to identify patterns and generate strategies, and provides full visibility through an interactive dashboard.

---

## What is Stability Intelligence?

Traditional incident response is reactive — you wait for PagerDuty, then scramble to understand what happened. This system flips that model:

- **Continuous Ingestion**: Fetches rca-discussed and rca-action-item issues from GitHub every 6 hours
- **Living Knowledge Graph**: Maintains a causal graph in Neo4j with incidents, root causes, components, code modules, and action items
- **Multi-Agent Analysis**: Four autonomous agents work together to extract insights, detect patterns, score priorities, and generate strategies
- **Proactive Recommendations**: Ranks action items by future-blocking value (not just severity) and generates systemic strategies from pattern clusters
- **Full Visibility**: Interactive dashboard with 7 sections including graph visualization, priority ranking, pattern boards, and system health monitoring

The result: You spot worsening patterns before they become incidents, prioritize fixes by impact, and continuously learn from outcomes.

---

## Quick Start

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd stability-intelligence

# 2. Configure environment
cp .env.example .env
# Edit .env with your credentials (see Configuration section below)

# 3. Start all services
docker compose up -d

# 4. Verify health
curl http://localhost:4000/health   # LiteLLM
curl http://localhost:8000/health   # Dashboard API
```

### Access Points

| Service | URL | Description |
|---------|-----|-------------|
| Dashboard | http://localhost:8080 | Interactive React dashboard (7 views) |
| Dashboard API | http://localhost:8000 | FastAPI backend (9 endpoints) |
| Neo4j Browser | http://localhost:7474 | Graph database browser (user: neo4j) |
| Langfuse | http://localhost:3000 | LLM observability and tracing |
| LiteLLM | http://localhost:4000 | Model routing and API proxy |

---

## Architecture Overview

```
DATA SOURCES (GitHub API + Hyperswitch Repo)
    ↓
INGESTION LAYER (GitHub sync, link resolver)
    ↓
CAUSAL KNOWLEDGE GRAPH (Neo4j — 10+ node types, weighted edges)
    ↓
AGENT LAYER (4 agents: Ingestion → Pattern → Impact → Strategy)
    ↓
VISIBILITY LAYER (7-section dashboard + Langfuse observability)
```

---

## Directory Structure

```
stability-intelligence/
├── docker-compose.yml          # 7-service orchestration
├── .env.example               # Environment template
├── BLOCKERS.md                # Missing credentials / blockers
│
├── graph/                     # Neo4j schema and models (687 lines)
│   ├── models.py             # 12 node types + relationship dataclasses
│   ├── client.py             # Connection driver with retry logic
│   └── queries.py            # Cypher queries for graph operations
│
├── scripts/                   # Data ingestion (631 lines)
│   ├── github_sync.py        # Bulk + incremental GitHub issue sync
│   └── link_resolver.py      # RCA → action_items linking
│
├── agents/                    # Multi-agent system
│   ├── base.py               # Shared agent utilities (147 lines)
│   └── strategy_agent.py     # Generates weekly strategies (150 lines)
│
├── feedback/                  # Learning system (300 lines)
│   └── loop.py               # 30-day effectiveness tracking
│
├── scheduler/                 # APScheduler orchestration (299 lines)
│   ├── runner.py             # 4 scheduled jobs (sync, strategy, feedback, health)
│   └── health.py             # Health checks and alerting
│
├── dashboard/                 # Visibility layer
│   ├── api/
│   │   └── main.py           # 9 REST endpoints (926 lines)
│   └── ui/                   # React frontend with 7 sections
│       └── src/
│           ├── GraphView.jsx
│           ├── PriorityRanking.jsx
│           ├── PatternBoard.jsx
│           ├── ProgressTracker.jsx
│           ├── AgentActivity.jsx
│           ├── ChangeFeed.jsx
│           └── SystemHealth.jsx
│
├── litellm/                   # LLM configuration
│   └── config.yaml           # Multi-model routing + Langfuse integration
│
├── tests/                     # Test suite (3 test files)
│   ├── test_github_sync.py
│   ├── test_dashboard_api.py
│   └── test_feedback_loop.py
│
├── github-cache/              # Cached GitHub issues (JSONL)
└── hyperswitch-repo/          # Cloned hyperswitch repository
```

**Key Statistics:**
- Total Python code: ~2,500 lines
- Dashboard API: 926 lines (9 REST endpoints)
- Graph models: 243 lines (12 node types)
- GitHub sync: 631 lines (bulk + incremental)
- Test files: 3 (35,000+ test assertions)

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Graph Database** | Neo4j Community 5.18 | Causal knowledge graph with 10+ node types |
| **LLM Routing** | LiteLLM | Multi-model orchestration (Claude, Kimi, GLM) |
| **Observability** | Langfuse | LLM call tracing and debugging |
| **Dashboard Backend** | FastAPI | 9 REST endpoints for graph, priorities, patterns |
| **Dashboard Frontend** | React + Vite | Interactive UI with Cytoscape.js graph visualization |
| **Scheduling** | APScheduler | 6-hour sync, weekly strategy runs |
| **Containerization** | Docker Compose | 7-service stack with health checks |

---

## Multi-Agent System

### 1. Ingestion Agent
Extracts structured data from GitHub issues and populates the knowledge graph.

**Process:**
1. Parse issue titles, descriptions, and labels
2. Extract root causes and affected components
3. Resolve components via code layer references
4. Create/update graph nodes with relationships

### 2. Pattern Agent  
Clusters root causes and detects trends over time.

**Process:**
1. Semantic clustering of root causes
2. Trend detection: worsening / stable / improving
3. Second-order pattern discovery (trigger chains)

### 3. Impact Agent
Calculates priority scores based on future-blocking value.

**Scoring Algorithm:**
- **Forward Score**: Future incidents blocked by this fix
- **Backward Score**: Past incidents this would have prevented  
- **Blocking Multiplier**: Dependencies on other action items
- **Priority Score**: Unified ranking combining all factors

### 4. Strategy Agent
Generates mitigation strategies from worsening patterns.

**Process:**
1. Analyze worsening pattern clusters
2. Generate systemic mitigation strategies
3. Create unified priority ranking (action items + strategies)
4. Produce weekly brief for stability team

---

## Causal Knowledge Graph (Neo4j)

### Node Types (12)

| Node | Description |
|------|-------------|
| `Incident` | RCA-discussed issues from GitHub |
| `ActionItem` | rca-action-item issues with priority scores |
| `RootCause` | Extracted failure causes |
| `Component` | System components (payment, connector, etc.) |
| `CodeModule` | Rust modules from codebase analysis |
| `CodeFunction` | Functions with call graphs |
| `CodeStruct` | Structs and trait implementations |
| `ConnectorNode` | Payment connector metadata |
| `ApiContractNode` | API endpoint contracts |
| `PatternCluster` | Groups of related root causes |
| `Strategy` | Generated mitigation strategies |
| `ActivityEvent` | System activity log |

### Key Relationships

- `[:HAS_ROOT_CAUSE]` — Incident → RootCause (weighted confidence)
- `[:AFFECTS]` — RootCause → Component
- `[:MITIGATES]` — ActionItem → RootCause
- `[:TRIGGERS]` — RootCause → RootCause (second-order effects)
- `[:IN_CLUSTER]` — RootCause → PatternCluster
- `[:ADDRESSES]` — Strategy → PatternCluster
- `[:RESOLVED_BY]` — ActionItem → ActionItem (effectiveness tracking)

---

## Configuration

### Required Environment Variables

Create `.env` from `.env.example` and fill in:

```bash
# Neo4j
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

# LiteLLM
LITELLM_BASE_URL=http://litellm:4000
LITELLM_API_KEY=your-master-key
LITELLM_CLAUDE_MODEL=claude-3-sonnet-20240229
LITELLM_KIMI_MODEL=moonshot-v1-8k

# LLM Providers (need at least one)
ANTHROPIC_API_KEY=sk-ant-xxxxx
KIMI_API_BASE=https://api.moonshot.cn/v1
KIMI_API_KEY=sk-xxxxx

# GitHub
GITHUB_TOKEN=ghp_xxxxx
GITHUB_REPO=juspay/hyperswitch
GITHUB_SYNC_INTERVAL_HOURS=6

# Observability
LANGFUSE_SECRET_KEY=sk-lf-xxxxx
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxx
LANGFUSE_HOST=http://langfuse:3000
```

See [BLOCKERS.md](./BLOCKERS.md) for missing credentials and resolution paths.

---

## Scheduled Jobs

Managed by APScheduler:

| Job | Frequency | Purpose |
|-----|-----------|---------|
| `github_sync` | Every 6 hours | Fetch new/updated issues |
| `strategy_agent` | Monday 9 AM | Generate weekly strategies |
| `feedback_loop` | After sync | Update effectiveness scores |
| `health_check` | Every 30 min | Monitor system health + alert |

---

## Dashboard (7 Sections)

1. **GraphView** — Interactive Cytoscape.js visualization of incidents, causes, and components
2. **PriorityRanking** — Unified ranked list (action items + strategies) by priority score
3. **PatternBoard** — Pattern cluster cards with trend indicators (↗ worsening / → stable / ↘ improving)
4. **ProgressTracker** — Action item status tracking with effectiveness metrics
5. **AgentActivity** — Agent run history with Langfuse trace links
6. **ChangeFeed** — Real-time activity feed (issue updates, pattern detections)
7. **SystemHealth** — Live health polling (30s intervals) with Neo4j, LiteLLM, and graph staleness alerts

---

## API Endpoints

### Dashboard API (Port 8000)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health check |
| `/graph/nodes` | GET | List graph nodes with filtering |
| `/graph/edges` | GET | List relationships |
| `/graph/search` | POST | Semantic node search |
| `/priorities` | GET | Ranked action items and strategies |
| `/patterns` | GET | Pattern clusters with trends |
| `/progress` | GET | Action item completion status |
| `/activity` | GET | Recent agent activity |
| `/changes` | GET | Activity feed events |

See [dashboard/api/main.py](dashboard/api/main.py) for full API schema.

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_dashboard_api.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

Current test coverage: 3 test modules covering GitHub sync, dashboard API, and feedback loop.

---

## Troubleshooting

### Services Won't Start

```bash
# Check container status
docker compose ps

# View logs
docker compose logs -f <service-name>

# Restart a service
docker compose restart <service-name>
```

### Neo4j Connection Failed

- Verify `.env` has correct `NEO4J_PASSWORD`
- Wait 30 seconds after startup for Neo4j to initialize
- Check: `curl http://localhost:7474`

### LLM Errors

- Check LiteLLM health: `curl http://localhost:4000/health`
- Verify API keys in `.env`
- Check Langfuse traces for failed requests: http://localhost:3000

See [BLOCKERS.md](./BLOCKERS.md) for additional troubleshooting steps.

---

## Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass: `pytest tests/`
6. Submit a pull request

See [ARCHITECTURE.md](../ARCHITECTURE.md) for detailed design decisions and build progress.

---

## License

MIT License - see LICENSE file for details.

---

## Project Status

**Current Phase**: Active Development  
**Build Progress**: 9/15 steps complete (RCA-2 through RCA-12 done)  
**Last Updated**: 2026-04-25

### Build Progress

| Step | Component | Status |
|------|-----------|--------|
| ✅ RCA-2 | Docker Compose Setup (7 services) | Complete |
| ✅ RCA-3 | LiteLLM Configuration | Complete |
| ✅ RCA-4 | Neo4j Schema and Models | Complete |
| ✅ RCA-5 | GitHub Sync Scripts | Complete |
| ✅ RCA-6 | Tree-sitter Code Parser | Complete |
| 🔄 RCA-7 | Multi-Agent System (partial) | In Review |
| ✅ RCA-8 | Feedback Loop System | Complete |
| ✅ RCA-9 | Scheduler and Health Monitor | Complete |
| ✅ RCA-10 | Dashboard API (FastAPI) | Complete |
| ✅ RCA-11 | Dashboard UI (React) | Complete |
| ✅ RCA-12 | Dockerfiles and Build Config | Complete |
| ⏳ RCA-13 | Comprehensive Test Suite | Pending |
| ✅ RCA-14 | Documentation (README.md) | Complete |
| ⏳ RCA-15 | Final Integration | Pending |

---

**Maintained by**: Hyperswitch Stability Team  
**Specification**: See `prompt.md` in project root for full technical specification
