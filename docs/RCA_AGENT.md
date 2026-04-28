# RCA Analysis Agent - Implementation Summary

## Overview

The RCA (Root Cause Analysis) Agent is the core intelligence component of the Stability Intelligence System. It automatically analyzes production incidents, extracts root causes using AI, and detects recurring patterns to enable proactive prevention strategies.

## Key Capabilities

### 1. Incident Analysis with Historical Context

The agent analyzes unanalyzed Incident nodes by:

- **Finding similar historical incidents** based on:
  - Same severity level
  - Overlapping affected flows
  - Similar title keywords
  - Temporal proximity

- **Building enriched context** by combining:
  - Current incident details
  - Up to 5 similar historical incidents with their root causes
  - Historical pattern information

- **AI-powered root cause extraction** using Claude via LiteLLM:
  - Root cause description (concise, 1-2 sentences)
  - Category classification (timeout, config, race_condition, api_change, etc.)
  - Contributing factors (technical reasons)
  - Affected components (services, APIs, databases)
  - Recurring status detection
  - Pattern signature generation

### 2. Pattern Recognition and Clustering

The agent automatically detects recurring incident patterns:

- **Groups incidents** by pattern_signature
- **Clusters incidents** with >= 3 occurrences
- **Calculates trends** by comparing:
  - Recent 30 days vs previous 30 days
  - Results: "worsening", "stable", or "improving"

- **Creates PatternCluster nodes** with:
  - Unique pattern identifier
  - Frequency count
  - Trend direction
  - Affected components
  - Date range (first/last occurrence)

### 3. Intelligent Prompting Strategy

The LiteLLM prompt template includes:

```
Current Incident:
- Title, severity, timestamps
- Description/body
- Affected flows

Historical Context:
- 5 similar past incidents
- Their root causes and categories
- Components they affected

Expected JSON Output:
- root_cause: Brief description
- category: Standardized classification
- contributing_factors: List of technical reasons
- affected_components: List of services/APIs
- is_recurring: Boolean flag
- pattern_signature: Unique pattern ID
```

### 4. Robust Error Handling

- **Graceful LiteLLM failures**: Creates fallback Analysis nodes
- **JSON parsing resilience**: Extracts JSON from mixed text responses
- **Idempotent operations**: Prevents duplicate analyses
- **Comprehensive logging**: Tracks all operations for debugging

## Architecture

### Node Schema

#### Analysis Node
```cypher
Analysis {
  id: "analysis-{uuid}",
  incident_id: String,
  root_cause: String,
  category: String,
  contributing_factors: List[String],
  affected_components: List[String],
  is_recurring: Boolean,
  pattern_signature: String,
  created_at: DateTime,
  updated_at: DateTime
}
```

#### PatternCluster Node
```cypher
PatternCluster {
  id: "pattern-{uuid}",
  pattern_signature: String,
  name: String,
  description: String,
  frequency: Int,
  trend: String,
  root_cause_category: String,
  affected_components: List[String],
  first_occurrence: DateTime,
  last_occurrence: DateTime,
  created_at: DateTime,
  updated_at: DateTime
}
```

### Relationships

- `(Incident)-[:HAS_ANALYSIS]->(Analysis)` - Links incidents to their analysis
- `(Incident)-[:EXHIBITS]->(PatternCluster)` - Links incidents to detected patterns

## Scheduling

The RCA Agent runs automatically every **1 hour** via APScheduler:

```python
scheduler.add_job(
    run_rca_agent,
    trigger=IntervalTrigger(hours=1),
    id="rca_agent",
    name="RCA Analysis Agent"
)
```

## Execution Flow

```
1. Find Unanalyzed Incidents
   ↓
2. For Each Incident:
   ├─ Find Similar Historical Incidents (similarity search)
   ├─ Build LiteLLM Prompt (current + historical context)
   ├─ Call Claude for Analysis (via LiteLLM)
   ├─ Parse JSON Response
   └─ Create Analysis Node
   ↓
3. Detect Patterns:
   ├─ Group by pattern_signature
   ├─ Filter clusters with >= 3 incidents
   ├─ Calculate trend (recent vs previous 30 days)
   └─ Create PatternCluster nodes
   ↓
4. Log Activity & Return Statistics
```

