import React, { useState, useEffect, useCallback } from 'react'
import './App.css'
import './styles/design-system.css'
import GraphView from './components/GraphView'
import PriorityRanking from './components/PriorityRanking'
import PatternBoard from './components/PatternBoard'
import ProgressTracker from './components/ProgressTracker'
import AgentActivity from './components/AgentActivity'
import ChangeFeed from './components/ChangeFeed'
import SystemHealth from './components/SystemHealth'
import { CommandPalette } from './components/ui/CommandPalette'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

function App() {
  const [activeTab, setActiveTab] = useState('overview')
  const [systemStats, setSystemStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [triggering, setTriggering] = useState(false)
  const [triggerStatus, setTriggerStatus] = useState('')
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  const [lastUpdated, setLastUpdated] = useState(null)

  useEffect(() => {
    fetchStats()
    
    // Set up polling every 30 seconds
    const interval = setInterval(fetchStats, 30000)
    return () => clearInterval(interval)
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Command palette: Cmd/Ctrl + K
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setCommandPaletteOpen(true)
      }
      
      // Section shortcuts: Cmd/Ctrl + 1-7
      if ((e.metaKey || e.ctrlKey) && e.key >= '1' && e.key <= '7') {
        e.preventDefault()
        const tabs = ['overview', 'graph', 'priorities', 'patterns', 'progress', 'activity', 'changes']
        const index = parseInt(e.key) - 1
        if (tabs[index]) {
          setActiveTab(tabs[index])
        }
      }
      
      // Refresh: R key
      if (e.key === 'r' || e.key === 'R') {
        if (!e.metaKey && !e.ctrlKey && !commandPaletteOpen) {
          e.preventDefault()
          fetchStats()
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [commandPaletteOpen])

  const fetchStats = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/stats`)
      if (!response.ok) throw new Error('Failed to fetch stats')
      const data = await response.json()
      setSystemStats(data.stats)
      setLastUpdated(new Date())
      setLoading(false)
    } catch (err) {
      setError(err.message)
      setLoading(false)
    }
  }

  const handleManualTrigger = async () => {
    setTriggering(true)
    setTriggerStatus('🔄 Syncing from GitHub...')
    
    try {
      // Step 1: Sync from GitHub
      const syncResponse = await fetch(`${API_BASE_URL}/trigger-sync`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      
      if (!syncResponse.ok) {
        throw new Error('Sync failed')
      }
      
      const syncData = await syncResponse.json()
      setTriggerStatus(`✅ Synced ${syncData.issues_synced} issues. Analyzing...`)
      
      // Step 2: Run analysis
      const analyzeResponse = await fetch(`${API_BASE_URL}/analyze-now`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      
      if (!analyzeResponse.ok) {
        throw new Error('Analysis failed')
      }
      
      setTriggerStatus('✅ Analysis complete! Refreshing dashboard...')
      
      // Step 3: Refresh dashboard stats
      await fetchStats()
      
      setTriggerStatus('✅ Done!')
      setTimeout(() => setTriggerStatus(''), 3000)
    } catch (err) {
      setTriggerStatus(`❌ Error: ${err.message}`)
      setTimeout(() => setTriggerStatus(''), 5000)
    } finally {
      setTriggering(false)
    }
  }

  const handleSearchSelect = (result) => {
    // Navigate based on result type
    const typeMap = {
      'ActionItem': 'priorities',
      'Strategy': 'priorities',
      'PatternCluster': 'patterns',
      'Incident': 'graph',
    }
    
    const tab = typeMap[result.type] || 'overview'
    setActiveTab(tab)
    
    // Could also open a detail panel here
    console.log('Selected:', result)
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
        <div className="header-left">
          <h1>◈ Stability</h1>
          <span className="version">v1.0</span>
        </div>
        
        <div className="header-center">
          <button 
            className="search-trigger"
            onClick={() => setCommandPaletteOpen(true)}
          >
            <span>⌘K Search</span>
          </button>
        </div>
        
        <div className="header-right">
          <div className="system-status-pill">
            <span className={`status-dot ${systemStats?.p0_incidents > 0 ? 'critical' : 'healthy'}`}></span>
            <span className="status-text">
              {systemStats?.p0_incidents > 0 ? 'Incident' : 'Operational'}
            </span>
          </div>
          
          <div className="last-sync">
            <span className="sync-dot"></span>
            <span className="sync-text">
              {lastUpdated ? `Updated ${Math.floor((Date.now() - lastUpdated) / 1000 / 60)}m ago` : 'Updating...'}
            </span>
          </div>
          
          <div className="agent-dots">
            <span className="agent-dot healthy" title="Ingestion Agent"></span>
            <span className="agent-dot healthy" title="Pattern Detection Agent"></span>
            <span className="agent-dot healthy" title="Scoring Agent"></span>
            <span className="agent-dot healthy" title="Strategy Agent"></span>
          </div>
          
          <button
            className="trigger-btn"
            onClick={handleManualTrigger}
            disabled={triggering}
            title="Manually check for new incidents and analyze"
          >
            {triggering ? '⏳ Analyzing...' : '🔄 Sync'}
          </button>
        </div>
        
        {triggerStatus && (
          <div className="trigger-status">
            {triggerStatus}
          </div>
        )}
      </header>

      <nav className="app-nav">
        {[
          { id: 'overview', label: 'Overview', icon: '◈', shortcut: '1' },
          { id: 'graph', label: 'Graph', icon: '⬡', shortcut: '2' },
          { id: 'priorities', label: 'Priorities', icon: '↑', shortcut: '3', count: systemStats?.open_action_items },
          { id: 'patterns', label: 'Patterns', icon: '◎', shortcut: '4', count: systemStats?.worsening_patterns },
          { id: 'progress', label: 'Progress', icon: '✓', shortcut: '5', count: systemStats?.resolved_this_week },
          { id: 'activity', label: 'Agents', icon: '⚡', shortcut: '6' },
          { id: 'changes', label: 'Feed', icon: '⟳', shortcut: '7' },
          { id: 'health', label: 'Health', icon: '●', shortcut: '' },
        ].map((tab) => (
          <button
            key={tab.id}
            className={`nav-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
            {tab.count > 0 && (
              <span className="tab-count">{tab.count}</span>
            )}
            {tab.shortcut && (
              <span className="tab-shortcut">⌘{tab.shortcut}</span>
            )}
          </button>
        ))}
      </nav>

      <main className="app-main">
        {renderTabContent()}
      </main>

      <footer className="app-footer">
        <p>Stability Intelligence System v1.0.0 | Connected to API at {API_BASE_URL}</p>
        <p className="keyboard-hint">Press ⌘K to search · ⌘1-7 to navigate · R to refresh</p>
      </footer>

      <CommandPalette 
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onSelect={handleSearchSelect}
      />
    </div>
  )
}

export default App
