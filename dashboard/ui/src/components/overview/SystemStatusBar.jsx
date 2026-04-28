import React from 'react';
import { clsx } from 'clsx';
import { Activity, AlertTriangle, CheckCircle2, Target, Zap, Bot } from 'lucide-react';

/**
 * SystemStatusBar Component
 * Full-width status banner showing key system metrics
 *
 * Props:
 *   - stats: object with system statistics
 */

const STAT_ITEMS = [
  { key: 'openActions', label: 'Open Actions', icon: Target, color: 'var(--info)' },
  { key: 'worseningPatterns', label: 'Worsening', icon: AlertTriangle, color: 'var(--high)' },
  { key: 'p0Incidents', label: 'P0/P1 This Week', icon: Activity, color: 'var(--critical)' },
  { key: 'strategiesGenerated', label: 'Strategies', icon: Zap, color: 'var(--strategy)' },
  { key: 'agentsHealthy', label: 'Agents Healthy', icon: Bot, color: 'var(--low)' },
];

const MOCK_STATS = {
  openActions: 12,
  worseningPatterns: 3,
  p0Incidents: 2,
  strategiesGenerated: 5,
  agentsHealthy: 4,
};

export function SystemStatusBar({ stats = MOCK_STATS }) {
  const hasCritical = stats.p0Incidents > 0;

  return (
    <div
      className={clsx(
        'w-full px-6 py-3 flex items-center justify-between border-b transition-all',
        hasCritical
          ? 'bg-[var(--critical)]/10 border-[var(--critical)]/30'
          : 'bg-[var(--bg-surface)] border-[var(--bg-overlay)]'
      )}
    >
      {STAT_ITEMS.map((item, idx) => {
        const Icon = item.icon;
        const value = stats[item.key] ?? 0;
        const isCritical = item.key === 'p0Incidents' && value > 0;

        return (
          <React.Fragment key={item.key}>
            <div className="flex items-center gap-3">
              <div
                className="w-8 h-8 rounded-md flex items-center justify-center"
                style={{ backgroundColor: `${item.color}20` }}
              >
                <Icon
                  className="w-4 h-4"
                  style={{ color: isCritical ? 'var(--critical)' : item.color }}
                />
              </div>
              <div>
                <div
                  className={clsx(
                    'text-2xl font-mono font-bold tabular-nums leading-none',
                    isCritical && 'text-[var(--critical)]'
                  )}
                  style={{ color: isCritical ? undefined : 'var(--text-primary)' }}
                >
                  {value}
                </div>
                <div className="text-[10px] uppercase tracking-wide text-[var(--text-secondary)] mt-0.5">
                  {item.label}
                </div>
              </div>
            </div>
            {idx < STAT_ITEMS.length - 1 && (
              <div className="w-px h-10 bg-[var(--bg-overlay)]" />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}