## Integration Points

### LiteLLM Integration
- **Endpoint**: Juspay Grid AI via LiteLLM proxy
- **Model**: `claude-critical` (configurable via env)
- **Tracing**: Langfuse integration for observability
- **Timeout**: 120 seconds

### Neo4j Integration
- **Read queries**: Find unanalyzed incidents, similar incidents
- **Write queries**: Create Analysis and PatternCluster nodes
- **Relationships**: Link incidents to analyses and patterns

### Activity Logging
- All operations logged to ActivityEvent nodes
- Includes statistics: incidents_analyzed, patterns_detected
- Linked to agent_name="rca_agent"

## Sample Output

### Analysis Example
```json
{
  "root_cause": "Redis connection pool exhaustion causing payment API timeouts",
  "category": "timeout",
  "contributing_factors": [
    "Insufficient connection pool size",
    "High concurrent request volume",
    "Lack of circuit breaker"
  ],
  "affected_components": [
    "payment-service",
    "redis-cache",
    "merchant-config-api"
  ],
  "is_recurring": true,
  "pattern_signature": "timeout-redis-payments"
}
```

### Pattern Cluster Example
```
Name: "Timeout Pattern: timeout-redis-payments"
Description: "Recurring pattern affecting payment-service, redis-cache, merchant-config-api"
Frequency: 3
Trend: "worsening"
Category: "timeout"
Components: ["payment-service", "redis-cache", "merchant-config-api"]
First Occurrence: 2026-03-26
Last Occurrence: 2026-04-21
```

## Testing

A comprehensive test suite is included in `tests/test_rca_agent.py`:

### Test Coverage
- ✅ Creates realistic test incidents (5 scenarios)
- ✅ Verifies incident analysis
- ✅ Validates pattern detection (clusters of 3+ similar incidents)
- ✅ Tests idempotency (no duplicate analyses)
- ✅ Validates JSON parsing
- ✅ Checks graph relationships
- ✅ Cleans up test data

### Running Tests
```bash
cd /home/sai_harsha/stability/rca-intelligence-system/stability-intelligence
python tests/test_rca_agent.py
```

## Performance Characteristics

- **Batch Size**: Processes up to 50 unanalyzed incidents per run
- **LiteLLM Latency**: ~2-5 seconds per incident
- **Pattern Detection**: O(n) where n = total analyzed incidents
- **Memory**: Minimal, processes incidents sequentially
- **Idempotent**: Safe to run multiple times

## Future Enhancements

1. **Advanced Similarity Matching**
   - Use vector embeddings for semantic similarity
   - NLP-based keyword extraction
   - Time-series pattern matching

2. **Confidence Scoring**
   - Add confidence scores to root cause extraction
   - Weight historical context by recency
   - Multi-model consensus voting

3. **Automated Remediation**
   - Link patterns to runbooks
   - Suggest automated fixes
   - Generate preventive action items

4. **Real-time Analysis**
   - Stream processing for immediate analysis
   - Alert on critical patterns
   - Predictive incident detection

## Deployment

The agent is deployed as part of the Stability Intelligence System:

```yaml
# docker-compose.yml
services:
  agents:
    build:
      context: .
      dockerfile: Dockerfile.agents
    environment:
      - LITELLM_BASE_URL=http://litellm:4000
      - NEO4J_URI=bolt://neo4j:7687
    depends_on:
      - neo4j
      - litellm
```

## Monitoring

Track agent health via:
- **ActivityEvent nodes**: Recent runs and statistics
- **Scheduler logs**: Execution timing and errors
- **Langfuse traces**: LiteLLM call latency and token usage
- **Neo4j metrics**: Node creation rate, query performance

---

**Status**: ✅ Fully Implemented and Tested
**Owner**: RCA Intelligence System
**Last Updated**: 2026-04-26
