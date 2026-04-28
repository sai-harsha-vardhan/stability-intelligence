# RCA Intelligence System - Agent Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        STABILITY INTELLIGENCE SYSTEM                         │
│                              Agent Orchestration                             │
└─────────────────────────────────────────────────────────────────────────────┘

                                    ┌──────────────┐
                                    │   GitHub     │
                                    │   Issues     │
                                    └──────┬───────┘
                                           │
                                           │ Sync (every 6 hours)
                                           ▼
                              ┌────────────────────────┐
                              │  GitHub Sync Script    │
                              │  - Fetch incidents     │
                              │  - Parse RCA docs      │
                              └───────────┬────────────┘
                                          │
                                          │ Transform
                                          ▼
                            ┌──────────────────────────────┐
                            │       Neo4j Graph DB         │
                            │                              │
                            │  Nodes:                      │
                            │  • Incident (unanalyzed)     │
                            │  • RCA Document              │
                            │  • ActionItem                │
                            └────────┬──────────────┬──────┘
                                     │              │
                ┌────────────────────┘              └─────────────────────┐
                │                                                         │
                │ Query unanalyzed                          Query similar │
                │ incidents (every 1 hour)                  historical    │
                ▼                                           incidents     │
    ┌───────────────────────────────┐                                    │
    │      RCA ANALYSIS AGENT       │◄───────────────────────────────────┘
    │                               │
    │  1. Find Unanalyzed Incidents │
    │     └─> Query: Incident       │
    │         without Analysis      │
    │                               │
    │  2. Find Similar Historical   │
    │     └─> Match: severity,      │
    │         flows, keywords       │
    │                               │
    │  3. Build Enriched Prompt     │
    │     └─> Current + Historical  │
    │                               │
    │  4. Call LiteLLM             │────────────┐
    │     └─> Extract root cause    │           │
    │                               │           ▼
    │  5. Create Analysis Nodes     │   ┌──────────────────┐
    │     └─> Link to Incident      │   │   LiteLLM Proxy  │
    │                               │   │                  │
    │  6. Detect Patterns           │   │ ┌──────────────┐ │
    │     └─> Group by signature    │   │ │ Claude Model │ │
    │                               │   │ │  (via Juspay │ │
    │  7. Create PatternClusters    │   │ │   Grid AI)   │ │
    │     └─> Frequency >= 3        │   │ └──────────────┘ │
    │                               │   │                  │
    │  8. Calculate Trends          │   │  • Root cause    │
    │     └─> Worsening/Stable/     │   │  • Category      │
    │         Improving             │   │  • Components    │
    └───────────┬───────────────────┘   │  • Pattern sig   │
                │                       └─────────┬────────┘
                │ Write results                   │
                ▼                                 │ Response
    ┌────────────────────────────────┐           │
    │      Neo4j Graph DB (Updated)  │◄──────────┘
    │                                │
    │  New Nodes:                    │
    │  • Analysis                    │
    │    ├─ root_cause              │
    │    ├─ category                │
    │    ├─ affected_components     │
    │    └─ pattern_signature       │
    │                                │
    │  • PatternCluster              │
    │    ├─ frequency               │
    │    ├─ trend                   │
    │    └─ affected_components     │
    │                                │
    │  Relationships:                │
    │  • (Incident)-[:HAS_ANALYSIS]→ │
    │    (Analysis)                  │
    │  • (Incident)-[:EXHIBITS]→     │
    │    (PatternCluster)            │
    └────────────┬───────────────────┘
                 │
                 │ Query patterns
                 │ (frequency >= 3, worsening)
                 ▼
    ┌────────────────────────────────┐
    │     STRATEGY AGENT             │
    │  (Runs weekly)                 │
    │                                │
    │  1. Find Worsening Patterns    │
    │  2. Generate Strategies        │
    │  3. Calculate Priority         │
    │  4. Link to Patterns           │
    └────────────┬───────────────────┘
                 │
                 │ Creates
                 ▼
    ┌────────────────────────────────┐
    │  Strategy Nodes                │
    │  • contract_test_suite         │
    │  • automated_regression_suite  │
    │  • staggered_rollout_gate      │
    │  • chaos_experiment            │
    └────────────┬───────────────────┘
                 │
                 │ Links via
                 │ [:ADDRESSES_PATTERN]
                 ▼
    ┌────────────────────────────────┐
    │    Dashboard / Feedback Loop   │
    │                                │
    │  • View strategies             │
    │  • Mark effectiveness          │
    │  • Track pattern trends        │
    │  • Monitor incident reduction  │
    └────────────────────────────────┘
```

## Data Flow: RCA Agent in Detail

```
INPUT: Unanalyzed Incident
├─ id: "incident-abc123"
├─ title: "Redis timeout causing payment failures"
├─ body: "Production incident: 15% payment timeouts..."
├─ severity: "P1"
└─ affected_flows: ["payments", "checkout"]

    │
    │ Step 1: Find Similar Incidents
    ▼

HISTORICAL CONTEXT: 5 Similar Incidents
├─ Incident A: "Redis cache timeout" (30 days ago)
│  └─ Previous root cause: "Connection pool exhaustion"
├─ Incident B: "Payment API timeout" (15 days ago)
│  └─ Previous root cause: "High Redis latency"
└─ ...

    │
    │ Step 2: Build LiteLLM Prompt
    ▼

