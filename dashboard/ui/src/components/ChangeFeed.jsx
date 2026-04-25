import React, { useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const ChangeFeed = ({ limit = 50, sinceHours = 24 }) => {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [eventTypeFilter, setEventTypeFilter] = useState('all')

  useEffect(() => {
    fetchChanges()
    
    // Set up auto-refresh every 60 seconds
    const interval = setInterval(fetchChanges, 60000)
    return () => clearInterval(interval)
  }, [limit, sinceHours])

  const fetchChanges = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/change-feed?limit=${limit}&since_hours=${sinceHours}`)
      if (!response.ok) throw new Error('Failed to fetch changes')
      const data = await response.json()
      setEvents(data.events || [])
      setLoading(false)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const getEventIcon = (eventType, nodeType) => {
    if (eventType.includes('issue')) return '🐙'
    if (eventType.includes('pattern')) return '🔍'
    if (eventType.includes('strategy')) return '🎯'
    if (eventType.includes('incident')) return '🔥'
    if (eventType.includes('action')) return '⚡'
    if (nodeType === 'Incident') return '🔴'
    if (nodeType === 'ActionItem') return '🟢'
    if (nodeType === 'RootCause') return '🟠'
    if (nodeType === 'PatternCluster') return '🟣'
    if (nodeType === 'Strategy') return '🟡'
    return '📝'
  }

  const getSeverityClass = (severity) => {
    if (severity === 'critical') return 'severity-critical'
    if (severity === 'high') return 'severity-high'
    if (severity === 'medium') return 'severity-medium'
    if (severity === 'low') return 'severity-low'
    return 'severity-none'
  }

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'Unknown'
    const date = new Date(timestamp)
    const now = new Date()
    const diffMs = now - date
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    
    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    return date.toLocaleString()
  }

  const getEventTypeLabel = (eventType) => {
    return eventType
      .replace(/_/g, ' ')
      .replace(/\b\w/g, l => l.toUpperCase())
  }

  const eventTypes = [...new Set(events.map(e => e.event_type))]
  
  const filteredEvents = eventTypeFilter === 'all' 
    ? events 
    : events.filter(e => e.event_type === eventTypeFilter)

  if (loading) {
    return (
      <div className="section-card change-feed">
        <div className="card-header">
          <h3>Change Feed</h3>
          <span className="live-indicator">● LIVE</span>
        </div>
        <div className="card-content loading">
          <div className="loading-spinner small"></div>
          <p>Loading changes...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="section-card change-feed">
        <div className="card-header">
          <h3>Change Feed</h3>
        </div>
        <div className="card-content error">
          <p>Error: {error}</p>
          <button onClick={fetchChanges}>Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className="section-card change-feed">
      <div className="card-header">
        <h3>Change Feed</h3>
        <span className="live-indicator">● LIVE</span>
        <span className="item-count">{filteredEvents.length} events</span>
      </div>
      
      <div className="card-controls">
        <select 
          value={eventTypeFilter} 
          onChange={(e) => setEventTypeFilter(e.target.value)}
          className="control-select"
        >
          <option value="all">All Types</option>
          {eventTypes.map(type => (
            <option key={type} value={type}>{getEventTypeLabel(type)}</option>
          ))}
        </select>
        <button onClick={fetchChanges} className="btn-refresh" title="Refresh">
          🔄
        </button>
      </div>
      
      <div className="card-content">
        <div className="change-list">
          {filteredEvents.length === 0 ? (
            <p className="empty-state">No changes in the last {sinceHours} hours</p>
          ) : (
            filteredEvents.map((event) => (
              <div 
                key={event.id} 
                className={`change-item ${getSeverityClass(event.severity)}`}
              >
                <div className="change-icon">
                  {getEventIcon(event.event_type, event.node_type)}
                </div>
                
                <div className="change-content">
                  <div className="change-header">
                    <span className="event-type">{getEventTypeLabel(event.event_type)}</span>
                    <span className="node-type-badge">{event.node_type}</span>
                    {event.severity && (
                      <span className={`severity-badge ${getSeverityClass(event.severity)}`}>
                        {event.severity}
                      </span>
                    )}
                    <span className="change-time">
                      {formatTimestamp(event.created_at)}
                    </span>
                  </div>
                  
                  <h4 className="change-title">{event.title}</h4>
                  
                  <p className="change-description">{event.change_description}</p>
                  
                  <div className="change-meta">
                    <span className="node-id">ID: {event.node_id}</span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

export default ChangeFeed
