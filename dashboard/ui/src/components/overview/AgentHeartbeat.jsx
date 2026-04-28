import React from 'react';
import { clsx } from 'clsx';
import { AgentStatusDot } from '../ui/AgentStatusDot';
import { Clock, Activity } from 'lucide-react';

/**
 * AgentHeartbeat Component
 * 4 agent status cards in a 2×2 grid
 *
 * Props:
 *   - agents: array of agent statuses
 *   - onAgentClick: (agent) => void
 */

const MOCK_AGENTS = [
  {
    name: 'Ingestion Agent',
    status: 'idle',
    lastRun: new Date(Date.now() - 120000),
    duration: 34,
    processed: 3,
    lastOutput: 'Added INC-2026-0051 → cluster "Connector Response Drift" (0.91)',
  },
  {
    name: 'Analyzer Agent',
    status: 'idle',
    lastRun: new Date(Date.now() - 1800000),
    duration: 142,
    processed: 12,
    lastOutput: 'Analyzed 12 incidents, found 3 new patterns',
  },
  {
    name: 'Strategist Agent',
    status: 'running',
    lastRun: new Date(),
    duration: 45,
    processed: 1,
    lastOutput: 'Generating strategies for worsening clusters...',
  },
  {
    name: 'Prioritizer Agent',
    status: 'idle',
    lastRun: new Date(Date.now() - 3600000),
    duration: 28,
    processed: 47,
    lastOutput: 'Recalculated priority scores for 47 action items',
  },
];

const formatDuration = (seconds) => {
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}m ${secs}s`;
};

const formatTimeAgo = (date) => {
  const mins = Math.floor((Date.now() - date.getTime()) / (1000 * 60));
  if (mins < 1) return 'Just now';
  if (mins === 1) return '1 min ago';
  if (mins < 60) return `${mins} mins ago`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ago`;
};

export function AgentHeartbeat({ agents = MOCK_AGENTS, onAgentClick }) {
  return (
    <div className="bg-[var(--bg-surface)] rounded-lg border border-[var(--bg-overlay)]">
      <div className="px-4 py-3 border-b border-[var(--bg-overlay)] flex items-center justify-between">
        <h3 className="font-mono font-semibold text-sm text-[var(--text-primary)]">
          Agent Heartbeat
        </h3>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-[var(--low)]" />
          <span className="text-xs text-[var(--text-secondary)]">All Healthy</span>
        </div>
      </div>

      <div className="p-4 grid grid-cols-2 gap-3">
        {agents.map((agent) => (
          <button
            key={agent.name}
            onClick={() => onAgentClick?.(agent)}
            className="p-3 bg-[var(--bg-elevated)]/30 rounded-lg hover:bg-[var(--bg-elevated)]/60 transition-colors text-left group"
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <AgentStatusDot status={agent.status} size="sm" />
                <span className="text-xs font-semibold text-[var(--text-primary)]">
                  {agent.name}
                </span>
              </div>
              <span className="text-[10px] uppercase font-semibold text-[var(--text-secondary)]">
                {agent.status.toUpperCase()}
              </span>
            </div>

            {/* Stats */}
            <div className="flex items-center gap-3 text-xs text-[var(--text-secondary)] mb-2">
              <div className="flex items-center gap-1">
                <Clock className="w-3 h-3" />
                <span>{formatTimeAgo(agent.lastRun)}</span>
              </div>
              <div className="flex items-center gap-1">
                <Activity className="w-3 h-3" />
                <span>{formatDuration(agent.duration)}</span>
              </div>
            </div>

            {/* Output */}
            <p className="text-[11px] text-[var(--text-tertiary)] line-clamp-2 leading-relaxed">
              {agent.lastOutput}
            </p>
          </button>
        ))}
      </div>
    </div>
  );
}
