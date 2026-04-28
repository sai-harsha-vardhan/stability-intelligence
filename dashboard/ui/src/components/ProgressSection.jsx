import React, { useEffect, useState, useMemo, useCallback } from 'react'
import { StatusPill } from './ui/StatusPill'
import { TypeBadge } from './ui/TypeBadge'
import { SkeletonCard } from './ui/Skeleton'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

const ProgressSection = () => {
  const [items, setItems] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [typeFilter, setTypeFilter] = useState('all')
  const [effectivenessFilter, setEffectivenessFilter] = useState('all')
  const [selectedItem, setSelectedItem] = useState(null)

  useEffect(() => {
    fetchProgress()
  }, [])

  const fetchProgress = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${API_BASE_URL}/progress?status_filter=all&limit=100`)
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

  const filteredItems = useMemo(() => {
    return items.filter(item => {
      // Status filter
      if (statusFilter === 'open') {
        if (item.status !== 'open') return false
      } else if (statusFilter === 'in_progress') {
        if (item.status !== 'in_progress') return false
      } else if (statusFilter === 'done') {
        if (!['resolved', 'closed'].includes(item.status)) return false
      }

      // Type filter
      if (typeFilter !== 'all' && item.type !== typeFilter) return false

      // Effectiveness filter
      if (effectivenessFilter === 'effective' && item.effective !== true) return false
      if (effectivenessFilter === 'ineffective' && item.effective !== false) return false
      if (effectivenessFilter === 'monitoring' && item.effectiveness_status !== 'monitoring') return false

      return true
    })
  }, [items, statusFilter, typeFilter, effectivenessFilter])

  const groupedItems = useMemo(() => {
    const groups = {
      open: [],
      in_progress: [],
      resolved: [],
      deferred: []
    }

    filteredItems.forEach(item => {
      if (groups[item.status]) {
        groups[item.status].push(item)
      } else if (['resolved', 'closed'].includes(item.status)) {
        groups.resolved.push(item)
      } else {
        groups.open.push(item)
      }
    })

    return groups
  }, [filteredItems])

  const getEffectivenessBadge = (item) => {
    if (item.effective === true) {
      return { icon: '✓', class: 'effective-yes', label: 'Verified Effective' }
    }
    if (item.effective === false) {
      return { icon: '✗', class: 'effective-no', label: 'Ineffective' }
    }
    if (item.effectiveness_status === 'monitoring') {
      const daysRemaining = item.monitoring_days_remaining || 30
      return { icon: '⏳', class: 'effective-monitoring', label: `${daysRemaining} days` }
    }
    return null
  }

  const getComplexityColor = (complexity) => {
    if (complexity === 'low') return '#22C55E'
    if (complexity === 'high') return '#F97316'
    return '#EAB308'
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Unknown'
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }

  const getDuration = (created, resolved) => {
    if (!created || !resolved) return null
    const start = new Date(created)
    const end = new Date(resolved)
    const days = Math.floor((end - start) / (1000 * 60 * 60 * 24))
    return `${days} days`
  }

  if (loading) {
    return (
      <div className="section-full progress-section">
        <div className="section-header">
          <h2>Progress</h2>
          <span className="section-subtitle">Track resolution effectiveness</span>
        </div>
        <div className="progress-three-panel">
          <div className="filters-sidebar">
            <SkeletonCard lines={4} />
          </div>
          <div className="items-list">
            <SkeletonCard lines={6} />
          </div>
          <div className="detail-panel">
            <SkeletonCard lines={5} />
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="section-full progress-section">
        <div className="section-header">
          <h2>Progress</h2>
        </div>
        <div className="section-content error-state">
          <p>Error loading progress: {error}</p>
          <button onClick={fetchProgress} className="btn-primary">Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className="section-full progress-section">
      <div className="section-header">
        <div className="header-left">
          <h2>Progress Tracker</h2>
          <span className="item-count">{filteredItems.length} items</span>
        </div>
        <button onClick={fetchProgress} className="btn-icon" title="Refresh">
          🔄
        </button>
      </div>

      {/* Effectiveness Summary Bar */}
      {stats && (
        <div className="effectiveness-summary">
          <div className="summary-stats">
            <div className="summary-stat">
              <span className="summary-value">{stats.resolved_this_quarter || 0}</span>
              <span className="summary-label">Resolved</span>
            </div>
            <div className="summary-stat effective">
              <span className="summary-value">{stats.effective_count || 0}</span>
              <span className="summary-label">
                Effective ({stats.resolved_this_quarter ? Math.round((stats.effective_count / stats.resolved_this_quarter) * 100) : 0}%)
              </span>
            </div>
            <div className="summary-stat ineffective">
              <span className="summary-value">{stats.ineffective_count || 0}</span>
              <span className="summary-label">
                Ineffective ({stats.resolved_this_quarter ? Math.round((stats.ineffective_count / stats.resolved_this_quarter) * 100) : 0}%)
              </span>
            </div>
            <div className="summary-stat monitoring">
              <span className="summary-value">{stats.monitoring_count || 0}</span>
              <span className="summary-label">Monitoring</span>
            </div>
          </div>
          <div className="summary-bar">
            <div 
              className="summary-fill effective" 
              style={{ 
                width: `${stats.resolved_this_quarter ? (stats.effective_count / stats.resolved_this_quarter) * 100 : 0}%` 
              }}
            />
            <div 
              className="summary-fill ineffective" 
              style={{ 
                width: `${stats.resolved_this_quarter ? (stats.ineffective_count / stats.resolved_this_quarter) * 100 : 0}%` 
              }}
            />
            <div 
              className="summary-fill monitoring" 
              style={{ 
                width: `${stats.resolved_this_quarter ? (stats.monitoring_count / stats.resolved_this_quarter) * 100 : 0}%` 
              }}
            />
          </div>
        </div>
      )}
      
      <div className="progress-three-panel">
        {/* Left Panel - Filters */}
        <div className="filters-sidebar">
          <div className="filter-section">
            <h4>Status</h4>
            <div className="filter-options">
              <label className={`filter-option ${statusFilter === 'all' ? 'active' : ''}`}>
                <input 
                  type="radio" 
                  name="status" 
                  value="all" 
                  checked={statusFilter === 'all'}
                  onChange={(e) => setStatusFilter(e.target.value)}
                />
                <span>All ({stats?.total || 0})</span>
              </label>
              <label className={`filter-option ${statusFilter === 'open' ? 'active' : ''}`}>
                <input 
                  type="radio" 
                  name="status" 
                  value="open" 
                  checked={statusFilter === 'open'}
                  onChange={(e) => setStatusFilter(e.target.value)}
                />
                <span>Open ({stats?.open || 0})</span>
              </label>
              <label className={`filter-option ${statusFilter === 'in_progress' ? 'active' : ''}`}>
                <input 
                  type="radio" 
                  name="status" 
                  value="in_progress" 
                  checked={statusFilter === 'in_progress'}
                  onChange={(e) => setStatusFilter(e.target.value)}
                />
                <span>In Progress ({stats?.in_progress || 0})</span>
              </label>
              <label className={`filter-option ${statusFilter === 'done' ? 'active' : ''}`}>
                <input 
                  type="radio" 
                  name="status" 
                  value="done" 
                  checked={statusFilter === 'done'}
                  onChange={(e) => setStatusFilter(e.target.value)}
                />
                <span>Done ({(stats?.resolved || 0) + (stats?.closed || 0)})</span>
              </label>
            </div>
          </div>

          <div className="filter-section">
            <h4>Type</h4>
            <div className="filter-options">
              <label className={`filter-option ${typeFilter === 'all' ? 'active' : ''}`}>
                <input 
                  type="radio" 
                  name="type" 
                  value="all" 
                  checked={typeFilter === 'all'}
                  onChange={(e) => setTypeFilter(e.target.value)}
                />
                <span>All</span>
              </label>
              <label className={`filter-option ${typeFilter === 'action_item' ? 'active' : ''}`}>
                <input 
                  type="radio" 
                  name="type" 
                  value="action_item" 
                  checked={typeFilter === 'action_item'}
                  onChange={(e) => setTypeFilter(e.target.value)}
                />
                <span>Action Items</span>
              </label>
              <label className={`filter-option ${typeFilter === 'strategy' ? 'active' : ''}`}>
                <input 
                  type="radio" 
                  name="type" 
                  value="strategy" 
                  checked={typeFilter === 'strategy'}
                  onChange={(e) => setTypeFilter(e.target.value)}
                />
                <span>Strategies</span>
              </label>
            </div>
          </div>

          <div className="filter-section">
            <h4>Effectiveness</h4>
            <div className="filter-options">
              <label className={`filter-option ${effectivenessFilter === 'all' ? 'active' : ''}`}>
                <input 
                  type="radio" 
                  name="effectiveness" 
                  value="all" 
                  checked={effectivenessFilter === 'all'}
                  onChange={(e) => setEffectivenessFilter(e.target.value)}
                />
                <span>All</span>
              </label>
              <label className={`filter-option ${effectivenessFilter === 'effective' ? 'active' : ''}`}>
                <input 
                  type="radio" 
                  name="effectiveness" 
                  value="effective" 
                  checked={effectivenessFilter === 'effective'}
                  onChange={(e) => setEffectivenessFilter(e.target.value)}
                />
                <span>Verified Effective</span>
              </label>
              <label className={`filter-option ${effectivenessFilter === 'ineffective' ? 'active' : ''}`}>
                <input 
                  type="radio" 
                  name="effectiveness" 
                  value="ineffective" 
                  checked={effectivenessFilter === 'ineffective'}
                  onChange={(e) => setEffectivenessFilter(e.target.value)}
                />
                <span>Ineffective</span>
              </label>
              <label className={`filter-option ${effectivenessFilter === 'monitoring' ? 'active' : ''}`}>
                <input 
                  type="radio" 
                  name="effectiveness" 
                  value="monitoring" 
                  checked={effectivenessFilter === 'monitoring'}
                  onChange={(e) => setEffectivenessFilter(e.target.value)}
                />
                <span>Monitoring</span>
              </label>
            </div>
          </div>

          <button onClick={fetchProgress} className="btn-refresh-full" title="Refresh">
            🔄 Refresh
          </button>
        </div>

        {/* Center Panel - Items List */}
        <div className="items-list">
          {filteredItems.length === 0 ? (
            <div className="empty-state">
              <p>No items match the selected filters</p>
            </div>
          ) : (
            <>
              {groupedItems.open.length > 0 && (
                <div className="item-group">
                  <h5 className="group-header">Open ({groupedItems.open.length})</h5>
                  {groupedItems.open.map(renderItemCard)}
                </div>
              )}
              {groupedItems.in_progress.length > 0 && (
                <div className="item-group">
                  <h5 className="group-header">In Progress ({groupedItems.in_progress.length})</h5>
                  {groupedItems.in_progress.map(renderItemCard)}
                </div>
              )}
              {groupedItems.resolved.length > 0 && (
                <div className="item-group">
                  <h5 className="group-header">Resolved ({groupedItems.resolved.length})</h5>
                  {groupedItems.resolved.map(renderItemCard)}
                </div>
              )}
            </>
          )}
        </div>

        {/* Right Panel - Detail */}
        <div className="detail-sidebar">
          {selectedItem ? (
            <div className="item-detail">
              <div className="detail-header">
                <TypeBadge type={selectedItem.type === 'action_item' ? 'action' : 'strategy'} />
                <StatusPill status={selectedItem.status} />
              </div>
              
              <h4 className="detail-title">{selectedItem.title}</h4>
              
              {selectedItem.description && (
                <p className="detail-description">{selectedItem.description}</p>
              )}

              <div className="detail-meta">
                {selectedItem.pattern_cluster_name && (
                  <div className="meta-row">
                    <span className="meta-label">Cluster:</span>
                    <span className="cluster-tag-sm">{selectedItem.pattern_cluster_name}</span>
                  </div>
                )}
                <div className="meta-row">
                  <span className="meta-label">Priority:</span>
                  <span className="meta-value">{selectedItem.priority_score?.toFixed(1)}</span>
                </div>
                {selectedItem.assignee && (
                  <div className="meta-row">
                    <span className="meta-label">Assignee:</span>
                    <span className="meta-value">@{selectedItem.assignee}</span>
                  </div>
                )}
                {selectedItem.created_at && (
                  <div className="meta-row">
                    <span className="meta-label">Created:</span>
                    <span className="meta-value">{formatDate(selectedItem.created_at)}</span>
                  </div>
                )}
                {selectedItem.resolved_at && (
                  <div className="meta-row">
                    <span className="meta-label">Resolved:</span>
                    <span className="meta-value">{formatDate(selectedItem.resolved_at)}</span>
                  </div>
                )}
                {selectedItem.created_at && selectedItem.resolved_at && (
                  <div className="meta-row">
                    <span className="meta-label">Duration:</span>
                    <span className="meta-value">{getDuration(selectedItem.created_at, selectedItem.resolved_at)}</span>
                  </div>
                )}
              </div>

              {(selectedItem.status === 'resolved' || selectedItem.status === 'closed') && (
                <div className="detail-effectiveness">
                  <h5>Effectiveness</h5>
                  {(() => {
                    const badge = getEffectivenessBadge(selectedItem)
                    if (!badge) return <p className="empty-sub">Not yet evaluated</p>
                    return (
                      <div className={`effectiveness-display ${badge.class}`}>
                        <span className="effectiveness-icon">{badge.icon}</span>
                        <span className="effectiveness-label">{badge.label}</span>
                      </div>
                    )
                  })()}
                </div>
              )}
            </div>
          ) : (
            <div className="empty-detail">
              <p>Select an item to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )

  function renderItemCard(item) {
    const effectiveness = getEffectivenessBadge(item)
    return (
      <div 
        key={item.id} 
        className={`progress-card ${selectedItem?.id === item.id ? 'selected' : ''}`}
        onClick={() => setSelectedItem(item)}
      >
        <div className="card-main">
          <TypeBadge type={item.type === 'action_item' ? 'action' : 'strategy'} size="sm" />
          <span className="card-title" title={item.title}>{item.title}</span>
          <StatusPill status={item.status} size="sm" />
        </div>
        <div className="card-meta">
          {item.pattern_cluster_name && (
            <span className="meta-cluster">{item.pattern_cluster_name}</span>
          )}
          <span 
            className="meta-priority"
            style={{ color: getComplexityColor(item.implementation_complexity) }}
          >
            {item.priority_score?.toFixed(1)}
          </span>
          {item.assignee && (
            <span className="meta-assignee">@{item.assignee}</span>
          )}
        </div>
        <div className="card-footer">
          <span className="footer-date">
            Created {formatDate(item.created_at)}
            {item.resolved_at && ` • Resolved ${formatDate(item.resolved_at)}`}
          </span>
          {effectiveness && (
            <span className={`footer-effectiveness ${effectiveness.class}`}>
              {effectiveness.icon} {effectiveness.label}
            </span>
          )}
        </div>
      </div>
    )
  }
}

export default ProgressSection
