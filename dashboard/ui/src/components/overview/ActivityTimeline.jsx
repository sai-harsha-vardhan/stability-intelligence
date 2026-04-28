import React from 'react';
import { clsx } from 'clsx';
import { formatDistanceToNow } from '../../utils/date';

/**
 * ActivityTimeline Component
 * Last 24 hours of system events as a compact timeline
 *
 * Props:
 *   - events: array of activity events
 *   - limit: number (default: 10)
 *   - onEventClick: (event) => void
 */

const EVENT_ICONS = {
  new_incident: '⚠️',
  priority_shift: '▲',
  strategy_generated: '◈',
  resolved: '✓',
  cluster_worsening: '↑',
  verified_effective: '✓',
  agent_failure: '❌',
};

const EVENT_COLORS = {
  new_incident: 'var(--critical)',
  priority_shift: 'var(--medium)',
  strategy_generated: 'var(--strategy)',
  resolved: 'var(--low)',
  cluster_worsening: 'var(--high)',
  verified_effective: 'var(--low)',
  agent_failure: 'var(--critical)',
};

const MOCK_EVENTS = [
  { id: 'EVT-001', type: 'new_incident', title: 'INC-2026-0051 opened — matched cluster "Connector Response Drift"', time: new Date(Date.now() - 120000) },
  { id: 'EVT-002', type: 'priority_shift', title: 'Action item #433 jumped rank 8 → 2', time: new Date(Date.now() - 1080000) },
  { id: 'EVT-003', type: 'strategy_generated', title: '"Connector Contract Test Suite" strategy created', time: new Date(Date.now() - 3600000) },
  { id: 'EVT-004', type: 'resolved', title: 'Action item #401 marked resolved by @praveenvijay', time: new Date(Date.now() - 10800000) },
  { id: 'EVT-005', type: 'cluster_worsening', title: '"Scheduler Idempotency Failures" changed stable → worsening', time: new Date(Date.now() - 86400000) },
  { id: 'EVT-006', type: 'verified_effective', title: 'Action item #388 verified effective after 30 days', time: new Date(Date.now() - 172800000) },
  { id: 'EVT-007', type: 'new_incident', title: 'INC-2026-0049 opened — P1 database timeout', time: new Date(Date.now() - 180000) },
  { id: 'EVT-008', type: 'strategy_generated', title: '"Automated Rollback System" strategy created', time: new Date(Date.now() - 7200000) },
];

function groupEventsByHour(events) {
  const groups = {};
  const now = Date.now();

  events.forEach(event => {
    const hoursAgo = Math.floor((now - event.time.getTime()) / (1000 * 60 * 60));
    const key = hoursAgo === 0 ? 'Within last hour' :
      hoursAgo === 1 ? '1 hour ago' :
      `${hoursAgo} hours ago`;

    if (!groups[key]) groups[key] = [];
    groups[key].push(event);
  });

  return Object.entries(groups);
}

export function ActivityTimeline({ events = MOCK_EVENTS, limit = 10, onEventClick }) {
  const displayEvents = events.slice(0, limit);
  const groupedEvents = groupEventsByHour(displayEvents);

  return (
    <div className="bg-[var(--bg-surface)] rounded-lg border border-[var(--bg-overlay)]">
      <div className="px-4 py-3 border-b border-[var(--bg-overlay)] flex items-center justify-between">
        <h3 className="font-mono font-semibold text-sm text-[var(--text-primary)]">
          Activity Timeline
        </h3>
        <span className="text-xs text-[var(--text-tertiary)]">
          Last 24 hours
        </span>
      </div>

      <div className="p-4">
        {groupedEvents.map(([timeGroup, groupEvents], groupIdx) => (
          <div key={timeGroup} className={groupIdx > 0 ? 'mt-4' : ''}>
            <div className="text-xs font-mono text-[var(--text-tertiary)] uppercase tracking-wide mb-2">
              {timeGroup}
            </div>
            <div className="space-y-2">
              {groupEvents.map((event) => (
                <button
                  key={event.id}
                  onClick={() => onEventClick?.(event)}
                  className="w-full flex items-start gap-3 p-2 rounded hover:bg-[var(--bg-elevated)]/50 transition-colors text-left group"
                >
                  <span
                    className="text-lg flex-shrink-0"
                    style={{ color: EVENT_COLORS[event.type] }}
                  >
                    {EVENT_ICONS[event.type]}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span
                        className="text-[10px] font-semibold uppercase tracking-wide"
                        style={{ color: EVENT_COLORS[event.type] }}
                      >
                        {event.type.replace(/_/g, ' ')}
                      </span>
                      <span className="text-[10px] text-[var(--text-tertiary)]">
                        {formatDistanceToNow(event.time)}
                      </span>
                    </div>
                    <p className="text-sm text-[var(--text-primary)] group-hover:text-[var(--accent)] transition-colors line-clamp-2">
                      {event.title}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
