import React, { useEffect, useState } from 'react'
import { AgentStatusDot } from './ui/AgentStatusDot'
import { Skeleton } from './ui/Skeleton'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'
const LANGFUSE_BASE_URL = import.meta.env.VITE_LANGFUSE_URL || 'http://localhost:3000'

const AGENTS = [
  { id: 'ingestion', name: 'INGESTION AGENT', icon: '📥', description: 'Syncs GitHub issues' },
  { id: 'pattern', name: 'PATTERN AGENT', icon: '🔍', description: 'Detects patterns' },
  { id: 'scoring', name: 'SCORING AGENT', icon: '🎯', description: 'Scores priorities' },
  { id: 'strategy', name: 'STRATEGY AGENT', icon: '🧠', description: 'Generates strategies' }
]

const AgentActivity = ({ limit = 50 }) => {
  const [agentData, setAgentData] = useState({})
  const [runHistory, setRunHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [agentFilter, setAgentFilter] = useState('all')

  useEffect(() => {
    fetchActivity()
    
    // Set up polling every 60 seconds
    const interval = setInterval(fetchActivity, 60000)
    return () => clearInterval(interval)
  }, [limit])

  const fetchActivity = async () => {
    try {
      setLoading(true)
      
      // Fetch agent activity data
      const response = await fetch(`${API_BASE_URL}/agents/activity?limit=${limit}`)
      if (!response.ok) throw new Error('Failed to fetch agent activity')
      const data = await response.json()
      
      setAgentData(data.agents || {})
      setRunHistory(data.run_history || [])
      setLoading(false)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const getStatusColor = (status) => {
    if (status === 'running') return 'running'
    if (status === 'success' || status === 'idle') return 'healthy'
    if (status === 'warning') return 'warning'
    return 'error'
  }

  const formatDuration = (seconds) => {
    if (!seconds && seconds !== 0) return '--'
    if (seconds < 60) return `${seconds}s`
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}m ${secs}s`
  }

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Never'
    const date = new Date(timestamp)
    const now = new Date()
    const diffMs = now - date
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)
    
    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    return date.toLocaleDateString()
  }

  const getLangfuseLink = (traceId) => {
    if (!traceId) return null
    return `${LANGFUSE_BASE_URL}/traces/${traceId}`
  }

  // Generate sample data for demo if no data available
  const getDemoAgentData = (agentId) => {
    const demos = {
      ingestion: {
        status: 'idle',
        lastRun: new Date(Date.now() - 2 * 60000).toISOString(),
        duration: 34,
        processed: 3,
        lastOutput: 'Added INC-2026-0051 → cluster "Connector Response Drift" (0.91)'
      },
      pattern: {
        status: 'idle',
        lastRun: new Date(Date.now() - 15 * 60000).toISOString(),
        duration: 12,
        processed: 1,
        lastOutput: 'Detected 2 new patterns in onboarding cluster'
      },
      scoring: {
        status: 'idle',
        lastRun: new Date(Date.now() - 45 * 60000).toISOString(),
        duration: 28,
        processed: 15,
        lastOutput: 'Recalculated priorities for 15 action items'
      },
      strategy: {
        status: 'idle',
        lastRun: new Date(Date.now() - 2 * 3600000).toISOString(),
        duration: 156,
        processed: 1,
        lastOutput: 'Generated strategy: "Connector Contract Test Suite"'
      }
    }
    return demos[agentId] || demos.ingestion
  }

  // Generate last 7 days of run history
  const generateRunHistory = () => {
    const history = []
    const agents = ['ingestion', 'pattern', 'scoring', 'strategy']
    const statuses = ['success', 'success', 'success', 'warning', 'error']
    
    for (let day = 0; day < 7; day++) {
      const date = new Date()
      date.setDate(date.getDate() - day)
      
      agents.forEach(agent => {
        // Generate 3-8 runs per day per agent
        const numRuns = Math.floor(Math.random() * 6) + 3
        for (let i = 0; i < numRuns; i++) {
          const hour = Math.floor(Math.random() * 24)
          const minute = Math.floor(Math.random() * 60)
          const runDate = new Date(date)
          runDate.setHours(hour, minute)
          
          history.push({
            id: `${agent}-${day}-${i}`,
            agent_id: agent,
            timestamp: runDate.toISOString(),
            status: statuses[Math.floor(Math.random() * statuses.length)],
            duration: Math.floor(Math.random() * 180) + 10,
            items_processed: Math.floor(Math.random() * 20) + 1
          })
        }
      })
    }
    
    return history.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
  }

  const getDisplayData = () => {
    if (Object.keys(agentData).length > 0) {
      return agentData
    }
    // Return demo data if no real data
    return AGENTS.reduce((acc, agent) => {
      acc[agent.id] = getDemoAgentData(agent.id)
      return acc
    }, {})
  }

  const getDisplayHistory = () => {
    if (runHistory.length > 0) {
      return runHistory.slice(0, 100)
    }
    return generateRunHistory().slice(0, 100)
  }

  const displayData = getDisplayData()
  const displayHistory = getDisplayHistory()

  const filteredHistory = agentFilter === 'all' 
    ? displayHistory 
    : displayHistory.filter(run => run.agent_id === agentFilter)

  // Group runs by day for the timeline
  const groupRunsByDay = (runs) => {
    const groups = {}
    runs.forEach(run => {
      const date = new Date(run.timestamp).toLocaleDateString()
      if (!groups[date]) groups[date] = []
      groups[date].push(run)
    })
    return groups
  }

  const runsByDay = groupRunsByDay(filteredHistory)
  const sortedDays = Object.keys(runsByDay).sort((a, b) => new Date(b) - new Date(a))

  if (loading && Object.keys(displayData).length === 0) {
    return (
      <div className="section-card agent-activity">
        <div className="card-header">
          <h3>Agent Activity</h3>
        </div>
        <div className="card-content">
          <div className="agent-cards-grid">
            {[1, 2, 3, 4].map(i => (
              <Skeleton key={i} height="180px" />
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="section-card agent-activity">
        <div className="card-header">
          <h3>Agent Activity</h3>
        </div>
        <div className="card-content error">
          <p>Error: {error}</p>
          <button onClick={fetchActivity}>Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className="section-card agent-activity">
      <div className="card-header">
        <h3>Agents</h3>
        <span className="live-indicator">● LIVE</span>
      </div>
      
      {/* Agent Status Cards - 2×2 Grid */}
      <div className="agent-cards-grid">
        {AGENTS.map(agent => {
          const data = displayData[agent.id] || getDemoAgentData(agent.id)
          const statusColor = getStatusColor(data.status)
          
          return (
            <div key={agent.id} className={`agent-card ${data.status}`}>
              <div className="agent-card-header">
                <AgentStatusDot status={statusColor} size="large" pulse={data.status === 'running'} />
                <span className="agent-name">{agent.name}</span>
                <span className="agent-status-label">{data.status?.toUpperCase() || 'IDLE'}</span>
              </div>
              
              <div className="agent-card-body">
                <div className="agent-metrics">
                  <div className="agent-metric">
                    <span className="metric-label">Last run:</span>
                    <span className="metric-value">{formatTimestamp(data.lastRun || data.last_run)}</span>
                  </div>
                  <div className="agent-metric">
                    <span className="metric-label">Duration:</span>
                    <span className="metric-value">{formatDuration(data.duration)}</span>
                  </div>
                  <div className="agent-metric">
                    <span className="metric-label">Processed:</span>
                    <span className="metric-value">{data.processed || data.items_processed || 0} items</span>
                  </div>
                </div>
                
                {data.lastOutput && (
                  <div className="agent-last-output">
                    <span className="output-label">Last output:</span>
                    <p className="output-text">"{data.lastOutput}"</p>
                  </div>
                )}
                
                {data.trace_id && (
                  <a 
                    href={getLangfuseLink(data.trace_id)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="langfuse-link"
                  >
                    View Langfuse trace ↗
                  </a>
                )}
              </div>
            </div>
          )
        })}
      </div>
      
      {/* Run History Timeline */}
      <div className="run-history-section">
        <div className="section-subheader">
          <h4>Run History</h4>
          <select 
            value={agentFilter} 
            onChange={(e) => setAgentFilter(e.target.value)}
            className="control-select small"
          >
            <option value="all">All Agents</option>
            {AGENTS.map(agent => (
              <option key={agent.id} value={agent.id}>{agent.name}</option>
            ))}
          </select>
        </div>
        
        <div className="timeline-container">
          {sortedDays.slice(0, 7).map(day => (
            <div key={day} className="timeline-day">
              <div className="timeline-date">
                <span className="date-label">{
                  new Date(day).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
                }</span>
              </div>
              <div className="timeline-runs">
                {runsByDay[day]
                  .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
                  .slice(0, 12)
                  .map(run => (
                    <div 
                      key={run.id}
                      className={`timeline-run ${run.status}`}
                      title={`${AGENTS.find(a => a.id === run.agent_id)?.name || run.agent_id} - ${formatDuration(run.duration)} - ${new Date(run.timestamp).toLocaleTimeString()}`}
                    >
                      <span className="run-indicator"></span>
                    </div>
                  ))
                }
              </div>
            </div>
          ))}
        </div>
        
        <div className="timeline-legend">
          <div className="legend-item"><span className="legend-dot success"></span> Success</div>
          <div className="legend-item"><span className="legend-dot warning"></span> Warning</div>
          <div className="legend-item"><span className="legend-dot error"></span> Error</div>
        </div>
      </div>
      
      {/* GitHub Sync Status */}
      <div className="github-sync-card">
        <div className="sync-header">
          <span className="sync-icon">🐙</span>
          <span className="sync-title">GITHUB SYNC</span>
        </div>
        <div className="sync-details">
          <div className="sync-detail">
            <span className="detail-label">Last sync:</span>
            <span className="detail-value">4 minutes ago</span>
          </div>
          <div className="sync-detail">
            <span className="detail-label">Next sync:</span>
            <span className="detail-value">in 5h 56m</span>
          </div>
          <div className="sync-detail">
            <span className="detail-label">Issues processed today:</span>
            <span className="detail-value">12</span>
          </div>
          <div className="sync-detail">
            <span className="detail-label">Cache size:</span>
            <span className="detail-value">847 issues</span>
          </div>
        </div>
        <button className="btn-sync-now">Run sync now →</button>
      </div>
    </div>
  )
}

export default AgentActivity
