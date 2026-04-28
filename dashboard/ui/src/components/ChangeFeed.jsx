import React, { useEffect, useState } from 'react'
import { Skeleton } from './ui/Skeleton'
import { TypeBadge } from './ui/TypeBadge'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

const EVENT_TYPES = {
  'new_incident': { label: 'NEW INCIDENT', color: 'critical', icon: '●' },
  'priority_shift_up': { label: 'PRIORITY SHIFT', color: 'low', icon: '▲' },
  'priority_shift_down': { label: 'PRIORITY SHIFT', color: 'medium', icon: '▼' },
  'strategy_generated': { label: 'STRATEGY GENERATED', color: 'strategy', icon: '◈' },
  'resolved': { label: 'RESOLVED', color: 'low', icon: '✓' },
  'worsening': { label: 'CLUSTER WORSENING', color: 'high', icon: '↑' },
  'verified_effective': { label: 'VERIFIED EFFECTIVE', color: 'low', icon: '✓' },
  'agent_failure': { label: 'AGENT FAILURE', color: 'critical', icon: '⚠' },
  'default': { label: 'EVENT', color: 'info', icon: '•' }
}

const AGENTS = ['ingestion', 'pattern', 'scoring', 'strategy', 'all']

const ChangeFeed = ({ limit = 50, sinceHours = 24 }) => {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [eventTypeFilter, setEventTypeFilter] = useState('all')
  const [agentFilter, setAgentFilter] = useState('all')
  const [timeFilter, setTimeFilter] = useState('today')
  const [searchQuery, setSearchQuery] = useState('')

  useEffect(() => {
    fetchChanges()
    
    // Set up auto-refresh every 60 seconds
    const interval = setInterval(fetchChanges, 60000)
    return () => clearInterval(interval)
  }, [limit, sinceHours])

  const fetchChanges = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${API_BASE_URL}/feed?limit=${limit}&since_hours=${sinceHours}`)
      if (!response.ok) throw new Error('Failed to fetch feed')
      const data = await response.json()
      setEvents(data.events || [])
      setLoading(false)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const getEventConfig = (eventType, severity) => {
    if (eventType?.includes('incident')) return EVENT_TYPES.new_incident
    if (eventType?.includes('priority') && severity === 'improved') return EVENT_TYPES.priority_shift_up
    if (eventType?.includes('priority')) return EVENT_TYPES.priority_shift_down
    if (eventType?.includes('strategy')) return EVENT_TYPES.strategy_generated
    if (eventType?.includes('resolved')) return EVENT_TYPES.resolved
    if (eventType?.includes('worsening')) return EVENT_TYPES.worsening
    if (eventType?.includes('verified')) return EVENT_TYPES.verified_effective
    if (eventType?.includes('failure') || severity === 'error') return EVENT_TYPES.agent_failure
    return EVENT_TYPES.default
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
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  const isSameDay = (date1, date2) => {
    const d1 = new Date(date1)
    const d2 = new Date(date2)
    return d1.getFullYear() === d2.getFullYear() &&
           d1.getMonth() === d2.getMonth() &&
           d1.getDate() === d2.getDate()
  }

  const getDateLabel = (dateStr) => {
    const date = new Date(dateStr)
    const now = new Date()
    const yesterday = new Date(now)
    yesterday.setDate(yesterday.getDate() - 1)
    
    if (isSameDay(date, now)) return 'Today'
    if (isSameDay(date, yesterday)) return 'Yesterday'
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }

  // Generate sample events for demo
  const generateSampleEvents = () => {
    const samples = [
      {
        id: 'evt-1',
        event_type: 'new_incident',
        severity: 'critical',
        title: 'INC-2026-0051 opened — matched cluster',
        description: '"Connector Response Drift" (confidence 0.91)',
        node_type: 'Incident',
        node_id: 'INC-2026-0051',
        created_at: new Date(Date.now() - 2 * 60000).toISOString()
      },
      {
        id: 'evt-2',
        event_type: 'priority_shift_up',
        severity: 'improved',
        title: 'Action item #433 jumped rank 8 → 2',
        description: 'Forward score increased: 4 → 9 after new incident',
        node_type: 'ActionItem',
        node_id: 'ACT-433',
        created_at: new Date(Date.now() - 18 * 60000).toISOString()
      },
      {
        id: 'evt-3',
        event_type: 'strategy_generated',
        severity: 'info',
        title: '"Connector Contract Test Suite" created',
        description: 'Est. 34% reduction in connector onboarding incidents',
        node_type: 'Strategy',
        node_id: 'STR-15',
        created_at: new Date(Date.now() - 60 * 60000).toISOString()
      },
      {
        id: 'evt-4',
        event_type: 'resolved',
        severity: 'low',
        title: 'Action item #401 marked resolved by @praveenvijay',
        description: 'Monitoring window started — 30 days',
        node_type: 'ActionItem',
        node_id: 'ACT-401',
        created_at: new Date(Date.now() - 3 * 3600000).toISOString()
      },
      {
        id: 'evt-5',
        event_type: 'worsening',
        severity: 'high',
        title: '"Scheduler Idempotency Failures" changed',
        description: 'stable → worsening (3 incidents in 45 days)',
        node_type: 'PatternCluster',
        node_id: 'CLU-23',
        created_at: new Date(Date.now() - 12 * 3600000).toISOString()
      },
      {
        id: 'evt-6',
        event_type: 'verified_effective',
        severity: 'low',
        title: 'Action item #388 verified effective',
        description: '0 new incidents in "Config Drift" cluster over 30 days',
        node_type: 'ActionItem',
        node_id: 'ACT-388',
        created_at: new Date(Date.now() - 2 * 86400000).toISOString()
      }
    ]
    return samples
  }

  const getDisplayEvents = () => {
    if (events.length > 0) return events
    return generateSampleEvents()
  }

  // Filter events
  let filteredEvents = getDisplayEvents()
  
  if (eventTypeFilter !== 'all') {
    filteredEvents = filteredEvents.filter(e => e.event_type === eventTypeFilter)
  }
  
  if (agentFilter !== 'all') {
    filteredEvents = filteredEvents.filter(e => e.agent_name === agentFilter)
  }
  
  if (timeFilter === 'today') {
    const today = new Date()
    filteredEvents = filteredEvents.filter(e => isSameDay(new Date(e.created_at), today))
  } else if (timeFilter === 'week') {
    const weekAgo = new Date(Date.now() - 7 * 86400000)
    filteredEvents = filteredEvents.filter(e => new Date(e.created_at) >= weekAgo)
  }
  
  if (searchQuery) {
    const query = searchQuery.toLowerCase()
    filteredEvents = filteredEvents.filter(e => 
      (e.title && e.title.toLowerCase().includes(query)) ||
      (e.description && e.description.toLowerCase().includes(query)) ||
      (e.node_id && e.node_id.toLowerCase().includes(query))
    )
  }

  // Group events by day
  const groupEventsByDay = (events) => {
    const groups = []
    let currentGroup = null
    
    events.forEach(event => {
      const dateLabel = getDateLabel(event.created_at)
      
      if (!currentGroup || currentGroup.dateLabel !== dateLabel) {
        currentGroup = { dateLabel, events: [] }
        groups.push(currentGroup)
      }
      
      currentGroup.events.push(event)
    })
    
    return groups
  }

  const eventGroups = groupEventsByDay(filteredEvents)
  const eventTypes = [...new Set(getDisplayEvents().map(e => e.event_type))]

  if (loading && events.length === 0) {
    return (
      <div className="section-card change-feed">
        <div className="card-header">
          <h3>Feed</h3>
          <span className="live-indicator">● LIVE</span>
        </div>
        <div className="card-content">
          {[1, 2, 3, 4, 5].map(i => (
            <Skeleton key={i} height="52px" style={{ marginBottom: '8px' }} />
          ))}
        </div>
      </div>
    )
  }

  if (error && events.length === 0) {
    return (
      <div className="section-card change-feed">
        <div className="card-header">
          <h3>Feed</h3>
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
        <h3>Feed</h3>
        <span className="live-indicator">● LIVE</span>
        <span className="item-count">{filteredEvents.length} events</span>
      </div>
      
      {/* Filter Bar */}
      <div className="card-controls sticky">
        <select 
          value={eventTypeFilter} 
          onChange={(e) => setEventTypeFilter(e.target.value)}
          className="control-select"
        >
          <option value="all">All events</option>
          {eventTypes.map(type => (
            <option key={type} value={type}>
              {EVENT_TYPES[type]?.label || type.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
        
        <select 
          value={agentFilter} 
          onChange={(e) => setAgentFilter(e.target.value)}
          className="control-select"
        >
          <option value="all">All agents</option>
          {AGENTS.filter(a => a !== 'all').map(agent => (
            <option key={agent} value={agent}>{agent}</option>
          ))}
        </select>
        
        <select 
          value={timeFilter} 
          onChange={(e) => setTimeFilter(e.target.value)}
          className="control-select"
        >
          <option value="today">Today</option>
          <option value="week">Last 7 days</option>
          <option value="all">All time</option>
        </select>
        
        <input
          type="text"
          placeholder="Search events..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="control-input search"
        />
        
        <button onClick={fetchChanges} className="btn-refresh" title="Refresh">
          🔄
        </button>
      </div>
      
      <div className="card-content">
        <div className="feed-list">
          {filteredEvents.length === 0 ? (
            <p className="empty-state">No events in the selected time range</p>
          ) : (
            eventGroups.map((group, groupIndex) => (
              <React.Fragment key={group.dateLabel}>
                {/* Date Separator */}
                <div className="date-separator">
                  <span className="date-label">{group.dateLabel}</span>
                  <span className="date-line"></span>
                </div>
                
                {/* Events for this day */}
                {group.events.map((event) => {
                  const config = getEventConfig(event.event_type, event.severity)
                  
                  return (
                    <div 
                      key={event.id} 
                      className={`feed-item ${config.color}`}
                    >
                      <div className="feed-icon">
                        {config.icon}
                      </div>
                      
                      <div className="feed-content">
                        <div className="feed-header">
                          <span className="event-type-label">{config.label}</span>
                          <span className="feed-time">
                            {formatTimestamp(event.created_at)}
                          </span>
                        </div>
                        
                        <h4 className="feed-title">{event.title}</h4>
                        
                        {event.description && (
                          <p className="feed-description">{event.description}</p>
                        )}
                        
                        <div className="feed-actions">
                          <button className="feed-action-link">
                            View {event.node_type} →
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </React.Fragment>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

export default ChangeFeed
