import React from 'react';
import PropTypes from 'prop-types';
import { clsx } from 'clsx';

/**
 * PriorityScore Component
 * Renders a large monospaced number coloured by value
 * with optional progress bar
 *
 * Props:
 *   - score: number (0-10)
 *   - showBar: boolean (default: false)
 *   - size: 'sm' | 'md' | 'lg'
 */

const getScoreColor = (score) => {
  if (score >= 8) return '#22C55E'; // Green
  if (score >= 5) return '#EAB308'; // Yellow
  return '#484F58'; // Grey
};

const SIZE_CLASSES = {
  sm: {
    value: 'text-xl',
    label: 'text-[10px]',
    bar: 'w-16',
  },
  md: {
    value: 'text-2xl',
    label: 'text-xs',
    bar: 'w-20',
  },
  lg: {
    value: 'text-3xl',
    label: 'text-sm',
    bar: 'w-24',
  },
};

export function PriorityScore({ score, showBar = false, size = 'md', className }) {
  const color = getScoreColor(score);
  const sizeClasses = SIZE_CLASSES[size];

  return (
    <div className={clsx('flex flex-col items-end gap-1', className)}>
      <span
        className={clsx('font-mono font-bold tabular-nums leading-none', sizeClasses.value)}
        style={{ color }}
      >
        {score.toFixed(1)}
      </span>
      <span className={clsx('text-[var(--text-muted)] uppercase tracking-wide', sizeClasses.label)}>
        Score
      </span>
      {showBar && (
        <div
          className={clsx('h-1 bg-[var(--bg-overlay)] rounded-full mt-1', sizeClasses.bar)}
        >
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{ width: `${(score / 10) * 100}%`, backgroundColor: color }}
          />
        </div>
      )}
    </div>
  );
}

PriorityScore.propTypes = {
  score: PropTypes.number.isRequired,
  showBar: PropTypes.bool,
  size: PropTypes.oneOf(['sm', 'md', 'lg']),
  className: PropTypes.string,
};
