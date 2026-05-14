import React, { useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const LANGFUSE_BASE_URL = import.meta.env.VITE_LANGFUSE_URL || 'http://localhost:3000'

const AgentActivity = ({ limit = 50 }) => {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [agentFilter, setAgentFilter] = useState('all')

  useEffect(() => {
    fetchActivity()
  }, [limit])

  const fetchActivity = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${API_BASE_URL}/activity?limit=${limit}`)
      if (!response.ok) throw new Error('Failed to fetch activity')
      const data = await response.json()
      setEvents(data.events || [])
      setLoading(false)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const getAgentIcon = (agentName) => {
    const icons = {
      'ingestion': '📥',
      'pattern': '🔍',
      'impact': '🎯',
      'strategy': '🧠',
      'feedback': '🔄',
      'health': '❤️',
      'github_sync': '🐙'
    }
    
    for (const [key, icon] of Object.entries(icons)) {
      if (agentName.toLowerCase().includes(key)) return icon
    }
    return '🤖'
  }

  const getEventTypeClass = (eventType) => {
    if (eventType.includes('success') || eventType.includes('completed')) return 'event-success'
    if (eventType.includes('error') || eventType.includes('failed')) return 'event-error'
    if (eventType.includes('start')) return 'event-start'
    if (eventType.includes('detect')) return 'event-detect'
    return 'event-default'
  }

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Unknown'
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

  const agents = [...new Set(events.map(e => e.agent_name))]
  
  const filteredEvents = agentFilter === 'all' 
    ? events 
    : events.filter(e => e.agent_name === agentFilter)

  const agentStats = events.reduce((acc, event) => {
    const agent = event.agent_name
    if (!acc[agent]) {
      acc[agent] = { total: 0, success: 0, error: 0 }
    }
    acc[agent].total++
    if (event.event_type.includes('success') || event.event_type.includes('completed')) {
      acc[agent].success++
    } else if (event.event_type.includes('error') || event.event_type.includes('failed')) {
      acc[agent].error++
    }
    return acc
  }, {})

  if (loading) {
    return (
      <div className="section-card agent-activity">
        <div className="card-header">
          <h3>Agent Activity</h3>
        </div>
        <div className="card-content loading">
          <div className="loading-spinner small"></div>
          <p>Loading activity...</p>
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
        <h3>Agent Activity</h3>
        <span className="item-count">{filteredEvents.length} events</span>
      </div>
      
      {Object.keys(agentStats).length > 0 && (
        <div className="agent-stats-bar">
          {Object.entries(agentStats).slice(0, 4).map(([agent, stats]) => (
            <div key={agent} className="agent-stat">
              <span className="agent-icon">{getAgentIcon(agent)}</span>
              <span className="agent-name">{agent}</span>
              <span className="agent-count">{stats.total}</span>
            </div>
          ))}
        </div>
      )}
      
      <div className="card-controls">
        <select 
          value={agentFilter} 
          onChange={(e) => setAgentFilter(e.target.value)}
          className="control-select"
        >
          <option value="all">All Agents</option>
          {agents.map(agent => (
            <option key={agent} value={agent}>{agent}</option>
          ))}
        </select>
        <button onClick={fetchActivity} className="btn-refresh" title="Refresh">
          🔄
        </button>
      </div>
      
      <div className="card-content">
        <div className="activity-list">
          {filteredEvents.length === 0 ? (
            <p className="empty-state">No agent activity found</p>
          ) : (
            filteredEvents.map((event) => {
              const langfuseLink = getLangfuseLink(event.details?.trace_id)
              
              return (
                <div 
                  key={event.id} 
                  className={`activity-item ${getEventTypeClass(event.event_type)}`}
                >
                  <div className="activity-icon">
                    {getAgentIcon(event.agent_name)}
                  </div>
                  
                  <div className="activity-content">
                    <div className="activity-header">
                      <span className="agent-name">{event.agent_name}</span>
                      <span className={`event-type ${getEventTypeClass(event.event_type)}`}>
                        {event.event_type}
                      </span>
                      <span className="activity-time">
                        {formatTimestamp(event.created_at)}
                      </span>
                    </div>
                    
                    <p className="activity-message">{event.message}</p>
                    
                    {event.details && Object.keys(event.details).length > 0 && (
                      <div className="activity-details">
                        {Object.entries(event.details)
                          .filter(([key]) => key !== 'trace_id')
                          .slice(0, 3)
                          .map(([key, value]) => (
                            <span key={key} className="detail-chip">
                              {key}: {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                            </span>
                          ))}
                      </div>
                    )}
                  </div>
                  
                  <div className="activity-actions">
                    {langfuseLink && (
                      <a 
                        href={langfuseLink} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="langfuse-link"
                        title="View in Langfuse"
                      >
                        🔍 Langfuse
                      </a>
                    )}
                    
                    {event.linked_node_id && event.linked_node_type === 'langfuse_trace' ? (
                      <a
                        href={`${LANGFUSE_BASE_URL}/traces/${event.linked_node_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="langfuse-trace-link"
                        title={`View Langfuse trace: ${event.linked_node_id}`}
                      >
                        View Langfuse trace ↗
                      </a>
                    ) : event.linked_node_id && (
                      <button 
                        className="view-node-btn"
                        title={`View ${event.linked_node_type}: ${event.linked_node_id}`}
                      >
                        📄 View
                      </button>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
      
      <div className="card-footer">
        <a 
          href={LANGFUSE_BASE_URL} 
          target="_blank" 
          rel="noopener noreferrer"
          className="langfuse-dashboard-link"
        >
          Open Langfuse Dashboard →
        </a>
      </div>
    </div>
  )
}

export default AgentActivity
