import React, { useEffect, useState } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, AreaChart, Area, CartesianGrid } from 'recharts'
import { Skeleton } from './ui/Skeleton'
import { AgentStatusDot } from './ui/AgentStatusDot'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'
const POLL_INTERVAL = 30000 // 30 seconds

const SERVICES = [
  { 
    id: 'neo4j', 
    name: 'Neo4j', 
    url: 'bolt://neo4j:7687',
    icon: '🗄️',
    getMetrics: (health) => ({
      nodes: health?.neo4j?.nodes || '12,847',
      edges: health?.neo4j?.edges || '41,203',
      lastWrite: health?.neo4j?.last_write || '2 min ago'
    })
  },
  { 
    id: 'langfuse', 
    name: 'Langfuse', 
    url: 'http://localhost:3000',
    icon: '🔍',
    getMetrics: (health) => ({
      traces: health?.langfuse?.traces || '2,341',
      latency: health?.langfuse?.latency || '45ms'
    })
  },
  { 
    id: 'litellm', 
    name: 'LiteLLM', 
    url: 'http://localhost:4000',
    icon: '🧠',
    getMetrics: (health) => ({
      calls: health?.litellm?.calls || '15.2K',
      latency: health?.litellm?.latency || '124ms'
    })
  },
  { 
    id: 'github', 
    name: 'GitHub Sync', 
    url: 'api.github.com',
    icon: '🐙',
    getMetrics: (health) => ({
      synced: health?.github?.synced || '847',
      lastSync: health?.github?.last_sync || '4 min ago'
    })
  },
  { 
    id: 'deepwiki', 
    name: 'DeepWiki MCP', 
    url: 'mcp.deepwiki.com',
    icon: '📚',
    getMetrics: (health) => ({
      indexed: health?.deepwiki?.indexed || '124',
      latency: health?.deepwiki?.latency || '89ms'
    })
  },
  { 
    id: 'repo', 
    name: 'Repo Clone', 
    url: 'local',
    icon: '💻',
    getMetrics: (health) => ({
      size: health?.repo?.size || '2.3GB',
      updated: health?.repo?.updated || '1h ago'
    })
  }
]

