import React, { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';

/**
 * CommandPalette Component
 * Global search modal with keyboard navigation
 * 
 * Props:
 *   - isOpen: boolean
 *   - onClose: function
 *   - onSelect: function(result)
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

export function CommandPalette({ isOpen, onClose, onSelect }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [recentSearches, setRecentSearches] = useState([]);

  // Load recent searches from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('sis_recent_searches');
    if (saved) {
      try {
        setRecentSearches(JSON.parse(saved));
      } catch (e) {
        console.error('Failed to parse recent searches:', e);
      }
    }
  }, []);

  // Save recent searches
  const saveRecentSearch = useCallback((term) => {
    if (!term.trim()) return;
    const updated = [term, ...recentSearches.filter(s => s !== term)].slice(0, 5);
    setRecentSearches(updated);
    localStorage.setItem('sis_recent_searches', JSON.stringify(updated));
  }, [recentSearches]);

  // Search API
  useEffect(() => {
    if (!isOpen || !query.trim()) {
      setResults([]);
      return;
    }

    const timeoutId = setTimeout(async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/search?q=${encodeURIComponent(query)}&limit=20`);
        if (response.ok) {
          const data = await response.json();
          setResults(data.results || []);
          setSelectedIndex(0);
        }
      } catch (error) {
        console.error('Search error:', error);
        setResults([]);
      }
    }, 150);

    return () => clearTimeout(timeoutId);
  }, [isOpen, query]);

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex(prev => (prev + 1) % results.length);
          break;
        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex(prev => (prev - 1 + results.length) % results.length);
          break;
        case 'Enter':
          e.preventDefault();
          if (results[selectedIndex]) {
            handleSelect(results[selectedIndex]);
          }
          break;
        case 'Escape':
          e.preventDefault();
          onClose();
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, results, selectedIndex, onClose]);

  const handleSelect = (result) => {
    saveRecentSearch(query);
    if (onSelect) {
      onSelect(result);
    }
    onClose();
  };

  const handleRecentClick = (term) => {
    setQuery(term);
  };

  if (!isOpen) return null;

  const groupedResults = results.reduce((acc, result) => {
    const type = result.type || 'Other';
    if (!acc[type]) acc[type] = [];
    acc[type].push(result);
    return acc;
  }, {});

  const typeOrder = ['Incident', 'ActionItem', 'Strategy', 'PatternCluster'];
  const sortedGroups = typeOrder
    .filter(type => groupedResults[type])
    .map(type => ({ type, items: groupedResults[type] }));

  return (
    <div className="command-palette-overlay" onClick={onClose}>
      <div className="command-palette" onClick={e => e.stopPropagation()}>
        <div className="command-input-wrapper">
          <span className="search-icon">⌘K</span>
          <input
            type="text"
            className="command-input"
            placeholder="Search incidents, action items, strategies, clusters..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          {query && (
            <button className="clear-btn" onClick={() => setQuery('')}>
              ×
            </button>
          )}
        </div>

        <div className="command-results">
          {!query.trim() && recentSearches.length > 0 && (
            <div className="recent-searches">
              <h6>Recent Searches</h6>
              <div className="recent-list">
                {recentSearches.map((term, idx) => (
                  <button
                    key={idx}
                    className="recent-item"
                    onClick={() => handleRecentClick(term)}
                  >
                    <span className="recent-icon">🕐</span>
                    {term}
                  </button>
                ))}
              </div>
            </div>
          )}

          {query.trim() && results.length === 0 && (
            <div className="no-results">
              <p>No results found for "{query}"</p>
            </div>
          )}

          {sortedGroups.map(group => (
            <div key={group.type} className="result-group">
              <h6>{group.type.replace(/([A-Z])/g, ' $1').trim()}</h6>
              <ul className="result-list">
                {group.items.map((item, idx) => {
                  const globalIdx = results.indexOf(item);
                  return (
                    <li
                      key={item.id}
                      className={`result-item ${globalIdx === selectedIndex ? 'selected' : ''}`}
                      onClick={() => handleSelect(item)}
                      onMouseEnter={() => setSelectedIndex(globalIdx)}
                    >
                      <span className={`result-icon type-${item.type?.toLowerCase()}`}>
                        {getIconForType(item.type)}
                      </span>
                      <div className="result-content">
                        <span className="result-title">{item.title}</span>
                        {item.description && (
                          <span className="result-description">
                            {item.description.substring(0, 60)}...
                          </span>
                        )}
                      </div>
                      {item.priority_score && (
                        <span className="result-score">
                          {item.priority_score.toFixed(1)}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>

        <div className="command-footer">
          <div className="keyboard-hints">
            <span><kbd>↑↓</kbd> Navigate</span>
            <span><kbd>↵</kbd> Select</span>
            <span><kbd>Esc</kbd> Close</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function getIconForType(type) {
  const icons = {
    'Incident': '●',
    'ActionItem': '⚡',
    'Strategy': '🎯',
    'PatternCluster': '◈',
  };
  return icons[type] || '•';
}

CommandPalette.propTypes = {
  isOpen: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  onSelect: PropTypes.func,
};
