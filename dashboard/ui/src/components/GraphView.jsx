import React, { useEffect, useRef, useState } from 'react'
import CytoscapeComponent from 'react-cytoscapejs'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const GraphView = ({ limit = 1000, focusNodeId = null, onFocusComplete = null }) => {
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedNode, setSelectedNode] = useState(null)
  const [nodeDetails, setNodeDetails] = useState(null)
  const [cy, setCy] = useState(null)
  const cyRef = useRef(null)

  useEffect(() => {
    fetchGraphData()
  }, [limit])

  useEffect(() => {
    if (focusNodeId && cy) {
      const node = cy.$(`#${focusNodeId}`)
      if (node.length > 0) {
        cy.animate({
          center: { eles: node },
          zoom: 2
        }, { duration: 500 })
        node.select()
        fetchNodeDetails(focusNodeId)
        setSelectedNode(focusNodeId)
        onFocusComplete?.()
      }
    }
  }, [focusNodeId, cy])

  const fetchGraphData = async () => {
    try {
      setLoading(true)
      const response = await fetch(`${API_BASE_URL}/graph?limit=${limit}`)
      if (!response.ok) throw new Error('Failed to fetch graph data')
      const data = await response.json()
      setGraphData({
        nodes: data.nodes.map(n => ({
          data: {
            id: n.data.id,
            label: n.data.label,
            type: n.data.type,
            color: getNodeColor(n.data.type, n.data.color)
          }
        })),
        edges: data.edges.map(e => ({
          data: {
            id: e.data.id,
            source: e.data.source,
            target: e.data.target,
            label: e.data.label,
            weight: e.data.weight
          }
        }))
      })
      setLoading(false)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const fetchNodeDetails = async (nodeId) => {
    try {
      const response = await fetch(`${API_BASE_URL}/nodes/${nodeId}`)
      if (!response.ok) throw new Error('Failed to fetch node details')
      const data = await response.json()
      setNodeDetails(data)
    } catch (err) {
      console.error('Error fetching node details:', err)
    }
  }

  const getNodeColor = (type, defaultColor) => {
    const colors = {
      'Incident': '#ef4444',
      'ActionItem': '#22c55e',
      'RootCause': '#f97316',
      'Component': '#3b82f6',
      'PatternCluster': '#a855f7',
      'Strategy': '#eab308',
      'ActivityEvent': '#64748b'
    }
    return colors[type] || defaultColor || '#9ca3af'
  }

  const layout = {
    name: 'cose',
    animate: true,
    animationDuration: 1000,
    nodeRepulsion: 400000,
    idealEdgeLength: 100,
    edgeElasticity: 100,
    nestingFactor: 5,
    gravity: 80,
    numIter: 1000,
    initialTemp: 200,
    coolingFactor: 0.95,
    minTemp: 1.0
  }

  const stylesheet = [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        'label': 'data(label)',
        'width': 40,
        'height': 40,
        'font-size': '10px',
        'text-valign': 'bottom',
        'text-halign': 'center',
        'color': '#fff',
        'text-background-color': '#0f172a',
        'text-background-opacity': 0.8,
        'text-background-padding': '2px',
        'text-background-shape': 'roundrectangle',
        'border-width': 2,
        'border-color': '#334155'
      }
    },
    {
      selector: 'edge',
      style: {
        'width': 2,
        'line-color': '#64748b',
        'target-arrow-color': '#64748b',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'label': 'data(label)',
        'font-size': '8px',
        'color': '#94a3b8',
        'text-background-color': '#0f172a',
        'text-background-opacity': 0.8
      }
    },
    {
      selector: ':selected',
      style: {
        'border-width': 4,
        'border-color': '#fbbf24',
        'shadow-blur': 10,
        'shadow-color': '#fbbf24'
      }
    }
  ]

  const handleNodeClick = (event) => {
    const node = event.target
    const nodeId = node.id()
    setSelectedNode(nodeId)
    fetchNodeDetails(nodeId)
  }

  if (loading) {
    return (
      <div className="section-container graph-loading">
        <div className="loading-spinner"></div>
        <p>Loading graph visualization...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="section-container graph-error">
        <h3>Graph Error</h3>
        <p>{error}</p>
        <button onClick={fetchGraphData}>Retry</button>
      </div>
    )
  }

  const elements = [...graphData.nodes, ...graphData.edges]

  return (
    <div className="section-container graph-view">
      <div className="section-header">
        <h2>Knowledge Graph Visualization</h2>
        <div className="graph-controls">
          <button onClick={fetchGraphData} className="btn-secondary">Refresh</button>
          <span className="graph-stats">
            {graphData.nodes.length} nodes · {graphData.edges.length} edges
          </span>
        </div>
      </div>
      
      <div className="graph-content">
        <div className="graph-canvas">
          <CytoscapeComponent
            elements={elements}
            style={{ width: '100%', height: '100%' }}
            layout={layout}
            stylesheet={stylesheet}
            cy={(cyInstance) => {
              cyRef.current = cyInstance
              setCy(cyInstance)
              cyInstance.on('tap', 'node', handleNodeClick)
            }}
          />
        </div>
        
        {selectedNode && nodeDetails && (
          <div className="node-details-panel">
            <div className="panel-header">
              <h3>Node Details</h3>
              <button 
                className="close-btn"
                onClick={() => {
                  setSelectedNode(null)
                  setNodeDetails(null)
                  if (cyRef.current) {
                    cyRef.current.$(':selected').unselect()
                  }
                }}
              >
                ×
              </button>
            </div>
            <div className="panel-content">
              <div className="detail-row">
                <span className="detail-label">ID:</span>
                <span className="detail-value">{nodeDetails.id}</span>
              </div>
              <div className="detail-row">
                <span className="detail-label">Type:</span>
                <span className="detail-value">{nodeDetails.type}</span>
              </div>
              {Object.entries(nodeDetails.properties || {}).map(([key, value]) => (
                <div key={key} className="detail-row">
                  <span className="detail-label">{key}:</span>
                  <span className="detail-value">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </span>
                </div>
              ))}
              {nodeDetails.related_nodes && nodeDetails.related_nodes.length > 0 && (
                <div className="related-nodes">
                  <h4>Related Nodes ({nodeDetails.related_nodes.length})</h4>
                  <ul>
                    {nodeDetails.related_nodes.slice(0, 10).map((node, idx) => (
                      <li key={idx}>
                        <span className="rel-type">{node.relationship}</span>
                        <span className="rel-label">{node.label}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      
      <div className="graph-legend">
        <div className="legend-title">Node Types</div>
        <div className="legend-items">
          {[
            { type: 'Incident', color: '#ef4444' },
            { type: 'ActionItem', color: '#22c55e' },
            { type: 'RootCause', color: '#f97316' },
            { type: 'Component', color: '#3b82f6' },
            { type: 'PatternCluster', color: '#a855f7' },
            { type: 'Strategy', color: '#eab308' },
          ].map(({ type, color }) => (
            <div key={type} className="legend-item">
              <span className="legend-color" style={{ backgroundColor: color }}></span>
              <span className="legend-label">{type}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default GraphView
