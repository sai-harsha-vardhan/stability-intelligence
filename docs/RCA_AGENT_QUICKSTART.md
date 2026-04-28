# RCA Agent - Quick Reference Guide

## Running the Agent

### Option 1: Via Docker Compose (Recommended for Production)

```bash
# Start the entire system
cd /home/sai_harsha/stability/rca-intelligence-system/stability-intelligence
docker-compose up -d

# Monitor RCA agent specifically
docker-compose logs -f agents | grep rca_agent

# Check agent status
docker-compose ps agents
```

The agent will run automatically every 1 hour.

### Option 2: Manual Execution (Testing/Development)

```bash
# Activate virtual environment
cd /home/sai_harsha/stability/rca-intelligence-system/stability-intelligence
source .venv/bin/activate

# Run agent once
python -c "from agents.rca_agent import RCAAgent; agent = RCAAgent(); print(agent.run())"
```

### Option 3: Run Test Suite

```bash
# Full test with sample data
source .venv/bin/activate
python tests/test_rca_agent.py
```

## Expected Output

### Successful Run
```json
{
  "incidents_analyzed": 5,
  "patterns_detected": 2
}
```

### Log Messages
```
INFO - RCA Agent starting...
INFO - Found 5 unanalyzed incidents
INFO - Analyzed incident incident-abc123: Redis timeout causing payment failures
INFO - Analyzed incident incident-def456: Configuration drift in staging
INFO - ...
INFO - Detected 2 new pattern clusters
INFO - Created PatternCluster: pattern-xyz789 - Timeout Pattern: timeout-redis-payments (frequency=3, trend=worsening)
INFO - RCA agent complete: {'incidents_analyzed': 5, 'patterns_detected': 2}
```

## Verifying Results

### Check Analysis Nodes

```cypher
// In Neo4j Browser (http://localhost:7474)

// Count analyses created
MATCH (a:Analysis)
RETURN count(a) AS total_analyses

// View recent analyses
MATCH (i:Incident)-[:HAS_ANALYSIS]->(a:Analysis)
RETURN i.title, a.root_cause, a.category, a.pattern_signature
ORDER BY a.created_at DESC
LIMIT 10

// Find recurring patterns
MATCH (a:Analysis)
WHERE a.is_recurring = true
RETURN a.pattern_signature, count(*) AS frequency
ORDER BY frequency DESC
```

### Check Pattern Clusters

```cypher
// View all pattern clusters
MATCH (pc:PatternCluster)
RETURN pc.name, pc.frequency, pc.trend, pc.affected_components
ORDER BY pc.frequency DESC

// Find worsening patterns
MATCH (pc:PatternCluster)
WHERE pc.trend = 'worsening'
RETURN pc.name, pc.frequency, pc.description

// View incidents in a pattern
MATCH (pc:PatternCluster {pattern_signature: 'timeout-redis-payments'})
      <-[:EXHIBITS]-(i:Incident)
RETURN i.title, i.occurred_at
ORDER BY i.occurred_at DESC
```

## Troubleshooting

### Problem: No incidents analyzed

**Check**:
```cypher
// Are there unanalyzed incidents?
MATCH (i:Incident)
WHERE NOT EXISTS {
  MATCH (i)-[:HAS_ANALYSIS]->(:Analysis)
}
RETURN count(i) AS unanalyzed_count
```

**Solution**: 
- Run GitHub sync first: `docker-compose exec agents python scripts/github_sync.py`
- Ensure incidents exist in Neo4j

### Problem: LiteLLM errors

**Check logs**:
```bash
docker-compose logs litellm
```

**Common issues**:
- LiteLLM service not running → `docker-compose up -d litellm`
- Invalid API key → Check `.env` for `LITELLM_API_KEY`
- Timeout → Increase timeout in `agents/base.py` `call_claude()` method

**Fallback**: Agent creates basic analysis even if LiteLLM fails

### Problem: No patterns detected

**Expected**: Patterns require **>= 3 similar incidents**

**Check**:
```cypher
// Count incidents per pattern signature
MATCH (a:Analysis)
WHERE a.pattern_signature <> 'unanalyzed'
RETURN a.pattern_signature, count(*) AS frequency
ORDER BY frequency DESC
```

**Solution**: 
- Need at least 3 incidents with same pattern_signature
- Run agent multiple times to analyze more incidents
- Check if incidents are actually similar

### Problem: Duplicate analyses

**Check**:
```cypher
// Find incidents with multiple analyses
MATCH (i:Incident)-[:HAS_ANALYSIS]->(a:Analysis)
WITH i, count(a) AS analysis_count
WHERE analysis_count > 1
RETURN i.id, i.title, analysis_count
```

**Solution**: Should not happen (agent is idempotent). If it does:
1. Check for race conditions (multiple agents running?)
2. Review `_find_unanalyzed_incidents()` query
3. File bug report

## Configuration

