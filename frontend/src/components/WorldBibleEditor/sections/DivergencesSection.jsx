import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const SEVERITY_COLORS = {
  minor: 'bg-green-500/30 text-green-300 border-green-500/50',
  moderate: 'bg-yellow-500/30 text-yellow-300 border-yellow-500/50',
  major: 'bg-orange-500/30 text-orange-300 border-orange-500/50',
  critical: 'bg-red-500/30 text-red-300 border-red-500/50',
};

const STATUS_COLORS = {
  active: 'bg-purple-500/30 text-purple-300',
  resolved: 'bg-gray-500/30 text-gray-400',
  escalating: 'bg-red-500/30 text-red-300',
};

export default function DivergencesSection({ data, onSave }) {
  const [expandedId, setExpandedId] = useState(null);

  const divergences = data?.list || [];
  const butterflyEffects = data?.butterfly_effects || [];
  const stats = data?.stats || { total: 0, major: 0, minor: 0 };

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h2 className="text-lg font-bold text-white mb-2">Divergences</h2>
        <p className="text-sm text-gray-500">Track how the story diverges from canon and potential ripple effects.</p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-purple-500/10 border border-purple-500/30 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-purple-400">{stats.total || divergences.length}</div>
          <div className="text-xs text-purple-300/70">Total</div>
        </div>
        <div className="bg-orange-500/10 border border-orange-500/30 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-orange-400">{stats.major || 0}</div>
          <div className="text-xs text-orange-300/70">Major</div>
        </div>
        <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-green-400">{stats.minor || 0}</div>
          <div className="text-xs text-green-300/70">Minor</div>
        </div>
      </div>

      {/* Divergences List */}
      <div className="bg-white/5 rounded-xl p-4 border border-white/10">
        <h3 className="text-sm font-semibold text-purple-300 mb-4">
          Divergence Log ({divergences.length})
        </h3>

        {divergences.length === 0 ? (
          <p className="text-sm text-gray-600 text-center py-8">No divergences recorded</p>
        ) : (
          <div className="space-y-2">
            {divergences.map((div, idx) => (
              <div key={div.id || idx} className="bg-black/20 rounded-lg overflow-hidden">
                <button
                  onClick={() => setExpandedId(expandedId === div.id ? null : div.id)}
                  className="w-full flex items-center justify-between p-3 hover:bg-white/5 transition-colors text-left"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs text-gray-500">#{div.id || idx + 1}</span>
                      <span className="text-xs text-gray-600">|</span>
                      <span className="text-xs text-cyan-400">Ch. {div.chapter}</span>
                    </div>
                    <p className="text-sm text-gray-300 line-clamp-1">{div.what_changed}</p>
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <span className={`text-xs px-2 py-0.5 rounded border ${SEVERITY_COLORS[div.severity] || SEVERITY_COLORS.minor}`}>
                      {div.severity}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[div.status] || STATUS_COLORS.active}`}>
                      {div.status}
                    </span>
                    <svg
                      className={`w-4 h-4 text-gray-500 transition-transform ${expandedId === div.id ? 'rotate-180' : ''}`}
                      fill="none" stroke="currentColor" viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </button>

                <AnimatePresence>
                  {expandedId === div.id && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="border-t border-white/10"
                    >
                      <div className="p-4 space-y-3">
                        <div>
                          <label className="text-xs text-gray-500 block mb-1">What Changed</label>
                          <p className="text-sm text-gray-300">{div.what_changed}</p>
                        </div>

                        {div.canon_event && (
                          <div>
                            <label className="text-xs text-gray-500 block mb-1">Canon Event Affected</label>
                            <p className="text-sm text-gray-300">{div.canon_event}</p>
                          </div>
                        )}

                        {div.cause && (
                          <div>
                            <label className="text-xs text-gray-500 block mb-1">Cause</label>
                            <p className="text-sm text-gray-300">{div.cause}</p>
                          </div>
                        )}

                        {div.ripple_effects?.length > 0 && (
                          <div>
                            <label className="text-xs text-gray-500 block mb-1">Ripple Effects</label>
                            <ul className="list-disc list-inside text-sm text-gray-400 space-y-1">
                              {div.ripple_effects.map((effect, i) => (
                                <li key={i}>{effect}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {div.affected_canon_events?.length > 0 && (
                          <div>
                            <label className="text-xs text-gray-500 block mb-1">Affected Canon Events</label>
                            <div className="flex flex-wrap gap-1">
                              {div.affected_canon_events.map((event, i) => (
                                <span key={i} className="text-xs bg-red-500/20 text-red-300 px-2 py-0.5 rounded">
                                  {event}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Butterfly Effects */}
      {butterflyEffects.length > 0 && (
        <div className="bg-white/5 rounded-xl p-4 border border-white/10">
          <h3 className="text-sm font-semibold text-cyan-300 mb-4">
            Butterfly Effects ({butterflyEffects.length})
          </h3>
          <div className="space-y-2">
            {butterflyEffects.map((effect, idx) => (
              <div key={idx} className="bg-black/20 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-gray-300">{effect.prediction || effect}</span>
                  {effect.probability && (
                    <span className="text-xs text-purple-400">{effect.probability}%</span>
                  )}
                </div>
                {effect.materialized !== undefined && (
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    effect.materialized ? 'bg-green-500/30 text-green-300' : 'bg-gray-500/30 text-gray-400'
                  }`}>
                    {effect.materialized ? 'Materialized' : 'Pending'}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
