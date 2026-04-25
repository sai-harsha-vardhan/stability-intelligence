import React, { useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const POLL_INTERVAL = 30000 // 30 seconds

const SystemHealth = ({ fullWidth = false }) => {
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  useEffect(() => {
    fetchHealth()
    
    // Set up polling every 30 seconds
    const interval = setInterval(fetchHealth, POLL_INTERVAL)
    return () => clearInterval(interval)
  }, [])

  const fetchHealth = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/health`)
      if (!response.ok) throw new Error('Failed to fetch health status')
      const data = await response.json()
      setHealth(data)
      setLastUpdated(new Date())
      setLoading(false)
      setError(null)
    } catch (err) {
      setError(err.message)
      setLoading(false)
      setHealth({
        status: 'error',
        overall_healthy: false,
        components: {},
        timestamp: new Date().toISOString()
      })
    }
  }

  const getStatusIcon = (status) => {
    if (status === 'healthy' || status === 'fresh') return '✅'
    if (status === 'degraded') return '⚠️'
    if (status === 'unhealthy' || status === 'stale') return '❌'
    if (status === 'error') return '🔴'
    return '❓'
  }

  const getStatusClass = (status) => {
    if (status === 'healthy' || status === 'fresh') return 'status-healthy'
    if (status === 'degraded') return 'status-degraded'
    if (status === 'unhealthy' || status === 'stale' || status === 'error') return 'status-unhealthy'
    return 'status-unknown'
  }

  const getComponentIcon = (componentName) => {
    const icons = {
      'Neo4j Graph Database': '🗄️',
      'LiteLLM Gateway': '🧠',
      'Graph Data Freshness': '📊'
    }
    return icons[componentName] || '🔧'
  }

  const formatTimeSince = (timestamp) => {
    if (!timestamp) return 'Never'
    const date = new Date(timestamp)
    const now = new Date()
    const diffMs = now - date
    const diffSecs = Math.floor(diffMs / 1000)
    const diffMins = Math.floor(diffMs / 60000)
    
    if (diffSecs < 60) return `${diffSecs}s ago`
    if (diffMins < 60) return `${diffMins}m ago`
    return date.toLocaleTimeString()
  }

  if (loading) {
    return (
      <div className={`section-card system-health ${fullWidth ? 'full-width' : ''}`}>
        <div className="card-header">
          <h3>System Health</h3>
          <span className="polling-indicator">● Polling (30s)</span>
        </div>
        <div className="card-content loading">
          <div className="loading-spinner small"></div>
          <p>Checking system health...</p>
        </div>
      </div>
    )
  }

  const components = health?.components || {}

  return (
    <div className={`section-card system-health ${fullWidth ? 'full-width' : ''}`}>
      <div className="card-header">
        <h3>System Health</h3>
        <div className="header-right">
          <span className="polling-indicator">● Polling (30s)</span>
          <span className={`overall-status ${getStatusClass(health?.status)}`}>
            {getStatusIcon(health?.status)} {health?.status?.toUpperCase()}
          </span>
        </div>
      </div>
      
      <div className="card-controls">
        <span className="last-updated">
          Last updated: {lastUpdated ? formatTimeSince(lastUpdated) : 'Never'}
        </span>
        <button onClick={fetchHealth} className="btn-refresh" title="Refresh now">
          🔄 Refresh
        </button>
      </div>
      
      <div className="card-content">
        {error && !health && (
          <div className="error-banner">
            <p>⚠️ Unable to connect to API: {error}</p>
          </div>
        )}
        
        <div className="health-grid">
          {Object.entries(components).map(([key, component]) => (
            <div 
              key={key} 
              className={`health-card ${getStatusClass(component.status)}`}
            >
              <div className="health-card-header">
                <span className="component-icon">{getComponentIcon(component.name)}</span>
                <span className="component-name">{component.name}</span>
                <span className="component-status">
                  {getStatusIcon(component.status)} {component.status}
                </span>
              </div>
              
              <div className="health-card-body">
                {component.latency_ms > 0 && (
                  <div className="health-metric">
                    <span className="metric-label">Latency:</span>
                    <span className="metric-value">{component.latency_ms.toFixed(2)} ms</span>
                  </div>
                )}
                
                <div className="health-metric">
                  <span className="metric-label">Checked:</span>
                  <span className="metric-value">
                    {formatTimeSince(component.last_check)}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
        
        {fullWidth && (
          <div className="health-details">
            <h4>System Information</h4>
            <div className="info-grid">
              <div className="info-item">
                <span className="info-label">Overall Status:</span>
                <span className={`info-value ${getStatusClass(health?.status)}`}>
                  {health?.overall_healthy ? 'Healthy' : 'Unhealthy'}
                </span>
              </div>
              <div className="info-item">
                <span className="info-label">API Endpoint:</span>
                <span className="info-value">{API_BASE_URL}</span>
              </div>
              <div className="info-item">
                <span className="info-label">Poll Interval:</span>
                <span className="info-value">{POLL_INTERVAL / 1000} seconds</span>
              </div>
              <div className="info-item">
                <span className="info-label">Timestamp:</span>
                <span className="info-value">
                  {health?.timestamp ? new Date(health.timestamp).toLocaleString() : 'N/A'}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default SystemHealth
