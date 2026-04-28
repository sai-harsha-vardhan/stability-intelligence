import React from 'react';
import PropTypes from 'prop-types';
import { clsx } from 'clsx';

/**
 * Skeleton Component
 * Shimmer loading placeholder for various shapes
 *
 * Props:
 *   - width: string | number (default: '100%')
 *   - height: string | number (default: '16px')
 *   - variant: 'text' | 'rect' | 'circle'
 *   - className: string
 */

const VARIANT_CLASSES = {
  text: '',
  rect: '',
  circle: 'rounded-full',
};

export function Skeleton({
  width = '100%',
  height = '16px',
  variant = 'rect',
  className,
}) {
  const widthStyle = typeof width === 'number' ? `${width}px` : width;
  const heightStyle = typeof height === 'number' ? `${height}px` : height;

  return (
    <div
      className={clsx(
        'shimmer',
        VARIANT_CLASSES[variant],
        className
      )}
      style={{
        width: widthStyle,
        height: heightStyle,
        backgroundColor: 'var(--bg-surface)',
        borderRadius: variant === 'circle' ? '50%' : 'var(--radius-md)',
      }}
    />
  );
}

Skeleton.propTypes = {
  width: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  height: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
  variant: PropTypes.oneOf(['text', 'rect', 'circle']),
  className: PropTypes.string,
};

/**
 * SkeletonCard - Pre-built skeleton for cards
 */
export function SkeletonCard({ lines = 3, className }) {
  return (
    <div
      className={clsx('p-4 space-y-3', className)}
      style={{ backgroundColor: 'var(--bg-surface)', borderRadius: 'var(--radius-lg)' }}
    >
      <Skeleton width="60%" height="20px" variant="rect" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} width={i === lines - 1 ? '80%' : '100%'} height="14px" variant="rect" />
      ))}
    </div>
  );
}

SkeletonCard.propTypes = {
  lines: PropTypes.number,
  className: PropTypes.string,
};
