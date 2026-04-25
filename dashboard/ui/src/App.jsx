import React, { useState, useEffect } from 'react'
import './App.css'
import GraphView from './components/GraphView'
import PriorityRanking from './components/PriorityRanking'
import PatternBoard from './components/PatternBoard'
import ProgressTracker from './components/ProgressTracker'
import AgentActivity from './components/AgentActivity'
import ChangeFeed from './components/ChangeFeed'
import SystemHealth from './components/SystemHealth'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function App() {
  const [activeTab, setActiveTab] = useState('overview')
  const [systemStats, setSystemStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchStats()
  }, [])

  const fetchStats = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/stats`)
      if (!response.ok) throw new Error('Failed to fetch stats')
      const data = await response.json()
      setSystemStats(data.stats)
      setLoading(false)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const renderTabContent = () => {
    switch (activeTab) {
      case 'overview':
        return (
          <div className="dashboard-grid">
            <div className="grid-row">
              <SystemHealth />
              <ChangeFeed />
            </div>
            <div className="grid-row">
              <PriorityRanking limit={10} />
              <PatternBoard limit={6} />
            </div>
            <div className="grid-row">
              <ProgressTracker limit={10} />
              <AgentActivity limit={10} />
            </div>
          </div>
        )
      case 'graph':
        return <GraphView />
      case 'priorities':
        return <PriorityRanking />
      case 'patterns':
        return <PatternBoard />
      case 'progress':
        return <ProgressTracker />
      case 'activity':
        return <AgentActivity />
      case 'changes':
        return <ChangeFeed />
      case 'health':
        return <SystemHealth fullWidth />
      default:
        return null
    }
  }

  if (loading) {
    return (
      <div className="loading-container">
        <div className="loading-spinner"></div>
        <p>Loading Stability Intelligence Dashboard...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="error-container">
        <h2>Error Loading Dashboard</h2>
        <p>{error}</p>
        <button onClick={fetchStats}>Retry</button>
      </div>
    )
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Stability Intelligence Dashboard</h1>
        <div className="header-stats">
          <div className="stat-badge">
            <span className="stat-value">{systemStats?.total_incidents || 0}</span>
            <span className="stat-label">Incidents</span>
          </div>
          <div className="stat-badge">
            <span className="stat-value">{systemStats?.open_action_items || 0}</span>
            <span className="stat-label">Open Actions</span>
          </div>
          <div className="stat-badge">
            <span className="stat-value">{systemStats?.worsening_patterns || 0}</span>
            <span className="stat-label">Worsening</span>
          </div>
          <div className="stat-badge">
            <span className="stat-value">{systemStats?.proposed_strategies || 0}</span>
            <span className="stat-label">Strategies</span>
          </div>
        </div>
      </header>

      <nav className="app-nav">
        {[
          { id: 'overview', label: 'Overview', icon: '📊' },
          { id: 'graph', label: 'Graph', icon: '🕸️' },
          { id: 'priorities', label: 'Priorities', icon: '🎯' },
          { id: 'patterns', label: 'Patterns', icon: '🔍' },
          { id: 'progress', label: 'Progress', icon: '📈' },
          { id: 'activity', label: 'Activity', icon: '🤖' },
          { id: 'changes', label: 'Changes', icon: '📝' },
          { id: 'health', label: 'Health', icon: '❤️' },
        ].map((tab) => (
          <button
            key={tab.id}
            className={`nav-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
          </button>
        ))}
      </nav>

      <main className="app-main">
        {renderTabContent()}
      </main>

      <footer className="app-footer">
        <p>Stability Intelligence System v1.0.0 | Connected to API at {API_BASE_URL}</p>
      </footer>
    </div>
  )
}

export default App
