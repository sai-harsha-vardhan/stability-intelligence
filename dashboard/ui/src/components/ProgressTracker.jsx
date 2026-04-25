import React, { useEffect, useState } from 'react'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const ProgressTracker = ({ limit = 100 }) => {
  const [items, setItems] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [statusFilter, setStatusFilter] = useState('all')

  useEffect(() => {
    fetchProgress()
  }, [limit])

  const fetchProgress = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${API_BASE_URL}/progress?status_filter=all&limit=${limit}`)
      if (!response.ok) throw new Error('Failed to fetch progress')
      const data = await response.json()
      setItems(data.items || [])
      setStats(data.stats || null)
      setLoading(false)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const getStatusClass = (status) => {
    const classes = {
      'open': 'status-open',
      'in_progress': 'status-progress',
      'resolved': 'status-resolved',
      'closed': 'status-closed',
      'deferred': 'status-deferred'
    }
    return classes[status] || 'status-default'
  }

  const getStatusIcon = (status) => {
    if (status === 'resolved') return '✅'
    if (status === 'in_progress') return '🔄'
    if (status === 'deferred') return '⏸️'
    return '⭕'
  }

  const getComplexityClass = (complexity) => {
    if (complexity === 'low') return 'complexity-low'
    if (complexity === 'high') return 'complexity-high'
    return 'complexity-medium'
  }

  const getEffectivenessBadge = (effective) => {
    if (effective === true) return { icon: '✓', class: 'effective-yes', label: 'Effective' }
    if (effective === false) return { icon: '✗', class: 'effective-no', label: 'Ineffective' }
    return { icon: '?', class: 'effective-unknown', label: 'Pending' }
  }

  const filteredItems = statusFilter === 'all' 
    ? items 
    : items.filter(item => {
        if (statusFilter === 'done') return ['resolved', 'closed'].includes(item.status)
        return item.status === statusFilter
      })

  if (loading) {
    return (
      <div className="section-card progress-tracker">
        <div className="card-header">
          <h3>Progress Tracker</h3>
        </div>
        <div className="card-content loading">
          <div className="loading-spinner small"></div>
          <p>Loading progress...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="section-card progress-tracker">
        <div className="card-header">
          <h3>Progress Tracker</h3>
        </div>
        <div className="card-content error">
          <p>Error: {error}</p>
          <button onClick={fetchProgress}>Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className="section-card progress-tracker">
      <div className="card-header">
        <h3>Progress Tracker</h3>
        <span className="item-count">{filteredItems.length} items</span>
      </div>
      
      {stats && (
        <div className="stats-bar">
          <div className="stat-item">
            <span className="stat-number">{stats.total}</span>
            <span className="stat-label">Total</span>
          </div>
          <div className="stat-item">
            <span className="stat-number highlight">{stats.open}</span>
            <span className="stat-label">Open</span>
          </div>
          <div className="stat-item">
            <span className="stat-number">{stats.in_progress}</span>
            <span className="stat-label">In Progress</span>
          </div>
          <div className="stat-item">
            <span className="stat-number success">{stats.resolved}</span>
            <span className="stat-label">Resolved</span>
          </div>
          {(stats.effective_count > 0 || stats.ineffective_count > 0) && (
            <>
              <div className="stat-divider"></div>
              <div className="stat-item">
                <span className="stat-number success">{stats.effective_count}</span>
                <span className="stat-label">Effective</span>
              </div>
              <div className="stat-item">
                <span className="stat-number warning">{stats.ineffective_count}</span>
                <span className="stat-label">Ineffective</span>
              </div>
            </>
          )}
        </div>
      )}
      
      <div className="card-controls">
        <div className="filter-group">
          <button 
            className={`filter-btn ${statusFilter === 'all' ? 'active' : ''}`}
            onClick={() => setStatusFilter('all')}
          >
            All
          </button>
          <button 
            className={`filter-btn ${statusFilter === 'open' ? 'active' : ''}`}
            onClick={() => setStatusFilter('open')}
          >
            Open
          </button>
          <button 
            className={`filter-btn ${statusFilter === 'in_progress' ? 'active' : ''}`}
            onClick={() => setStatusFilter('in_progress')}
          >
            In Progress
          </button>
          <button 
            className={`filter-btn ${statusFilter === 'done' ? 'active' : ''}`}
            onClick={() => setStatusFilter('done')}
          >
            Done
          </button>
        </div>
        <button onClick={fetchProgress} className="btn-refresh" title="Refresh">
          🔄
        </button>
      </div>
      
      <div className="card-content">
        <div className="progress-list">
          {filteredItems.length === 0 ? (
            <p className="empty-state">No action items found</p>
          ) : (
            filteredItems.map((item) => {
              const effectiveness = getEffectivenessBadge(item.effective)
              return (
                <div key={item.id} className="progress-item">
                  <div className="item-main">
                    <div className={`status-icon ${getStatusClass(item.status)}`}>
                      {getStatusIcon(item.status)}
                    </div>
                    <div className="item-info">
                      <h4 className="item-title">{item.title}</h4>
                      {item.pattern_cluster_name && (
                        <span className="cluster-tag">{item.pattern_cluster_name}</span>
                      )}
                    </div>
                  </div>
                  
                  <div className="item-meta">
                    <div className={`complexity-badge ${getComplexityClass(item.implementation_complexity)}`}>
                      {item.implementation_complexity}
                    </div>
                    
                    <div className="priority-score">
                      <span className="score-value">{Math.round(item.priority_score)}</span>
                      <span className="score-label">priority</span>
                    </div>
                    
                    {item.assignee && (
                      <div className="assignee-badge">
                        👤 {item.assignee}
                      </div>
                    )}
                    
                    {(item.status === 'resolved' || item.status === 'closed') && (
                      <div className={`effectiveness-badge ${effectiveness.class}`}>
                        {effectiveness.icon} {effectiveness.label}
                      </div>
                    )}
                    
                    {item.created_at && (
                      <div className="date-info">
                        <span className="date-label">Created:</span>
                        <span className="date-value">
                          {new Date(item.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    )}
                    
                    {item.resolved_at && (
                      <div className="date-info resolved">
                        <span className="date-label">Resolved:</span>
                        <span className="date-value">
                          {new Date(item.resolved_at).toLocaleDateString()}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}

export default ProgressTracker
