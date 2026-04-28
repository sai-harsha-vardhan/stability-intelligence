import React from 'react';
import PropTypes from 'prop-types';
import { clsx } from 'clsx';

/**
 * NodeTag Component
 * Renders a small tag coloured by node type
 *
 * Props:
 *   - label: string
 *   - type: node type string (maps to color system)
 *   - onClick: optional click handler
 */

const NODE_COLORS = {
  incident_p0: '#FF4444',
  incident_p1: '#F97316',
  incident_p2: '#EAB308',
  incident_p3: '#484F58',
  pattern: '#8B5CF6',
  root_cause: '#EC4899',
  action_open: '#3B82F6',
  action_done: '#22C55E',
  strategy: '#06B6D4',
  component: '#F0883E',
  connector: '#F59E0B',
  code: '#484F58',
};

export function NodeTag({ label, type, onClick, className }) {
  const color = NODE_COLORS[type] || NODE_COLORS.code;
  const bgColor = `${color}33`; // 20% opacity

  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 text-xs rounded cursor-default',
        onClick && 'cursor-pointer hover:opacity-80',
        className
      )}
      style={{
        backgroundColor: bgColor,
        color: color,
      }}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      {label}
    </span>
  );
}

NodeTag.propTypes = {
  label: PropTypes.string.isRequired,
  type: PropTypes.oneOf(Object.keys(NODE_COLORS)).isRequired,
  onClick: PropTypes.func,
  className: PropTypes.string,
};
