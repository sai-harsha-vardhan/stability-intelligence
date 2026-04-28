import React from 'react';
import { Command, Activity, Clock, Zap } from 'lucide-react';
import { AgentStatusDot } from '../ui/AgentStatusDot';
import { clsx } from 'clsx';

/**
 * Topbar Component
 * Fixed header with logo, system status, search, and user info
 *
 * Props:
 *   - onSearchOpen: () => void
 *   - systemStats: object
 *   - agentStatus: array of agent statuses
 */

const AGENT_MOCK_STATUS = [
  { name: 'Ingestion', status: 'idle' },
  { name: 'Analyzer', status: 'idle' },
  { name: 'Strategist', status: 'running' },
  { name: 'Prioritizer', status: 'idle' },
];

export function Topbar({ onSearchOpen, systemStats, agentStatus = AGENT_MOCK_STATUS }) {
  const lastSyncMinutes = 4;
  const hasCritical = systemStats?.p0_count > 0;

  return (
    <header className="fixed top-0 left-0 right-0 h-[var(--topbar-height)] bg-[var(--bg-surface)] border-b border-[var(--bg-overlay)] z-40">
      <div className="h-full px-4 flex items-center justify-between">
        {/* Left - Logo */}
        <div className="flex items-center gap-3">
          <div className="w-6 h-6 bg-[var(--accent)] rounded-sm flex items-center justify-center">
            <Activity className="w-4 h-4 text-white" />
          </div>
          <h1 className="font-mono font-semibold text-sm text-[var(--text-primary)] tracking-tight">
            Stability
          </h1>
        </div>

        {/* Center - Search */}
        <button
          onClick={onSearchOpen}
          className="flex items-center gap-2 px-3 py-1.5 bg-[var(--bg-elevated)] rounded-md text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-overlay)] transition-colors"
        >
          <Command className="w-4 h-4" />
          <span className="text-sm">Search</span>
          <kbd className="ml-2 px-1.5 py-0.5 text-[10px] font-mono bg-[var(--bg-surface)] rounded">
            ⌘K
          </kbd>
        </button>

        {/* Right - Status Info */}
        <div className="flex items-center gap-4">
          {/* System Status Pill */}
          <div
            className={clsx(
              'flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold',
              hasCritical
                ? 'bg-[var(--critical)]/20 text-[var(--critical)]'
                : 'bg-[var(--low)]/20 text-[var(--low)]'
            )}
          >
            <span className={clsx('w-2 h-2 rounded-full', hasCritical ? 'bg-[var(--critical)] animate-pulse' : 'bg-[var(--low)]')} />
            {hasCritical ? `${systemStats?.p0_count} P0 Active` : 'Operational'}
          </div>

          {/* Last Sync */}
          <div className="flex items-center gap-1.5 text-xs text-[var(--text-secondary)]">
            <Clock className="w-3.5 h-3.5" />
            <span className="font-mono">{lastSyncMinutes}m ago</span>
          </div>

          {/* Agent Status Dots */}
          <div className="flex items-center gap-1 px-2 py-1 bg-[var(--bg-elevated)] rounded">
            <span className="text-[10px] text-[var(--text-tertiary)] mr-1">Agents</span>
            {agentStatus.map((agent) => (
              <AgentStatusDot key={agent.name} status={agent.status} size="sm" />
            ))}
          </div>

          {/* User Avatar */}
          <div className="w-8 h-8 rounded-full bg-[var(--accent)] flex items-center justify-center text-xs font-semibold text-white">
            SE
          </div>
        </div>
      </div>
    </header>
  );
}
