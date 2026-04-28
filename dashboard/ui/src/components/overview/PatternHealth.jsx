import React from 'react';
import { clsx } from 'clsx';
import { TrendIndicator } from '../ui/TrendIndicator';

/**
 * PatternHealth Component
 * Mini pattern board showing top 5 clusters
 *
 * Props:
 *   - patterns: array of pattern clusters
 *   - limit: number (default: 5)
 *   - onPatternClick: (pattern) => void
 */

const MOCK_PATTERNS = [
  { id: 'CL-0042', name: 'Database Connection Issues', frequency: 14, trend: 'worsening', maxFreq: 14 },
  { id: 'CL-0031', name: 'Webhook Reliability Failures', frequency: 9, trend: 'stable', maxFreq: 14 },
  { id: 'CL-0028', name: 'Payment Processing Delays', frequency: 7, trend: 'improving', maxFreq: 14 },
  { id: 'CL-0015', name: 'Configuration Drift', frequency: 5, trend: 'stable', maxFreq: 14 },
  { id: 'CL-0008', name: 'API Rate Limiting', frequency: 4, trend: 'stable', maxFreq: 14 },
];

export function PatternHealth({ patterns = MOCK_PATTERNS, limit = 5, onPatternClick }) {
  const displayPatterns = patterns.slice(0, limit);
  const maxFreq = Math.max(...patterns.map(p => p.frequency));

  return (
    <div className="bg-[var(--bg-surface)] rounded-lg border border-[var(--bg-overlay)]">
      <div className="px-4 py-3 border-b border-[var(--bg-overlay)] flex items-center justify-between">
        <h3 className="font-mono font-semibold text-sm text-[var(--text-primary)]">
          Pattern Health
        </h3>
        <span className="text-xs text-[var(--text-tertiary)]">
          Top {limit} Clusters
        </span>
      </div>

      <div className="p-4 space-y-4">
        {displayPatterns.map((pattern) => {
          const percentage = (pattern.frequency / maxFreq) * 100;
          const isWorsening = pattern.trend === 'worsening';

          return (
            <button
              key={pattern.id}
              onClick={() => onPatternClick?.(pattern)}
              className="w-full text-left group"
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-[var(--text-primary)] group-hover:text-[var(--accent)] transition-colors truncate pr-2">
                  {pattern.name}
                </span>
                <TrendIndicator
                  trend={pattern.trend}
                  value={pattern.frequency}
                  showLabel={false}
                />
              </div>

              {/* Frequency Bar */}
              <div className="relative h-2 bg-[var(--bg-elevated)] rounded-full overflow-hidden">
                <div
                  className={clsx(
                    'h-full rounded-full transition-all duration-300',
                    isWorsening ? 'bg-[var(--high)]' : 'bg-[var(--info)]'
                  )}
                  style={{ width: `${percentage}%` }}
                />
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between mt-1.5">
                <span className="text-xs text-[var(--text-tertiary)]">
                  Freq: {pattern.frequency}
                </span>
                {isWorsening && (
                  <span className="w-1.5 h-1.5 bg-[var(--high)] rounded-full animate-pulse" />
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
