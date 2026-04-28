import React, { useState } from 'react';
import { Topbar } from './Topbar';
import { Sidebar } from './Sidebar';
import { CommandPalette } from '../ui/CommandPalette';
import { clsx } from 'clsx';

/**
 * MainLayout Component
 * Overall application layout shell with topbar, sidebar, and content area
 *
 * Props:
 *   - children: ReactNode
 *   - activeSection: string
 *   - onNavigate: (section) => void
 *   - systemStats: object
 */

export function MainLayout({ children, activeSection, onNavigate, systemStats }) {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[var(--bg-base)]">
      {/* Topbar */}
      <Topbar
        onSearchOpen={() => setIsSearchOpen(true)}
        systemStats={systemStats}
      />

      {/* Sidebar */}
      <Sidebar
        activeSection={activeSection}
        onNavigate={onNavigate}
        isCollapsed={isSidebarCollapsed}
        onToggle={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
      />

      {/* Main Content */}
      <main
        className={clsx(
          'pt-[var(--topbar-height)] transition-all duration-200 min-h-screen',
          isSidebarCollapsed
            ? 'pl-[var(--sidebar-collapsed-width)]'
            : 'pl-[var(--sidebar-width)]'
        )}
      >
        <div className="max-w-[var(--content-max-width)] mx-auto p-6">
          {children}
        </div>
      </main>

      {/* Command Palette */}
      <CommandPalette
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
        onSelect={(item) => {
          console.log('Selected:', item);
        }}
      />
    </div>
  );
}
