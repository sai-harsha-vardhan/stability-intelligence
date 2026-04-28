import React, { useEffect, useState, useMemo } from 'react'
import { TrendIndicator } from './ui/TrendIndicator'
import { TypeBadge } from './ui/TypeBadge'
import { StatusPill } from './ui/StatusPill'
import { PriorityScore } from './ui/PriorityScore'
import { NodeTag } from './ui/NodeTag'
import { SkeletonCard } from './ui/Skeleton'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

// Sparkline component for incident timeline
const Sparkline = ({ data, height = 40, color = '#8B5CF6' }) => {
  if (!data || data.length === 0) return <div style={{ height }} className="sparkline-empty">No data</div>
  
  const max = Math.max(...data, 1)
  const min = Math.min(...data, 0)
  const range = max - min || 1
  const width = 200
  const padding = 2
  
  const points = data.map((val, i) => {
    const x = (i / (data.length - 1 || 1)) * (width - padding * 2) + padding
    const y = height - ((val - min) / range) * (height - padding * 2) - padding
    return `${x},${y}`
  }).join(' ')
  
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} className="sparkline">
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="2"
        points={points}
      />
      {data.map((val, i) => {
        const x = (i / (data.length - 1 || 1)) * (width - padding * 2) + padding
        const y = height - ((val - min) / range) * (height - padding * 2) - padding
        return (
          <circle
            key={i}
            cx={x}
            cy={y}
            r="3"
            fill={color}
            className="sparkline-dot"
          />
        )
      })}
    </svg>
  )
}

