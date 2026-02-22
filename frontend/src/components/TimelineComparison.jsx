import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const API_BASE = 'http://localhost:8000';

// Status icons and colors
const STATUS_CONFIG = {
  matched: { icon: '✓', color: '#22c55e', bg: '#14532d', label: 'Matched' },
  modified: { icon: '~', color: '#eab308', bg: '#422006', label: 'Modified' },
  prevented: { icon: '✗', color: '#ef4444', bg: '#450a0a', label: 'Prevented' },
  upcoming: { icon: '→', color: '#a78bfa', bg: '#2e1065', label: 'Upcoming' },
  unaddressed: { icon: '?', color: '#9ca3af', bg: '#1f2937', label: 'Unaddressed' },
  story_only: { icon: '★', color: '#06b6d4', bg: '#083344', label: 'Story Only' },
};

function EventCard({ event, status, showStoryMatch = false }) {
  const config = STATUS_CONFIG[status];
  const isMajor = event.importance === 'major';

  return (
    <div
      className="p-3 rounded-lg border mb-2 transition-all hover:scale-[1.01]"
      style={{
        borderColor: config.color + '40',
        backgroundColor: config.bg + '60',
      }}
    >
      <div className="flex items-start gap-2">
        <span
          className="text-lg font-bold flex-shrink-0 w-6 text-center"
          style={{ color: config.color }}
        >
          {config.icon}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-400 font-mono">[{event.date}]</span>
            {isMajor && <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-900/50 text-yellow-400 font-bold">MAJOR</span>}
          </div>
          <p className={`text-sm mt-1 ${isMajor ? 'font-semibold text-white' : 'text-gray-300'}`}>
            {event.event}
          </p>
          {event.characters && event.characters.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-2">
              {event.characters.slice(0, 5).map((char, i) => (
                <span key={i} className="text-xs px-1.5 py-0.5 rounded bg-gray-800 text-gray-400">
                  {char}
                </span>
              ))}
              {event.characters.length > 5 && (
                <span className="text-xs text-gray-500">+{event.characters.length - 5}</span>
              )}
            </div>
          )}
          {showStoryMatch && event.story_match && (
            <div className="mt-2 pl-3 border-l-2 border-cyan-600">
              <span className="text-xs text-cyan-400">Story Version:</span>
              <p className="text-sm text-cyan-200">{event.story_match}</p>
              {event.story_date && (
                <span className="text-xs text-gray-500">[{event.story_date}]</span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatsBar({ stats }) {
  const total = stats.total_canon || 1;
  const bars = [
    { key: 'matched', value: stats.matched, color: '#22c55e' },
    { key: 'modified', value: stats.modified, color: '#eab308' },
    { key: 'prevented', value: stats.prevented, color: '#ef4444' },
    { key: 'upcoming', value: stats.upcoming, color: '#a78bfa' },
    { key: 'unaddressed', value: stats.unaddressed, color: '#9ca3af' },
  ];

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-400">Canon Event Status</span>
        <span className="text-sm font-mono">
          <span className="text-gray-400">Divergence:</span>{' '}
          <span
            className={`font-bold ${
              stats.divergence_pct > 50 ? 'text-red-400' :
              stats.divergence_pct > 25 ? 'text-yellow-400' :
              'text-green-400'
            }`}
          >
            {stats.divergence_pct}%
          </span>
        </span>
      </div>
      <div className="h-3 bg-gray-800 rounded-full overflow-hidden flex">
        {bars.map(bar => {
          const pct = (bar.value / total) * 100;
          if (pct === 0) return null;
          return (
            <motion.div
              key={bar.key}
              initial={{ width: 0 }}
              animate={{ width: `${pct}%` }}
              transition={{ duration: 0.5, delay: 0.1 }}
              style={{ backgroundColor: bar.color }}
              className="h-full"
              title={`${STATUS_CONFIG[bar.key].label}: ${bar.value}`}
            />
          );
        })}
      </div>
      <div className="flex flex-wrap gap-4 mt-2 text-xs">
        {bars.map(bar => (
          <div key={bar.key} className="flex items-center gap-1">
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: bar.color }}
            />
            <span className="text-gray-400">{STATUS_CONFIG[bar.key].label}:</span>
            <span className="font-mono text-white">{bar.value}</span>
          </div>
        ))}
        {stats.story_only > 0 && (
          <div className="flex items-center gap-1">
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: '#06b6d4' }}
            />
            <span className="text-gray-400">Story Only:</span>
            <span className="font-mono text-white">{stats.story_only}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function DivergenceList({ divergences }) {
  if (!divergences || divergences.length === 0) return null;

  return (
    <div className="mb-4 p-3 rounded-lg bg-red-950/30 border border-red-900/50">
      <h4 className="text-sm font-semibold text-red-400 mb-2">Recent Divergences</h4>
      {divergences.map((div, i) => (
        <div key={i} className="text-sm mb-2 last:mb-0">
          <div className="flex items-start gap-2">
            <span className="text-red-400">✗</span>
            <div>
              <span className="text-gray-400 line-through">{div.canon_event}</span>
              <span className="text-gray-500 mx-2">→</span>
              <span className="text-cyan-300">{div.what_changed}</span>
            </div>
          </div>
          {div.cause && (
            <p className="text-xs text-gray-500 ml-5 mt-1">Cause: {div.cause}</p>
          )}
        </div>
      ))}
    </div>
  );
}

export default function TimelineComparison({ storyId }) {
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all'); // all, matched, modified, prevented, upcoming, story_only

  useEffect(() => {
    if (!storyId) return;

    const fetchComparison = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/stories/${storyId}/timeline-comparison`);
        if (!res.ok) throw new Error('Failed to fetch comparison');
        const data = await res.json();
        setComparison(data);
        setError(null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchComparison();
  }, [storyId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-violet-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-950/30 border border-red-900/50 rounded-lg text-red-400">
        Error loading timeline comparison: {error}
      </div>
    );
  }

  if (!comparison) return null;

  const filterOptions = [
    { key: 'all', label: 'All Events' },
    { key: 'matched', label: 'Matched' },
    { key: 'modified', label: 'Modified' },
    { key: 'prevented', label: 'Prevented' },
    { key: 'upcoming', label: 'Upcoming' },
    { key: 'story_only', label: 'Story Only' },
  ];

  // Determine which events to show based on filter
  const getFilteredEvents = () => {
    if (filter === 'all') {
      // Show all in chronological order by category
      const allEvents = [
        ...comparison.matched.map(e => ({ ...e, _status: 'matched' })),
        ...comparison.modified.map(e => ({ ...e, _status: 'modified' })),
        ...comparison.prevented.map(e => ({ ...e, _status: 'prevented' })),
        ...comparison.upcoming.map(e => ({ ...e, _status: 'upcoming' })),
        ...comparison.unaddressed.map(e => ({ ...e, _status: 'unaddressed' })),
        ...comparison.story_only.map(e => ({ ...e, _status: 'story_only' })),
      ];
      return allEvents;
    }
    return (comparison[filter] || []).map(e => ({ ...e, _status: filter }));
  };

  const events = getFilteredEvents();

  return (
    <div className="p-4">
      {/* Header */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-lg font-bold text-white">Canon vs Story Timeline</h3>
          <span className="text-sm text-gray-400 font-mono">
            Story Date: <span className="text-violet-400">{comparison.current_date}</span>
          </span>
        </div>
        <StatsBar stats={comparison.stats} />
      </div>

      {/* Divergences */}
      <DivergenceList divergences={comparison.divergences} />

      {/* Filter tabs */}
      <div className="flex flex-wrap gap-2 mb-4">
        {filterOptions.map(opt => {
          const count = opt.key === 'all'
            ? events.length
            : (comparison[opt.key]?.length || 0);

          return (
            <button
              key={opt.key}
              onClick={() => setFilter(opt.key)}
              className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
                filter === opt.key
                  ? 'bg-violet-600 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}
            >
              {opt.label} ({count})
            </button>
          );
        })}
      </div>

      {/* Events list */}
      <div className="space-y-1">
        <AnimatePresence mode="popLayout">
          {events.length > 0 ? (
            events.map((event, i) => (
              <motion.div
                key={`${event._status}-${event.event}-${i}`}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2, delay: i * 0.02 }}
              >
                <EventCard
                  event={event}
                  status={event._status}
                  showStoryMatch={event._status === 'modified'}
                />
              </motion.div>
            ))
          ) : (
            <div className="text-center text-gray-500 py-8">
              No events in this category
            </div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
