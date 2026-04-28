import React from 'react';
import { SystemStatusBar } from './SystemStatusBar';
import { PriorityItems } from './PriorityItems';
import { PatternHealth } from './PatternHealth';
import { ActivityTimeline } from './ActivityTimeline';
import { AgentHeartbeat } from './AgentHeartbeat';

/**
 * OverviewSection Component
 * Main overview/landing page with all subsections
 *
 * Props:
 *   - systemStats: object
 *   - priorityItems: array
 *   - patterns: array
 *   - events: array
 *   - agents: array
 *   - onItemClick: (item) => void
 *   - onPatternClick: (pattern) => void
 *   - onEventClick: (event) => void
 *   - onAgentClick: (agent) => void
 */

export function OverviewSection({
  systemStats,
  priorityItems,
  patterns,
  events,
  agents,
  onItemClick,
  onPatternClick,
  onEventClick,
  onAgentClick,
}) {
  return (
    <div className="space-y-6">
      {/* Row 1 - System Status Bar */}
      <SystemStatusBar stats={systemStats} />

      {/* Row 2 - Priority Items (2/3) + Pattern Health (1/3) */}
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-8">
          <PriorityItems items={priorityItems} onItemClick={onItemClick} />
        </div>
        <div className="col-span-12 lg:col-span-4">
          <PatternHealth patterns={patterns} onPatternClick={onPatternClick} />
        </div>
      </div>

      {/* Row 3 - Activity Timeline (2/3) + Agent Heartbeat (1/3) */}
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-8">
          <ActivityTimeline events={events} onEventClick={onEventClick} />
        </div>
        <div className="col-span-12 lg:col-span-4">
          <AgentHeartbeat agents={agents} onAgentClick={onAgentClick} />
        </div>
      </div>
    </div>
  );
}
