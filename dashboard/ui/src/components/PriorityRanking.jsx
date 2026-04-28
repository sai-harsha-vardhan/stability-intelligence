import React, { useEffect, useState, useMemo } from 'react'
import { TypeBadge } from './ui/TypeBadge'
import { StatusPill } from './ui/StatusPill'
import { PriorityScore } from './ui/PriorityScore'
import { RankChange } from './ui/RankChange'
import { Skeleton, SkeletonCard } from './ui/Skeleton'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

const COLUMNS = [
  { key: 'rank', label: 'Rank', sortable: false, width: '60px' },
  { key: 'change', label: 'Δ', sortable: false, width: '50px' },
  { key: 'type', label: 'Type', sortable: true, width: '80px' },
  { key: 'item', label: 'Item', sortable: true, width: 'flex' },
  { key: 'cluster', label: 'Cluster', sortable: true, width: '120px' },
  { key: 'score', label: 'Score', sortable: true, width: '80px' },
  { key: 'forward', label: 'Fwd', sortable: true, width: '50px' },
  { key: 'backward', label: 'Bwd', sortable: true, width: '50px' },
  { key: 'multiplier', label: '×', sortable: false, width: '50px' },
  { key: 'complexity', label: 'Cmplx', sortable: true, width: '60px' },
  { key: 'status', label: 'Status', sortable: true, width: '90px' },
]