const PatternBoard = ({ limit = 20 }) => {
  const [clusters, setClusters] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedCluster, setSelectedCluster] = useState(null)

  useEffect(() => {
    fetchPatterns()
  }, [])

  const fetchPatterns = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${API_BASE_URL}/patterns`)
      if (!response.ok) throw new Error('Failed to fetch patterns')
      const data = await response.json()
      setClusters(data.clusters || [])
      if (data.clusters?.length > 0 && !selectedCluster) {
        setSelectedCluster(data.clusters[0])
      }
      setLoading(false)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const maxFrequency = useMemo(() => {
    return Math.max(...clusters.map(c => c.frequency || c.incident_count || 0), 1)
  }, [clusters])

  const getFrequencyBarWidth = (frequency) => {
    return `${(frequency / maxFrequency) * 100}%`
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Unknown'
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  }

  const getDaysAgo = (dateStr) => {
    if (!dateStr) return null
    const date = new Date(dateStr)
    const now = new Date()
    const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24))
    if (diffDays === 0) return 'Today'
    if (diffDays === 1) return 'Yesterday'
    return `${diffDays} days ago`
  }

  // Mock sparkline data generator (will be replaced with real data)
  const getSparklineData = (cluster) => {
    // Generate random-looking data based on cluster properties
    const baseCount = cluster.incident_count || cluster.frequency || 5
    const weeks = 26 // 6 months
    return Array.from({ length: weeks }, (_, i) => {
      const trend = cluster.trend === 'worsening' ? 1.1 : cluster.trend === 'improving' ? 0.9 : 1
      const random = 0.5 + Math.random()
      return Math.max(0, Math.round(baseCount * random * Math.pow(trend, i / 10)))
    })
  }

  if (loading) {
    return (
      <div className="section-card pattern-board">
        <div className="card-header">
          <h3>Patterns</h3>
        </div>
        <div className="pattern-board-layout">
          <div className="cluster-list-loading">
            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonCard key={i} lines={2} />
            ))}
          </div>
          <div className="cluster-detail-loading">
            <SkeletonCard lines={6} />
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="section-card pattern-board">
        <div className="card-header">
          <h3>Patterns</h3>
        </div>
        <div className="card-content error p-4">
          <p>Error: {error}</p>
          <button onClick={fetchPatterns} className="btn-primary mt-2">Retry</button>
        </div>
      </div>
    )
  }

  return (
    <div className="section-card pattern-board">
      <div className="card-header">
        <h3>Pattern Clusters</h3>
        <span className="item-count">{clusters.length} clusters</span>
      </div>
      
      <div className="pattern-board-layout">
        {/* Left Column - Cluster List */}
        <div className="cluster-list">
          {clusters.length === 0 ? (
            <p className="empty-state">No pattern clusters found</p>
          ) : (
            clusters.map((cluster) => (
              <div 
                key={cluster.id}
                className={`cluster-card ${selectedCluster?.id === cluster.id ? 'selected' : ''}`}
                onClick={() => setSelectedCluster(cluster)}
              >
                <div className="cluster-card-header">
                  <h4 className="cluster-name">{cluster.name}</h4>
                  <TrendIndicator trend={cluster.trend} showLabel={false} />
                </div>
                
                <div className="cluster-frequency">
                  <div className="frequency-bar-bg">
                    <div 
                      className="frequency-bar-fill"
                      style={{ width: getFrequencyBarWidth(cluster.frequency || cluster.incident_count || 0) }}
                    />
                  </div>
                  <span className="frequency-label">
                    {cluster.frequency || cluster.incident_count || 0} incidents
                  </span>
                </div>
                
                <div className="cluster-meta">
                  <span className="meta-item">
                    Last: {getDaysAgo(cluster.last_incident_date) || 'Unknown'}
                  </span>
                  <span className="meta-item">
                    Open: {cluster.open_action_items || 0}
                  </span>
                  {cluster.strategies > 0 && (
                    <span className="meta-item">
                      Strategies: {cluster.strategies}
                    </span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Right Column - Cluster Detail */}
        <div className="cluster-detail">
          {selectedCluster ? (
            <>
              <div className="detail-header">
                <h4 className="detail-title">{selectedCluster.name}</h4>
                <TrendIndicator trend={selectedCluster.trend} />
              </div>

              <div className="detail-stats">
                <div className="stat-item">
                  <span className="stat-label">Frequency</span>
                  <span className="stat-value">{selectedCluster.frequency || selectedCluster.incident_count || 0} incidents</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">First Seen</span>
                  <span className="stat-value">{formatDate(selectedCluster.first_incident_date)}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Last</span>
                  <span className="stat-value">{formatDate(selectedCluster.last_incident_date)}</span>
                </div>
                {selectedCluster.confidence && (
                  <div className="stat-item">
                    <span className="stat-label">Confidence</span>
                    <span className="stat-value">{(selectedCluster.confidence * 100).toFixed(0)}%</span>
                  </div>
                )}
              </div>

              {selectedCluster.description && (
                <div className="detail-section">
                  <h5>Description</h5>
                  <p className="detail-description">{selectedCluster.description}</p>
                </div>
              )}

              <div className="detail-section">
                <h5>Incident Timeline (Last 6 Months)</h5>
                <Sparkline data={getSparklineData(selectedCluster)} />
              </div>

              {selectedCluster.root_causes && selectedCluster.root_causes.length > 0 && (
                <div className="detail-section">
                  <h5>Contributing Root Causes</h5>
                  <ul className="root-causes-list">
                    {selectedCluster.root_causes.map((rc, idx) => (
                      <li key={idx} className="root-cause-item">
                        <span className="root-cause-name">{rc.name}</span>
                        {rc.confidence && (
                          <span className="root-cause-confidence">
                            {(rc.confidence * 100).toFixed(0)}%
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {selectedCluster.open_action_items > 0 && (
                <div className="detail-section">
                  <h5>Open Action Items ({selectedCluster.open_action_items})</h5>
                  <div className="action-items-list">
                    {selectedCluster.related_action_items?.slice(0, 5).map((item, idx) => (
                      <div key={idx} className="action-item-mini">
                        <TypeBadge type="action" size="sm" />
                        <span className="item-title-sm">{item.title}</span>
                        <span className="item-score">{item.priority_score?.toFixed(1)}</span>
                      </div>
                    )) || <p className="empty-sub">No action items linked</p>}
                  </div>
                </div>
              )}

              {selectedCluster.strategies > 0 && (
                <div className="detail-section">
                  <h5>Generated Strategies ({selectedCluster.strategies})</h5>
                  <div className="strategies-list">
                    {selectedCluster.related_strategies?.slice(0, 3).map((strategy, idx) => (
                      <div key={idx} className="strategy-card-mini">
                        <TypeBadge type="strategy" size="sm" />
                        <span className="strategy-title">{strategy.title}</span>
                        {strategy.estimated_reduction_percent && (
                          <span className="strategy-impact">
                            -{strategy.estimated_reduction_percent}% incidents
                          </span>
                        )}
                      </div>
                    )) || <p className="empty-sub">No strategies linked</p>}
                  </div>
                </div>
              )}

              {selectedCluster.affected_components && selectedCluster.affected_components.length > 0 && (
                <div className="detail-section">
                  <h5>Code Hotspots</h5>
                  <div className="hotspots-list">
                    {selectedCluster.affected_components.slice(0, 5).map((comp, idx) => (
                      <div key={idx} className="hotspot-item">
                        <NodeTag label={comp.name || comp} type="component" />
                        <div className="hotspot-bar">
                          <div 
                            className="hotspot-fill" 
                            style={{ width: `${(comp.count / (selectedCluster.incident_count || 1)) * 100}%` }}
                          />
                        </div>
                        <span className="hotspot-count">{comp.count || 1}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="detail-footer">
                <button className="btn-secondary" onClick={() => {}}>
                  View in Graph →
                </button>
              </div>
            </>
          ) : (
            <div className="empty-detail">
              <p>Select a cluster to view details</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default PatternBoard
