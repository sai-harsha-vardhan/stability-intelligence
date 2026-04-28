import React from 'react';
import { clsx } from 'clsx';
import { TypeBadge } from '../ui/TypeBadge';
import { RankChange } from '../ui/RankChange';
import { ChevronRight } from 'lucide-react';

/**
 * PriorityItems Component
 * Top 5 action items and strategies ranked by priority score
 *
 * Props:
 *   - items: array of priority items
 *   - limit: number (default: 5)
 *   - onItemClick: (item) => void
 */

const MOCK_ITEMS = [
  {
    rank: 1,
    change: 3,
    type: 'action',
    title: 'Increase database connection pool size for payment processor',
    cluster: 'Database Connection Issues',
    score: 9.4,
    complexity: 'Low',
    isNew: false,
  },
  {
    rank: 2,
    change: 0,
    type: 'strategy',
    title: 'Implement circuit breaker pattern for all external API calls',
    cluster: 'Webhook Reliability',
    score: 8.7,
    complexity: 'High',
    isNew: false,
  },
  {
    rank: 3,
    change: -1,
    type: 'action',
    title: 'Add rate limiting to webhook endpoints',
    cluster: 'Webhook Reliability',
    score: 8.2,
    complexity: 'Medium',
    isNew: false,
  },
  {
    rank: 4,
    change: 0,
    type: 'action',
    title: 'Implement retry mechanism with exponential backoff',
    cluster: 'Payment Processing',
    score: 7.9,
    complexity: 'Medium',
    isNew: false,
  },
  {
    rank: 5,
    change: 0,
    type: 'strategy',
    title: 'Automated health checks for all microservices',
    cluster: 'System Health',
    score: 7.5,
    complexity: 'High',
    isNew: true,
  },
];

const COMPLEXITY_SIZE = {
  Low: 'w-2 h-2',
  Medium: 'w-3 h-3',
  High: 'w-4 h-4',
};

const COMPLEXITY_COLOR = {
  Low: 'var(--low)',
  Medium: 'var(--medium)',
  High: 'var(--high)',
};

export function PriorityItems({ items = MOCK_ITEMS, limit = 5, onItemClick }) {
  const displayItems = items.slice(0, limit);

  return (
    <div className="bg-[var(--bg-surface)] rounded-lg border border-[var(--bg-overlay)]">
      <div className="px-4 py-3 border-b border-[var(--bg-overlay)] flex items-center justify-between">
        <h3 className="font-mono font-semibold text-sm text-[var(--text-primary)]">
          Top Priority Items
        </h3>
        <span className="text-xs text-[var(--text-tertiary)]">
          Showing {displayItems.length} of {items.length}
        </span>
      </div>

      <div className="divide-y divide-[var(--bg-overlay)]">
        {displayItems.map((item) => (
          <button
            key={`${item.type}-${item.rank}`}
            onClick={() => onItemClick?.(item)}
            className="w-full px-4 py-3 flex items-start gap-3 hover:bg-[var(--bg-elevated)]/50 transition-colors text-left group"
          >
            {/* Rank */}
            <div className="flex flex-col items-center min-w-[40px]">
              <span className="font-mono text-xl font-bold text-[var(--text-tertiary)]">
                {item.rank}
              </span>
              <RankChange change={item.change} isNew={item.isNew} size="sm" />
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <TypeBadge type={item.type} size="sm" />
                <span
                  className="text-xs px-1.5 py-0.5 rounded"
                  style={{
                    backgroundColor: 'var(--bg-elevated)',
                    color: 'var(--text-secondary)',
                  }}
                >
                  {item.cluster}
                </span>
              </div>
              <p className="text-sm text-[var(--text-primary)] truncate group-hover:text-[var(--accent)] transition-colors">
                {item.title}
              </p>
            </div>

            {/* Meta */}
            <div className="flex items-center gap-3">
              {/* Score */}
              <div className="text-right">
                <span
                  className="font-mono font-bold text-lg tabular-nums"
                  style={{
                    color: item.score >= 8 ? 'var(--low)' : item.score >= 5 ? 'var(--medium)' : 'var(--text-tertiary)',
                  }}
                >
                  {item.score.toFixed(1)}
                </span>
              </div>

              {/* Complexity Dot */}
              <div
                className={clsx('rounded-full', COMPLEXITY_SIZE[item.complexity])}
                style={{ backgroundColor: COMPLEXITY_COLOR[item.complexity] }}
                title={`Complexity: ${item.complexity}`}
              />

              {/* Arrow */}
              <ChevronRight className="w-5 h-5 text-[var(--text-tertiary)] opacity-0 group-hover:opacity-100 transition-opacity" />
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
