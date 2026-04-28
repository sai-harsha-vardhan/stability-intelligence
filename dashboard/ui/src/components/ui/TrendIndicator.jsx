import React from 'react';
import PropTypes from 'prop-types';
import { clsx } from 'clsx';

/**
 * TrendIndicator Component
 * Renders coloured arrow + frequency count for pattern trends
 *
 * Props:
 *   - trend: 'worsening' | 'stable' | 'improving'
 *   - value: number (frequency count)
 *   - showLabel: boolean
 */

const TREND_CONFIG = {
  worsening: {
    icon: '↑',
    color: '#F97316',
    label: 'Worsening',
    pulse: true,
  },
  stable: {
    icon: '→',
    color: '#EAB308',
    label: 'Stable',
    pulse: false,
  },
  improving: {
    icon: '↓',
    color: '#22C55E',
    label: 'Improving',
    pulse: false,
  },
};

export function TrendIndicator({ trend, value, showLabel = true, className }) {
  const config = TREND_CONFIG[trend] || TREND_CONFIG.stable;

  return (
    <div className={clsx('flex items-center gap-2', className)}>
      <span
        className={clsx(
          'flex items-center gap-1 font-mono text-sm font-semibold',
          config.pulse && 'animate-pulse-slow'
        )}
        style={{ color: config.color }}
      >
        <span>{config.icon}</span>
        {showLabel && <span>{config.label}</span>}
      </span>
      {value !== undefined && (
        <span className="text-[var(--text-secondary)] text-sm font-mono">
          {value}
        </span>
      )}
    </div>
  );
}

TrendIndicator.propTypes = {
  trend: PropTypes.oneOf(['worsening', 'stable', 'improving']).isRequired,
  value: PropTypes.number,
  showLabel: PropTypes.bool,
  className: PropTypes.string,
};
