import React from 'react';
import PropTypes from 'prop-types';
import { clsx } from 'clsx';

/**
 * TypeBadge Component
 * Renders a monospaced caps pill badge for different entity types
 *
 * Props:
 *   - type: 'action' | 'strategy' | 'incident' | 'cluster' | 'pattern' | 'root_cause'
 *   - size: 'sm' | 'md'
 */

const TYPE_CONFIG = {
  action: {
    bg: 'rgba(59, 130, 246, 0.2)',
    color: '#3B82F6',
    label: 'ACTION',
  },
  strategy: {
    bg: 'rgba(6, 182, 212, 0.2)',
    color: '#06B6D4',
    label: 'STRATEGY',
  },
  incident: {
    bg: 'rgba(255, 68, 68, 0.2)',
    color: '#FF4444',
    label: 'INCIDENT',
  },
  cluster: {
    bg: 'rgba(139, 92, 246, 0.2)',
    color: '#8B5CF6',
    label: 'CLUSTER',
  },
  pattern: {
    bg: 'rgba(139, 92, 246, 0.2)',
    color: '#8B5CF6',
    label: 'PATTERN',
  },
  root_cause: {
    bg: 'rgba(236, 72, 153, 0.2)',
    color: '#EC4899',
    label: 'ROOT CAUSE',
  },
};

const SIZE_CLASSES = {
  sm: 'px-1.5 py-0.5 text-[9px]',
  md: 'px-2 py-1 text-[10px]',
};

export function TypeBadge({ type, size = 'md', className }) {
  const config = TYPE_CONFIG[type] || TYPE_CONFIG.action;

  return (
    <span
      className={clsx(
        'inline-block font-mono font-semibold rounded tracking-wider',
        SIZE_CLASSES[size],
        className
      )}
      style={{
        backgroundColor: config.bg,
        color: config.color,
      }}
    >
      {config.label}
    </span>
  );
}

TypeBadge.propTypes = {
  type: PropTypes.oneOf([
    'action',
    'strategy',
    'incident',
    'cluster',
    'pattern',
    'root_cause',
  ]).isRequired,
  size: PropTypes.oneOf(['sm', 'md']),
  className: PropTypes.string,
};
