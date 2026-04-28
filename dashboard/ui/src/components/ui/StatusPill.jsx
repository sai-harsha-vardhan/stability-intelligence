import React from 'react';
import PropTypes from 'prop-types';
import { clsx } from 'clsx';

/**
 * StatusPill Component
 * Renders a small pill with coloured background + label
 *
 * Props:
 *   - status: 'open' | 'resolved' | 'worsening' | 'healthy' | 'error' | 'monitoring'
 *   - label: optional custom label (defaults to status)
 *   - size: 'sm' | 'md' (default: 'md')
 */

const STATUS_CONFIG = {
  open: {
    bg: 'rgba(59, 130, 246, 0.2)',
    color: '#3B82F6',
    label: 'Open',
  },
  resolved: {
    bg: 'rgba(34, 197, 94, 0.2)',
    color: '#22C55E',
    label: 'Resolved',
  },
  worsening: {
    bg: 'rgba(249, 115, 22, 0.2)',
    color: '#F97316',
    label: 'Worsening',
  },
  healthy: {
    bg: 'rgba(34, 197, 94, 0.2)',
    color: '#22C55E',
    label: 'Healthy',
  },
  error: {
    bg: 'rgba(255, 68, 68, 0.2)',
    color: '#FF4444',
    label: 'Error',
  },
  monitoring: {
    bg: 'rgba(100, 116, 139, 0.2)',
    color: '#8B949E',
    label: 'Monitoring',
  },
  'in-progress': {
    bg: 'rgba(234, 179, 8, 0.2)',
    color: '#EAB308',
    label: 'In Progress',
  },
  deferred: {
    bg: 'rgba(72, 79, 88, 0.2)',
    color: '#484F58',
    label: 'Deferred',
  },
  degraded: {
    bg: 'rgba(249, 115, 22, 0.2)',
    color: '#F97316',
    label: 'Degraded',
  },
};

const SIZE_CLASSES = {
  sm: 'px-1.5 py-0.5 text-[10px]',
  md: 'px-2 py-1 text-xs',
};

export function StatusPill({ status, label, size = 'md', className }) {
  const config = STATUS_CONFIG[status.toLowerCase()] || STATUS_CONFIG.open;

  return (
    <span
      className={clsx(
        'inline-flex items-center rounded font-medium uppercase tracking-wide',
        SIZE_CLASSES[size],
        className
      )}
      style={{
        backgroundColor: config.bg,
        color: config.color,
      }}
    >
      {label || config.label}
    </span>
  );
}

StatusPill.propTypes = {
  status: PropTypes.oneOf([
    'open',
    'resolved',
    'worsening',
    'healthy',
    'error',
    'monitoring',
    'in-progress',
    'deferred',
    'degraded',
  ]).isRequired,
  label: PropTypes.string,
  size: PropTypes.oneOf(['sm', 'md']),
  className: PropTypes.string,
};