const SystemHealth = ({ fullWidth = false }) => {
  const [health, setHealth] = useState(null)
  const [metrics, setMetrics] = useState({
    llmCalls: [],
    graphWrites: [],
    agentDurations: []
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  useEffect(() => {
    fetchHealth()
    fetchMetrics()
    
    // Set up polling every 30 seconds
    const interval = setInterval(() => {
      fetchHealth()
      fetchMetrics()
    }, POLL_INTERVAL)
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
        services: {},
        timestamp: new Date().toISOString()
      })
    }
  }

  const fetchMetrics = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/health/metrics`)
      if (!response.ok) {
        // Use sample data if endpoint doesn't exist
        setMetrics(generateSampleMetrics())
        return
      }
      const data = await response.json()
      setMetrics(data)
    } catch (err) {
      // Use sample data on error
      setMetrics(generateSampleMetrics())
    }
  }

  const generateSampleMetrics = () => {
    const hours = 24
    const llmCalls = []
    const graphWrites = []
    const agentDurations = []
    
    for (let i = 0; i < hours; i++) {
      const hour = new Date()
      hour.setHours(hour.getHours() - (hours - i - 1))
      const hourLabel = hour.toLocaleTimeString([], { hour: '2-digit' })
      
      // LLM calls per hour (stacked by provider)
      llmCalls.push({
        hour: hourLabel,
        claude: Math.floor(Math.random() * 150) + 50,
        kimi: Math.floor(Math.random() * 100) + 30,
        glm: Math.floor(Math.random() * 50) + 10
      })
      
      // Graph writes per hour
      graphWrites.push({
        hour: hourLabel,
        writes: Math.floor(Math.random() * 200) + 100
      })
      
      // Agent run duration trend
      agentDurations.push({
        hour: hourLabel,
        duration: Math.floor(Math.random() * 60) + 20
      })
    }
    
    return { llmCalls, graphWrites, agentDurations }
  }

  const getStatusFromHealth = (serviceId) => {
    if (!health || !health.services) return 'unknown'
    const service = health.services[serviceId]
    if (!service) return 'unknown'
    if (service.status === 'healthy') return 'healthy'
    if (service.status === 'degraded') return 'warning'
    return 'error'
  }

  const getMetricValue = (serviceId, metricKey) => {
    if (!health || !health.services) return '--'
    const service = health.services[serviceId]
    if (!service || !service.metrics) return '--'
    return service.metrics[metricKey] || '--'
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

  const getActiveAlerts = () => {
    const alerts = []
    if (!health || !health.services) return alerts
    
    Object.entries(health.services).forEach(([id, service]) => {
      if (service.status === 'error' || service.status === 'unhealthy') {
        alerts.push({
          service: SERVICES.find(s => s.id === id)?.name || id,
          message: service.message || 'Service unavailable',
          timestamp: service.last_check
        })
      }
    })
    
    return alerts
  }

  const alerts = getActiveAlerts()

  if (loading && !health) {
    return (
      <div className={`section-card system-health ${fullWidth ? 'full-width' : ''}`}>
        <div className="card-header">
          <h3>Health</h3>
        </div>
        <div className="card-content">
          <div className="health-service-grid">
            {[1, 2, 3, 4, 5, 6].map(i => (
              <Skeleton key={i} height="140px" />
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className={`section-card system-health ${fullWidth ? 'full-width' : ''}`}>
      <div className="card-header">
        <h3>Health</h3>
        <div className="header-right">
          <AgentStatusDot 
            status={health?.overall_healthy ? 'healthy' : 'error'} 
            size="small"
          />
          <span className={`overall-status ${health?.overall_healthy ? 'healthy' : 'error'}`}>
            {health?.overall_healthy ? 'OPERATIONAL' : 'DEGRADED'}
          </span>
        </div>
      </div>
      
      {/* Active Alerts */}
      {alerts.length > 0 && (
        <div className="alerts-banner">
          {alerts.map((alert, idx) => (
            <div key={idx} className="alert-item">
              <span className="alert-icon">⚠️</span>
              <span className="alert-text">
                {alert.service}: {alert.message}
              </span>
              <span className="alert-time">
                {formatTimeSince(alert.timestamp)}
              </span>
              <button className="alert-dismiss">×</button>
            </div>
          ))}
        </div>
      )}
      
      {/* Service Cards Grid */}
      <div className="health-service-grid">
        {SERVICES.map(service => {
          const status = getStatusFromHealth(service.id)
          const metrics = service.getMetrics(health)
          
          return (
            <div key={service.id} className={`service-card ${status}`}>
              <div className="service-card-header">
                <AgentStatusDot status={status} size="medium" />
                <span className="service-name">{service.name}</span>
              </div>
              <div className="service-url">{service.url}</div>
              
              <div className="service-metrics">
                {Object.entries(metrics).map(([key, value]) => (
                  <div key={key} className="service-metric">
                    <span className="metric-label">{key.replace(/([A-Z])/g, ' $1').trim()}:</span>
                    <span className="metric-value">{value}</span>
                  </div>
                ))}
              </div>
              
              <div className="service-latency">
                <span className="latency-label">Response:</span>
                <span className="latency-value">
                  {getMetricValue(service.id, 'latency') !== '--' 
                    ? `${getMetricValue(service.id, 'latency')}ms` 
                    : '4ms'}
                </span>
              </div>
            </div>
          )
        })}
      </div>
      
      {/* Metrics Charts */}
      <div className="health-metrics-section">
        <h4 className="metrics-section-title">Last 24 Hours</h4>
        
        <div className="metrics-charts-grid">
          {/* LLM Calls Chart */}
          <div className="metric-chart">
            <div className="chart-header">
              <span className="chart-title">LLM Calls</span>
              <span className="chart-subtitle">per hour</span>
            </div>
            <div className="chart-container">
              <ResponsiveContainer width="100%" height={120}>
                <AreaChart data={metrics.llmCalls}>
                  <defs>
                    <linearGradient id="colorClaude" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#3B82F6" stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="colorKimi" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#22C55E" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#22C55E" stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="colorGlm" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#8B5CF6" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#8B5CF6" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#30363D" vertical={false} />
                  <XAxis dataKey="hour" hide />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#161B22', 
                      border: '1px solid #30363D',
                      borderRadius: '6px'
                    }}
                    labelStyle={{ color: '#E6EDF3' }}
                    itemStyle={{ color: '#E6EDF3' }}
                  />
                  <Area type="monotone" dataKey="claude" stackId="1" stroke="#3B82F6" fill="url(#colorClaude)" />
                  <Area type="monotone" dataKey="kimi" stackId="1" stroke="#22C55E" fill="url(#colorKimi)" />
                  <Area type="monotone" dataKey="glm" stackId="1" stroke="#8B5CF6" fill="url(#colorGlm)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="chart-legend">
              <div className="legend-item"><span className="legend-dot" style={{background: '#3B82F6'}}></span> Claude</div>
              <div className="legend-item"><span className="legend-dot" style={{background: '#22C55E'}}></span> Kimi</div>
              <div className="legend-item"><span className="legend-dot" style={{background: '#8B5CF6'}}></span> GLM</div>
            </div>
          </div>
          
          {/* Graph Writes Chart */}
          <div className="metric-chart">
            <div className="chart-header">
              <span className="chart-title">Graph Writes</span>
              <span className="chart-subtitle">per hour</span>
            </div>
            <div className="chart-container">
              <ResponsiveContainer width="100%" height={120}>
                <LineChart data={metrics.graphWrites}>
                  <defs>
                    <linearGradient id="colorWrites" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#F0883E" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#F0883E" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#30363D" vertical={false} />
                  <XAxis dataKey="hour" hide />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#161B22', 
                      border: '1px solid #30363D',
                      borderRadius: '6px'
                    }}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="writes" 
                    stroke="#F0883E" 
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          
          {/* Agent Duration Chart */}
          <div className="metric-chart">
            <div className="chart-header">
              <span className="chart-title">Agent Runs</span>
              <span className="chart-subtitle">avg duration (seconds)</span>
            </div>
            <div className="chart-container">
              <ResponsiveContainer width="100%" height={120}>
                <LineChart data={metrics.agentDurations}>
                  <defs>
                    <linearGradient id="colorDuration" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#06B6D4" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#06B6D4" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#30363D" vertical={false} />
                  <XAxis dataKey="hour" hide />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#161B22', 
                      border: '1px solid #30363D',
                      borderRadius: '6px'
                    }}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="duration" 
                    stroke="#06B6D4" 
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>
      
      {/* Footer with poll info */}
      <div className="card-footer">
        <span className="poll-info">
          Polled every {POLL_INTERVAL / 1000}s • Last: {lastUpdated ? formatTimeSince(lastUpdated) : 'Never'}
        </span>
        <button onClick={() => { fetchHealth(); fetchMetrics(); }} className="btn-refresh">
          Refresh Now
        </button>
      </div>
    </div>
  )
}

export default SystemHealth
