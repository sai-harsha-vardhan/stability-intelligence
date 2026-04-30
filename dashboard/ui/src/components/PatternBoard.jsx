import React, { useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const PatternBoard = ({ limit = 20, onViewInGraph = null }) => {
  const [clusters, setClusters] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedTrend, setSelectedTrend] = useState('all')

  useEffect(() => {
    fetchPatterns()
  }, [limit])

  const fetchPatterns = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${API_BASE_URL}/patterns`)
      if (!response.ok) throw new Error('Failed to fetch patterns')
      const data = await response.json()
      setClusters(data.clusters || [])
      setLoading(false)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const getTrendIcon = (trend) => {
    if (trend === 'worsening') return '↗️'
    if (trend === 'improving') return '↘️'
    return '→'
  }

  const getTrendClass = (trend) => {
    if (trend === 'worsening') return 'trend-worsening'
    if (trend === 'improving') return 'trend-improving'
    return 'trend-stable'
  }

  const getFrequencyClass = (frequency) => {
    if (frequency >= 10) return 'freq-high'
    if (frequency >= 5) return 'freq-medium'
    return 'freq-low'
  }

  const filteredClusters = clusters
    .filter(cluster => selectedTrend === 'all' || cluster.trend === selectedTrend)
    .slice(0, limit)

  const trendCounts = clusters.reduce((acc, c) => {
    acc[c.trend] = (acc[c.trend] || 0) + 1
    return acc
  }, {})

  if (loading) {
    return (
      <div className="section-card pattern-board">
        <div className="card-header">
          <h3>Pattern Board</h3>
        </div>
        <div className="card-content loading">
          <div className="loading-spinner small"></div>
          <p>Loading patterns...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="section-card pattern-board">
        <div className="card-header">
          <h3>Pattern Board</h3>
        </div>
        <div className="card-content error">
          <p>Error: {error}</p>
          <button onClick={fetchPatterns}>Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className="section-card pattern-board">
      <div className="card-header">
        <h3>Pattern Clusters</h3>
        <span className="item-count">{filteredClusters.length} clusters</span>
      </div>
      
      <div className="card-controls">
        <div className="trend-filters">
          <button 
            className={`filter-btn ${selectedTrend === 'all' ? 'active' : ''}`}
            onClick={() => setSelectedTrend('all')}
          >
            All ({clusters.length})
          </button>
          <button 
            className={`filter-btn ${selectedTrend === 'worsening' ? 'active' : ''} trend-worsening`}
            onClick={() => setSelectedTrend('worsening')}
          >
            ↗️ Worsening ({trendCounts.worsening || 0})
          </button>
          <button 
            className={`filter-btn ${selectedTrend === 'stable' ? 'active' : ''} trend-stable`}
            onClick={() => setSelectedTrend('stable')}
          >
            → Stable ({trendCounts.stable || 0})
          </button>
          <button 
            className={`filter-btn ${selectedTrend === 'improving' ? 'active' : ''} trend-improving`}
            onClick={() => setSelectedTrend('improving')}
          >
            ↘️ Improving ({trendCounts.improving || 0})
          </button>
        </div>
        <button onClick={fetchPatterns} className="btn-refresh" title="Refresh">
          🔄
        </button>
      </div>
      
      <div className="card-content">
        <div className="pattern-grid">
          {filteredClusters.length === 0 ? (
            <p className="empty-state">No pattern clusters found</p>
          ) : (
            filteredClusters.map((cluster) => (
              <div key={cluster.id} className="pattern-card">
                <div className={`pattern-header ${getTrendClass(cluster.trend)}`}>
                  <span className="trend-icon">{getTrendIcon(cluster.trend)}</span>
                  <span className="trend-label">{cluster.trend}</span>
                  <span className={`frequency-badge ${getFrequencyClass(cluster.frequency)}`}>
                    {cluster.frequency} incidents
                  </span>
                </div>
                
                <h4 className="pattern-name">{cluster.name}</h4>
                
                {cluster.description && (
                  <p className="pattern-description">{cluster.description}</p>
                )}
                
                <div className="pattern-metrics">
                  <div className="metric">
                    <span className="metric-value">{cluster.incident_count}</span>
                    <span className="metric-label">Incidents</span>
                  </div>
                  <div className="metric">
                    <span className="metric-value">{cluster.open_action_items}</span>
                    <span className="metric-label">Open Actions</span>
                  </div>
                  <div className="metric">
                    <span className="metric-value">{cluster.strategies}</span>
                    <span className="metric-label">Strategies</span>
                  </div>
                </div>
                
                {cluster.affected_components && cluster.affected_components.length > 0 && (
                  <div className="affected-components">
                    <span className="components-label">Components:</span>
                    <div className="components-list">
                      {cluster.affected_components.slice(0, 5).map((comp, idx) => (
                        <span key={idx} className="component-tag">{comp}</span>
                      ))}
                      {cluster.affected_components.length > 5 && (
                        <span className="component-more">
                          +{cluster.affected_components.length - 5} more
                        </span>
                      )}
                    </div>
                  </div>
                )}
                
                <button 
                  className="view-in-graph-btn"
                  onClick={() => onViewInGraph?.(cluster.id)}
                  disabled={!onViewInGraph}
                >
                  View in Graph →
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

export default PatternBoard
