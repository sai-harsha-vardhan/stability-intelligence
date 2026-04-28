import React from 'react';
import PropTypes from 'prop-types';
import { clsx } from 'clsx';

/**
 * AgentStatusDot Component
 * Renders a coloured dot, pulsing animation if running
 *
 * Props:
 *   - status: 'running' | 'idle' | 'warning' | 'error'
 *   - size: 'sm' | 'md' | 'lg'
 *   - showLabel: boolean
 */

const STATUS_CONFIG = {
  running: {
    color: '#22C55E',
    label: 'Running',
    pulse: true,
  },
  idle: {
    color: '#22C55E',
    label: 'Idle',
    pulse: false,
  },
  warning: {
    color: '#EAB308',
    label: 'Warning',
    pulse: false,
  },
  error: {
    color: '#FF4444',
    label: 'Error',
    pulse: false,
  },
};

const SIZE_CLASSES = {
  sm: 'w-2 h-2',
  md: 'w-3 h-3',
  lg: 'w-4 h-4',
};

export function AgentStatusDot({ status, size = 'md', showLabel = false, className }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.idle;

  return (
    <div className={clsx('flex items-center gap-2', className)}>
      <span
        className={clsx(
          'rounded-full',
          SIZE_CLASSES[size],
          config.pulse && 'animate-pulse-slow'
        )}
        style={{ backgroundColor: config.color }}
      />
      {showLabel && (
        <span className="text-sm text-[var(--text-secondary)]">{config.label}</span>
      )}
    </div>
  );
}

AgentStatusDot.propTypes = {
  status: PropTypes.oneOf(['running', 'idle', 'warning', 'error']).isRequired,
  size: PropTypes.oneOf(['sm', 'md', 'lg']),
  showLabel: PropTypes.bool,
  className: PropTypes.string,
};
