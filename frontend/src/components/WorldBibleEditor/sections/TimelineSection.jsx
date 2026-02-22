import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import EditableField from '../EditableField';

const STATUS_COLORS = {
  upcoming: 'bg-blue-500/30 text-blue-300',
  occurred: 'bg-green-500/30 text-green-300',
  modified: 'bg-yellow-500/30 text-yellow-300',
  prevented: 'bg-red-500/30 text-red-300',
};

export default function TimelineSection({ data, onSave, worldBible }) {
  const [activeTab, setActiveTab] = useState('story');

  const storyTimeline = data || {};
  const canonTimeline = worldBible?.canon_timeline || {};

  const storyEvents = storyTimeline?.events || [];
  const canonEvents = canonTimeline?.events || [];
  const chapterDates = storyTimeline?.chapter_dates || [];

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h2 className="text-lg font-bold text-white mb-2">Timeline</h2>
        <p className="text-sm text-gray-500">Track story events and compare with canon timeline.</p>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-2 mb-6">
        <button
          onClick={() => setActiveTab('story')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'story'
              ? 'bg-purple-500/30 text-purple-300 border border-purple-500/50'
              : 'bg-white/5 text-gray-400 hover:bg-white/10'
          }`}
        >
          Story Timeline ({storyEvents.length})
        </button>
        <button
          onClick={() => setActiveTab('canon')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'canon'
              ? 'bg-cyan-500/30 text-cyan-300 border border-cyan-500/50'
              : 'bg-white/5 text-gray-400 hover:bg-white/10'
          }`}
        >
          Canon Timeline ({canonEvents.length})
        </button>
        <button
          onClick={() => setActiveTab('chapters')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            activeTab === 'chapters'
              ? 'bg-green-500/30 text-green-300 border border-green-500/50'
              : 'bg-white/5 text-gray-400 hover:bg-white/10'
          }`}
        >
          Chapter Dates ({chapterDates.length})
        </button>
      </div>

      <AnimatePresence mode="wait">
        {activeTab === 'story' && (
          <motion.div
            key="story"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="space-y-3"
          >
            {storyEvents.length === 0 ? (
              <p className="text-sm text-gray-600 text-center py-8">No story events recorded</p>
            ) : (
              storyEvents.map((event, idx) => (
                <div key={idx} className="bg-white/5 rounded-xl p-4 border border-white/10">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500">Ch. {event.chapter || '?'}</span>
                      <span className="text-xs text-gray-600">|</span>
                      <span className="text-xs text-cyan-400">{event.date || 'Unknown date'}</span>
                    </div>
                    {event.source && (
                      <span className="text-xs text-gray-600">{event.source}</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-300">{event.event}</p>
                </div>
              ))
            )}
          </motion.div>
        )}

        {activeTab === 'canon' && (
          <motion.div
            key="canon"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="space-y-3"
          >
            {/* Canon Position */}
            <div className="bg-white/5 rounded-xl p-4 border border-white/10 mb-4">
              <EditableField
                path="canon_timeline.current_position"
                value={canonTimeline?.current_position}
                onSave={onSave}
                label="Current Canon Position"
              />
            </div>

            {canonEvents.length === 0 ? (
              <p className="text-sm text-gray-600 text-center py-8">No canon events defined</p>
            ) : (
              canonEvents.map((event, idx) => (
                <div key={idx} className="bg-white/5 rounded-xl p-4 border border-white/10">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-cyan-400">{event.date || 'Unknown'}</span>
                      {event.importance && (
                        <>
                          <span className="text-xs text-gray-600">|</span>
                          <span className={`text-xs ${
                            event.importance === 'critical' ? 'text-red-400' :
                            event.importance === 'major' ? 'text-orange-400' :
                            'text-gray-400'
                          }`}>
                            {event.importance}
                          </span>
                        </>
                      )}
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[event.status] || 'bg-gray-500/30 text-gray-300'}`}>
                      {event.status || 'unknown'}
                    </span>
                  </div>
                  <p className="text-sm text-gray-300 font-medium">{event.event}</p>
                  {event.characters && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {event.characters.map((char, i) => (
                        <span key={i} className="text-xs bg-purple-500/20 text-purple-300 px-2 py-0.5 rounded">
                          {char}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </motion.div>
        )}

        {activeTab === 'chapters' && (
          <motion.div
            key="chapters"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="space-y-2"
          >
            {chapterDates.length === 0 ? (
              <p className="text-sm text-gray-600 text-center py-8">No chapter dates recorded</p>
            ) : (
              <div className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-white/10">
                      <th className="text-left text-xs text-gray-500 font-medium p-3">Chapter</th>
                      <th className="text-left text-xs text-gray-500 font-medium p-3">In-Story Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chapterDates.map((entry, idx) => (
                      <tr key={idx} className="border-b border-white/5 hover:bg-white/5">
                        <td className="p-3 text-sm text-purple-300 font-medium">
                          Chapter {entry.chapter}
                        </td>
                        <td className="p-3 text-sm text-gray-300">
                          {entry.date}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