PROMPT TO CLAUDE:
┌────────────────────────────────────────┐
│ You are analyzing a production         │
│ incident for Hyperswitch.              │
│                                        │
│ Current Incident:                      │
│ - Title: Redis timeout...              │
│ - Severity: P1                         │
│ - Body: [full description]            │
│                                        │
│ Historical Context:                    │
│ - 5 similar incidents with analyses   │
│                                        │
│ Extract in JSON:                       │
│ {                                      │
│   "root_cause": "...",                │
│   "category": "timeout",              │
│   "contributing_factors": [...],      │
│   "affected_components": [...],       │
│   "is_recurring": true,               │
│   "pattern_signature": "..."          │
│ }                                      │
└────────────────────────────────────────┘

    │
    │ Step 3: LiteLLM Response
    ▼

CLAUDE ANALYSIS:
{
  "root_cause": "Redis connection pool exhausted under peak load",
  "category": "timeout",
  "contributing_factors": [
    "Insufficient connection pool size",
    "No circuit breaker",
    "High concurrent requests"
  ],
  "affected_components": [
    "payment-service",
    "redis-cache",
    "merchant-config-api"
  ],
  "is_recurring": true,
  "pattern_signature": "timeout-redis-payments"
}

    │
    │ Step 4: Create Analysis Node
    ▼

GRAPH WRITE:
CREATE (a:Analysis {
  id: "analysis-xyz789",
  incident_id: "incident-abc123",
  root_cause: "Redis connection pool exhausted...",
  category: "timeout",
  pattern_signature: "timeout-redis-payments",
  ...
})
CREATE (i)-[:HAS_ANALYSIS]->(a)

    │
    │ Step 5: Detect Patterns (after analyzing multiple incidents)
    ▼

PATTERN DETECTION:
Group by pattern_signature:
├─ "timeout-redis-payments": 3 incidents
│  ├─ Incident A (30 days ago)
│  ├─ Incident B (15 days ago)
│  └─ Incident C (5 days ago)
│
└─ Trend Calculation:
   - Recent 30 days: 2 incidents
   - Previous 30 days: 1 incident
   - Result: "worsening"

    │
    │ Step 6: Create PatternCluster
    ▼

GRAPH WRITE:
CREATE (pc:PatternCluster {
  id: "pattern-def456",
  pattern_signature: "timeout-redis-payments",
  name: "Timeout Pattern: timeout-redis-payments",
  frequency: 3,
  trend: "worsening",
  affected_components: ["payment-service", "redis-cache"],
  ...
})
CREATE (incident_a)-[:EXHIBITS]->(pc)
CREATE (incident_b)-[:EXHIBITS]->(pc)
CREATE (incident_c)-[:EXHIBITS]->(pc)

    │
    │ Step 7: Log Activity
    ▼

OUTPUT: Statistics
{
  "incidents_analyzed": 3,
  "patterns_detected": 1
}

ACTIVITY LOG:
CREATE (ae:ActivityEvent {
  agent_name: "rca_agent",
  message: "RCA analysis complete: 3 analyzed, 1 pattern detected",
  ...
})
```

## Scheduler Timeline

```
Hour  0  ────────────────────────────────────────────────────────
         │ GitHub Sync (6hr interval)
         │ RCA Agent (1hr interval)
         │ Health Check (5min interval)
         └─> System Bootstrap

Hour  1  ────────────────────────────────────────────────────────
         │ RCA Agent runs
         └─> Analyzes new incidents

Hour  2  ────────────────────────────────────────────────────────
         │ RCA Agent runs
         └─> Detects patterns

Hour  3  ────────────────────────────────────────────────────────
         │ RCA Agent runs

Hour  6  ────────────────────────────────────────────────────────
         │ GitHub Sync runs (fetches new incidents)
         │ RCA Agent runs (analyzes new incidents)

Hour 24  ────────────────────────────────────────────────────────
         │ Feedback Loop runs (daily)
         │ Marks strategy effectiveness

Week  1  ────────────────────────────────────────────────────────
         │ Strategy Agent runs (Monday 09:00)
         └─> Generates prevention strategies from patterns
```

## Success Metrics

The RCA Agent is successful when:

✅ **Incident Analysis**
   - All unanalyzed incidents get Analysis nodes within 1 hour
   - Root causes are accurate and actionable
   - Categories are correctly classified
   - Affected components are identified

✅ **Pattern Detection**
   - Recurring patterns are detected (>= 3 similar incidents)
   - Trends are calculated correctly (worsening/stable/improving)
   - Pattern signatures are unique and meaningful

✅ **System Integration**
   - Runs on schedule every 1 hour
   - No errors or failures
   - Activity logs show progress
   - Enables Strategy Agent to generate prevention plans

✅ **Quality Assurance**
   - LiteLLM responses are valid JSON
   - Graph relationships are correct
   - No duplicate analyses
   - Idempotent operations

---

**Status**: ✅ Fully Operational  
**Next Agent**: Strategy Agent (already implemented)  
**Integration**: Seamless with existing system
