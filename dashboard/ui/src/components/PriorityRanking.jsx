import React, { useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const PriorityRanking = ({ limit = 50, onViewInGraph = null }) => {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sortBy, setSortBy] = useState('priority_score')
  const [filterType, setFilterType] = useState('all')

  useEffect(() => {
    fetchPriorities()
  }, [limit])

  const fetchPriorities = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${API_BASE_URL}/priorities?limit=${limit}`)
      if (!response.ok) throw new Error('Failed to fetch priorities')
      const data = await response.json()
      setItems(data.items || [])
      setLoading(false)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const getScoreClass = (score) => {
    if (score >= 80) return 'score-critical'
    if (score >= 60) return 'score-high'
    if (score >= 40) return 'score-medium'
    return 'score-low'
  }

  const getTrendIcon = (trend) => {
    if (trend === 'worsening') return '↗️'
    if (trend === 'improving') return '↘️'
    return '→'
  }

  const getStatusBadgeClass = (status) => {
    const classes = {
      'open': 'status-open',
      'in_progress': 'status-progress',
      'resolved': 'status-resolved',
      'closed': 'status-closed',
      'proposed': 'status-proposed',
      'implemented': 'status-implemented'
    }
    return classes[status] || 'status-default'
  }

  const filteredItems = items
    .filter(item => filterType === 'all' || item.type === filterType)
    .sort((a, b) => {
      if (sortBy === 'priority_score') return b.priority_score - a.priority_score
      if (sortBy === 'forward_score') return b.forward_score - a.forward_score
      if (sortBy === 'backward_score') return b.backward_score - a.backward_score
      return 0
    })

  if (loading) {
    return (
      <div className="section-card priority-ranking">
        <div className="card-header">
          <h3>Priority Ranking</h3>
        </div>
        <div className="card-content loading">
          <div className="loading-spinner small"></div>
          <p>Loading priorities...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="section-card priority-ranking">
        <div className="card-header">
          <h3>Priority Ranking</h3>
        </div>
        <div className="card-content error">
          <p>Error: {error}</p>
          <button onClick={fetchPriorities}>Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className="section-card priority-ranking">
      <div className="card-header">
        <h3>Priority Ranking</h3>
        <span className="item-count">{filteredItems.length} items</span>
      </div>
      
      <div className="card-controls">
        <select 
          value={filterType} 
          onChange={(e) => setFilterType(e.target.value)}
          className="control-select"
        >
          <option value="all">All Types</option>
          <option value="action_item">Action Items</option>
          <option value="strategy">Strategies</option>
        </select>
        
        <select 
          value={sortBy} 
          onChange={(e) => setSortBy(e.target.value)}
          className="control-select"
        >
          <option value="priority_score">Priority Score</option>
          <option value="forward_score">Forward Score</option>
          <option value="backward_score">Backward Score</option>
        </select>
        
        <button onClick={fetchPriorities} className="btn-refresh" title="Refresh">
          🔄
        </button>
      </div>
      
      <div className="card-content">
        <div className="priority-list">
          {filteredItems.length === 0 ? (
            <p className="empty-state">No priority items found</p>
          ) : (
            filteredItems.map((item, index) => (
              <div 
                key={item.id} 
                className={`priority-item ${getScoreClass(item.priority_score)}`}
              >
                <div className="item-rank">#{index + 1}</div>
                
                <div className="item-content">
                  <div className="item-header">
                    <span className={`type-badge ${item.type}`}>
                      {item.type === 'action_item' ? '⚡ Action' : '🎯 Strategy'}
                    </span>
                    <span className={`status-badge ${getStatusBadgeClass(item.status)}`}>
                      {item.status}
                    </span>
                    {item.trend && (
                      <span className="trend-indicator" title={`Trend: ${item.trend}`}>
                        {getTrendIcon(item.trend)}
                      </span>
                    )}
                  </div>
                  
                  <h4 className="item-title">{item.title}</h4>
                  
                  {item.description && (
                    <p className="item-description">
                      {item.description.substring(0, 120)}
                      {item.description.length > 120 ? '...' : ''}
                    </p>
                  )}
                  
                  {item.pattern_clusters && item.pattern_clusters.length > 0 && (
                    <div className="pattern-tags">
                      {item.pattern_clusters.map((cluster, idx) => (
                        <span key={idx} className="pattern-tag">{cluster}</span>
                      ))}
                    </div>
                  )}
                </div>
                
                <div className="item-scores">
                  <div className="score-main">
                    <span className="score-value">
                      {Math.round(item.priority_score)}
                    </span>
                    <span className="score-label">Priority</span>
                  </div>
                  
                  <div className="score-breakdown">
                    <div className="score-detail" title="Future incidents blocked">
                      <span className="detail-value">{item.forward_score}</span>
                      <span className="detail-label">Fwd</span>
                    </div>
                    <div className="score-detail" title="Past incidents mitigated">
                      <span className="detail-value">{item.backward_score}</span>
                      <span className="detail-label">Bwd</span>
                    </div>
                    <div className="score-detail" title="Blocking multiplier">
                      <span className="detail-value">×{item.blocking_multiplier.toFixed(1)}</span>
                      <span className="detail-label">Blk</span>
                    </div>
                  </div>
                  
                  {item.estimated_reduction_percent && (
                    <div className="reduction-badge">
                      -{item.estimated_reduction_percent}% incidents
                    </div>
                  )}
                  
                  {item.implementation_complexity && (
                    <div className={`complexity-badge ${item.implementation_complexity}`}>
                      {item.implementation_complexity}
                    </div>
                  )}
                  
                  <button 
                    className="view-in-graph-btn"
                    onClick={() => onViewInGraph?.(item.id)}
                    disabled={!onViewInGraph}
                    title="View in Graph"
                  >
                    🔍
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

export default PriorityRanking