const PriorityRanking = ({ limit = 50 }) => {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sortBy, setSortBy] = useState('priority_score')
  const [sortDirection, setSortDirection] = useState('desc')
  const [filterType, setFilterType] = useState('all')
  const [filterComplexity, setFilterComplexity] = useState('all')
  const [selectedItem, setSelectedItem] = useState(null)
  const [panelOpen, setPanelOpen] = useState(false)

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

  const handleSort = (columnKey) => {
    const column = COLUMNS.find(c => c.key === columnKey)
    if (!column?.sortable) return

    if (sortBy === columnKey) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(columnKey)
      setSortDirection('desc')
    }
  }

  const getSortValue = (item, key) => {
    switch (key) {
      case 'type': return item.type
      case 'item': return item.title?.toLowerCase()
      case 'cluster': return item.pattern_clusters?.[0]?.toLowerCase() || ''
      case 'score': return item.priority_score
      case 'forward': return item.forward_score
      case 'backward': return item.backward_score
      case 'complexity': return item.implementation_complexity
      case 'status': return item.status
      default: return item[key]
    }
  }

  const filteredAndSortedItems = useMemo(() => {
    let result = [...items]

    // Apply filters
    if (filterType !== 'all') {
      result = result.filter(item => item.type === filterType)
    }
    if (filterComplexity !== 'all') {
      result = result.filter(item => item.implementation_complexity === filterComplexity)
    }

    // Apply sorting
    result.sort((a, b) => {
      const aVal = getSortValue(a, sortBy)
      const bVal = getSortValue(b, sortBy)
      
      if (typeof aVal === 'string') {
        return sortDirection === 'asc' 
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal)
      }
      
      return sortDirection === 'asc' ? aVal - bVal : bVal - aVal
    })

    return result
  }, [items, filterType, filterComplexity, sortBy, sortDirection])

  const handleRowClick = (item) => {
    setSelectedItem(item)
    setPanelOpen(true)
  }

  const closePanel = () => {
    setPanelOpen(false)
    setSelectedItem(null)
  }

  const getScoreColor = (score) => {
    if (score >= 8) return '#22C55E'
    if (score >= 5) return '#EAB308'
    return '#484F58'
  }

  const getComplexityDisplay = (complexity) => {
    const map = { low: 'L', medium: 'M', high: 'H' }
    return map[complexity] || complexity?.[0]?.toUpperCase() || '?'
  }

  const getComplexityColor = (complexity) => {
    if (complexity === 'low') return '#22C55E'
    if (complexity === 'high') return '#F97316'
    return '#EAB308'
  }

  if (loading) {
    return (
      <div className="section-card priority-ranking">
        <div className="card-header">
          <h3>Priority Ranking</h3>
        </div>
        <div className="p-4">
          <SkeletonCard lines={5} />
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
        <div className="card-content error p-4">
          <p>Error: {error}</p>
          <button onClick={fetchPriorities} className="btn-primary mt-2">Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className={`section-card priority-ranking ${panelOpen ? 'with-panel' : ''}`}>
      <div className="card-header">
        <h3>Priorities</h3>
        <span className="item-count">{filteredAndSortedItems.length} items</span>
      </div>
      
      <div className="card-controls">
        <div className="filter-group">
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
            value={filterComplexity} 
            onChange={(e) => setFilterComplexity(e.target.value)}
            className="control-select"
          >
            <option value="all">All Complexity</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>
        
        <button onClick={fetchPriorities} className="btn-refresh" title="Refresh">
          🔄
        </button>
      </div>
      
      <div className="card-content">
        <div className="priority-table-wrapper">
          <table className="priority-table">
            <thead>
              <tr>
                {COLUMNS.map(col => (
                  <th 
                    key={col.key}
                    style={{ width: col.width }}
                    className={col.sortable ? 'sortable' : ''}
                    onClick={() => handleSort(col.key)}
                  >
                    <span>{col.label}</span>
                    {col.sortable && sortBy === col.key && (
                      <span className="sort-arrow">{sortDirection === 'asc' ? '↑' : '↓'}</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredAndSortedItems.length === 0 ? (
                <tr>
                  <td colSpan={COLUMNS.length} className="empty-cell">
                    <p>No priority items found</p>
                  </td>
                </tr>
              ) : (
                filteredAndSortedItems.map((item, index) => (
                  <tr 
                    key={item.id} 
                    className={`priority-row ${selectedItem?.id === item.id ? 'selected' : ''}`}
                    onClick={() => handleRowClick(item)}
                  >
                    <td className="cell-rank">
                      <span className="rank-number">#{index + 1}</span>
                    </td>
                    <td className="cell-change">
                      <RankChange 
                        change={item.rank_change} 
                        isNew={item.is_new}
                        size="sm"
                      />
                    </td>
                    <td className="cell-type">
                      <TypeBadge 
                        type={item.type === 'action_item' ? 'action' : 'strategy'}
                        size="sm"
                      />
                    </td>
                    <td className="cell-item">
                      <span className="item-title truncate" title={item.title}>
                        {item.title}
                      </span>
                    </td>
                    <td className="cell-cluster">
                      {item.pattern_clusters?.[0] && (
                        <span className="cluster-tag-sm">{item.pattern_clusters[0]}</span>
                      )}
                    </td>
                    <td className="cell-score">
                      <span 
                        className="score-value"
                        style={{ color: getScoreColor(item.priority_score) }}
                      >
                        {item.priority_score?.toFixed(1)}
                      </span>
                    </td>
                    <td className="cell-forward">
                      <span className="detail-value">{item.forward_score}</span>
                    </td>
                    <td className="cell-backward">
                      <span className="detail-value">{item.backward_score}</span>
                    </td>
                    <td className="cell-multiplier">
                      <span className="multiplier-value">×{item.blocking_multiplier?.toFixed(1)}</span>
                    </td>
                    <td className="cell-complexity">
                      <span 
                        className="complexity-letter"
                        style={{ color: getComplexityColor(item.implementation_complexity) }}
                      >
                        {getComplexityDisplay(item.implementation_complexity)}
                      </span>
                    </td>
                    <td className="cell-status">
                      <StatusPill status={item.status} size="sm" />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detail Side Panel */}
      {panelOpen && selectedItem && (
        <div className="detail-panel-overlay" onClick={closePanel}>
          <div className="detail-panel" onClick={e => e.stopPropagation()}>
            <div className="panel-header">
              <div className="panel-actions">
                <a 
                  href={selectedItem.github_url} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="github-link"
                >
                  GitHub ↗
                </a>
                <button className="close-btn" onClick={closePanel}>×</button>
              </div>
            </div>

            <div className="panel-content">
              <h4 className="panel-title">{selectedItem.title}</h4>
              
              {selectedItem.description && (
                <p className="panel-description">{selectedItem.description}</p>
              )}

              <div className="panel-section">
                <h5>Scoring Breakdown</h5>
                
                <div className="score-row">
                  <span className="score-label">Priority Score</span>
                  <span className="score-value-large">{selectedItem.priority_score?.toFixed(1)}</span>
                  <div className="score-bar-container">
                    <div 
                      className="score-bar" 
                      style={{ width: `${(selectedItem.priority_score / 10) * 100}%` }}
                    />
                  </div>
                </div>

                <div className="score-row">
                  <span className="score-label">Forward Score</span>
                  <span className="score-value">{selectedItem.forward_score}</span>
                  <span className="score-detail">{selectedItem.forward_score} incident classes blocked</span>
                </div>

                <div className="score-row">
                  <span className="score-label">Backward Score</span>
                  <span className="score-value">{selectedItem.backward_score}</span>
                  <span className="score-detail">{selectedItem.backward_score} past incidents prevented</span>
                </div>

                <div className="score-row">
                  <span className="score-label">Blocking Mult.</span>
                  <span className="score-value">×{selectedItem.blocking_multiplier?.toFixed(1)}</span>
                  {selectedItem.blocking_connectors?.length > 0 && (
                    <span className="score-detail">
                      per {selectedItem.blocking_connectors.join(', ')}
                    </span>
                  )}
                </div>

                <div className="score-row">
                  <span className="score-label">Complexity</span>
                  <span className="score-value" style={{ color: getComplexityColor(selectedItem.implementation_complexity) }}>
                    {selectedItem.implementation_complexity}
                  </span>
                </div>

                {selectedItem.stagger_safe !== undefined && (
                  <div className="score-row">
                    <span className="score-label">Stagger Safe</span>
                    <span className="score-value">{selectedItem.stagger_safe ? 'Yes' : 'No'}</span>
                  </div>
                )}
              </div>

              {selectedItem.pattern_clusters?.length > 0 && (
                <div className="panel-section">
                  <h5>Pattern Clusters</h5>
                  <div className="cluster-tags">
                    {selectedItem.pattern_clusters.map((cluster, idx) => (
                      <span key={idx} className="cluster-tag">{cluster}</span>
                    ))}
                  </div>
                </div>
              )}

              {selectedItem.affected_components?.length > 0 && (
                <div className="panel-section">
                  <h5>Components Affected</h5>
                  <div className="component-tags">
                    {selectedItem.affected_components.map((comp, idx) => (
                      <span key={idx} className="component-tag">{comp}</span>
                    ))}
                  </div>
                </div>
              )}

              {selectedItem.connected_items?.length > 0 && (
                <div className="panel-section">
                  <h5>Connected Items</h5>
                  <ul className="connected-list">
                    {selectedItem.connected_items.map((conn, idx) => (
                      <li key={idx}>{conn}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="panel-section">
                <h5>Human Feedback</h5>
                <div className="feedback-actions">
                  <button className="feedback-btn accept">✓ Accept</button>
                  <button className="feedback-btn adjust">↑↓ Adjust</button>
                  <button className="feedback-btn reject">✗ Reject</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default PriorityRanking
