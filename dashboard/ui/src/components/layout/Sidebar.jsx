import React from 'react';
import { clsx } from 'clsx';
import {
  LayoutDashboard,
  Network,
  Target,
  Layers,
  TrendingUp,
  Bot,
  Activity,
  HeartPulse,
  ChevronLeft,
} from 'lucide-react';

/**
 * Sidebar Component
 * Collapsible navigation sidebar with icons and badge counts
 *
 * Props:
 *   - activeSection: string
 *   - onNavigate: (section) => void
 *   - isCollapsed: boolean
 *   - onToggle: () => void
 *   - counts: object with badge counts
 */

const NAV_ITEMS = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard, badge: null },
  { id: 'graph', label: 'Graph', icon: Network, badge: null },
  { id: 'priorities', label: 'Priorities', icon: Target, badge: 'openItems' },
  { id: 'patterns', label: 'Patterns', icon: Layers, badge: 'worsening' },
  { id: 'progress', label: 'Progress', icon: TrendingUp, badge: 'resolved' },
  { id: 'agents', label: 'Agents', icon: Bot, badge: 'errors' },
  { id: 'feed', label: 'Feed', icon: Activity, badge: 'newEvents' },
  { id: 'health', label: 'Health', icon: HeartPulse, badge: null },
];

const MOCK_COUNTS = {
  openItems: 12,
  worsening: 3,
  resolved: 8,
  errors: 0,
  newEvents: 5,
};

export function Sidebar({
  activeSection,
  onNavigate,
  isCollapsed = false,
  onToggle,
  counts = MOCK_COUNTS,
}) {
  return (
    <aside
      className={clsx(
        'fixed left-0 top-[var(--topbar-height)] bottom-0 bg-[var(--bg-surface)] border-r border-[var(--bg-overlay)] z-30 transition-all duration-200',
        isCollapsed ? 'w-[var(--sidebar-collapsed-width)]' : 'w-[var(--sidebar-width)]'
      )}
    >
      <nav className="flex flex-col h-full">
        {/* Navigation Items */}
        <div className="flex-1 py-3 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeSection === item.id;
            const badgeCount = counts[item.badge];
            const hasBadge = badgeCount !== undefined && badgeCount > 0;

            return (
              <button
                key={item.id}
                onClick={() => onNavigate(item.id)}
                className={clsx(
                  'w-full flex items-center px-3 py-2.5 text-sm transition-all duration-120 group relative',
                  isActive
                    ? 'text-[var(--accent)] bg-[var(--bg-elevated)] border-l-2 border-[var(--accent)]'
                    : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]/50'
                )}
              >
                <Icon className={clsx('w-5 h-5 flex-shrink-0', isCollapsed && 'mx-auto')} />
                {!isCollapsed && (
                  <>
                    <span className="ml-3 flex-1 text-left">{item.label}</span>
                    {hasBadge && (
                      <span className={clsx(
                        'ml-2 px-1.5 py-0.5 text-[10px] font-mono font-semibold rounded',
                        item.badge === 'errors' || item.badge === 'worsening'
                          ? 'bg-[var(--critical)]/20 text-[var(--critical)]'
                          : 'bg-[var(--bg-overlay)] text-[var(--text-secondary)]'
                      )}>
                        {badgeCount}
                      </span>
                    )}
                  </>
                )}
                {isCollapsed && hasBadge && (
                  <span className="absolute top-1 right-1 w-2 h-2 bg-[var(--critical)] rounded-full" />
                )}
              </button>
            );
          })}
        </div>

        {/* Collapse Toggle */}
        <div className="p-2 border-t border-[var(--bg-overlay)]">
          <button
            onClick={onToggle}
            className="w-full flex items-center justify-center px-2 py-2 text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)] rounded transition-colors"
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <ChevronLeft
              className={clsx(
                'w-5 h-5 transition-transform duration-200',
                isCollapsed && 'rotate-180'
              )}
            />
          </button>
        </div>
      </nav>
    </aside>
  );
}
