import React from 'react';
import PropTypes from 'prop-types';
import { clsx } from 'clsx';

/**
 * RankChange Component
 * Renders rank change indicator (↑N green / ↓N red / NEW accent / — grey)
 *
 * Props:
 *   - change: number (positive = up, negative = down)
 *   - isNew: boolean (shows NEW instead of change)
 *   - size: 'sm' | 'md'
 */

const SIZE_CLASSES = {
  sm: 'text-xs',
  md: 'text-sm',
};

export function RankChange({ change, isNew = false, size = 'md', className }) {
  const sizeClass = SIZE_CLASSES[size];

  if (isNew) {
    return (
      <span
        className={clsx('font-mono font-semibold', sizeClass, className)}
        style={{ color: '#F0883E' }}
      >
        NEW
      </span>
    );
  }

  if (change === 0 || change === undefined || change === null) {
    return (
      <span
        className={clsx('font-mono font-semibold', sizeClass, className)}
        style={{ color: '#484F58' }}
      >
        —
      </span>
    );
  }

  const isUp = change > 0;
  const absChange = Math.abs(change);
  const color = isUp ? '#22C55E' : '#F97316';
  const arrow = isUp ? '↑' : '↓';

  return (
    <span
      className={clsx('font-mono font-semibold', sizeClass, className)}
      style={{ color }}
    >
      {arrow}{absChange}
    </span>
  );
}

RankChange.propTypes = {
  change: PropTypes.number,
  isNew: PropTypes.bool,
  size: PropTypes.oneOf(['sm', 'md']),
  className: PropTypes.string,
};