### Environment Variables

```bash
# .env file

# LiteLLM Configuration
LITELLM_BASE_URL=http://litellm:4000
LITELLM_API_KEY=your-api-key-here
LITELLM_CLAUDE_MODEL=claude-critical

# Neo4j Configuration
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-password

# Scheduler Configuration
RCA_AGENT_INTERVAL_HOURS=1  # Run every 1 hour (default)
```

### Adjusting Schedule

Edit `scheduler/runner.py`:

```python
# Change from 1 hour to 30 minutes
self.scheduler.add_job(
    self.run_rca_agent,
    trigger=IntervalTrigger(minutes=30),  # Changed from hours=1
    id="rca_agent",
    name="RCA Analysis Agent",
    replace_existing=True,
)
```

## Performance Tuning

### Batch Size

Adjust in `agents/rca_agent.py`:

```python
def _find_unanalyzed_incidents(self):
    cypher = """
    ...
    LIMIT 50  # Increase to process more incidents per run
    """
```

### Similar Incidents Count

Adjust context size in `find_similar_incidents()`:

```python
cypher = """
...
LIMIT 5  # Increase for more historical context (slower)
"""
```

### LiteLLM Timeout

Adjust in `agents/base.py`:

```python
def call_claude(self, ..., max_tokens: int = 4000):
    response = httpx.post(
        ...,
        timeout=120,  # Increase if LiteLLM is slow
    )
```

## Monitoring

### Activity Events

```cypher
// Recent RCA agent runs
MATCH (ae:ActivityEvent)
WHERE ae.agent_name = 'rca_agent'
RETURN ae.message, ae.details, ae.created_at
ORDER BY ae.created_at DESC
LIMIT 10
```

### Success Rate

```cypher
// Analysis success rate
MATCH (i:Incident)-[:HAS_ANALYSIS]->(a:Analysis)
WITH count(a) AS total_analyses
MATCH (a2:Analysis)
WHERE a2.category <> 'other'
WITH total_analyses, count(a2) AS successful
RETURN successful, total_analyses, 
       (successful * 100.0 / total_analyses) AS success_rate
```

### Pattern Growth

```cypher
// Pattern clusters over time
MATCH (pc:PatternCluster)
RETURN pc.created_at AS date, count(*) AS new_patterns
ORDER BY date DESC
```

## API Usage (Programmatic)

### Python API

```python
from agents.rca_agent import RCAAgent

# Create agent instance
agent = RCAAgent()

# Run full analysis
stats = agent.run()
print(f"Analyzed {stats['incidents_analyzed']} incidents")
print(f"Detected {stats['patterns_detected']} patterns")

# Analyze specific incident
incident = {
    'id': 'incident-123',
    'title': 'Payment timeout',
    'body': 'Description...',
    'severity': 'P1',
    'affected_flows': ['payments']
}
agent.analyze_incident(incident)

# Find similar incidents
similar = agent.find_similar_incidents(incident)
print(f"Found {len(similar)} similar incidents")

# Detect patterns
pattern_count = agent.detect_patterns()
print(f"Detected {pattern_count} new patterns")
```

## Best Practices

### 1. Regular Monitoring
- Check agent logs daily
- Review new patterns weekly
- Validate analysis accuracy monthly

### 2. Data Quality
- Ensure incidents have good descriptions
- Add affected_flows metadata
- Use consistent severity levels

### 3. Pattern Validation
- Review detected patterns manually
- Confirm root causes are accurate
- Adjust prompts if needed

### 4. Performance
- Keep batch size reasonable (<100)
- Monitor LiteLLM latency
- Scale Neo4j if needed

### 5. Iterative Improvement
- Track analysis accuracy
- Refine LiteLLM prompts based on results
- Add new categories as needed
- Improve similarity matching

## Support

### Documentation
- Full docs: `docs/RCA_AGENT.md`
- Flow diagram: `docs/RCA_AGENT_FLOW.md`
- Test suite: `tests/test_rca_agent.py`

### Logs Location
- Docker: `docker-compose logs agents`
- Local: `/app/logs/scheduler.log`

### Common Queries
Save these in Neo4j Browser for quick access:

```cypher
// Dashboard: RCA Agent Stats
MATCH (i:Incident)
OPTIONAL MATCH (i)-[:HAS_ANALYSIS]->(a:Analysis)
OPTIONAL MATCH (pc:PatternCluster)
RETURN 
  count(DISTINCT i) AS total_incidents,
  count(DISTINCT a) AS analyzed_incidents,
  count(DISTINCT pc) AS total_patterns,
  count(DISTINCT CASE WHEN pc.trend = 'worsening' THEN pc END) AS worsening_patterns
```

---

**Quick Start**: `docker-compose up -d && docker-compose logs -f agents`  
**Validation**: `python scripts/validate_rca_agent.py`  
**Testing**: `python tests/test_rca_agent.py`
