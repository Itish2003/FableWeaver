import { motion } from 'framer-motion';
import useChapterEvolution from '../../hooks/useChapterEvolution';

export default function ChapterEvolutionView({ history }) {
  const evolution = useChapterEvolution(history);

  if (!evolution || evolution.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-gray-600">No chapter data available</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="mb-4">
        <h3 className="text-sm font-bold text-white mb-1">Chapter Evolution</h3>
        <p className="text-xs text-gray-500">
          Track how the World Bible evolved across {evolution.length} chapters
        </p>
      </div>

      <div className="space-y-3">
        {evolution.map((chapter, idx) => (
          <motion.div
            key={chapter.chapterNumber}
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: idx * 0.03 }}
            className={`bg-white/5 rounded-lg border ${
              chapter.hasData ? 'border-purple-500/30' : 'border-white/10'
            } overflow-hidden`}
          >
            {/* Chapter Header */}
            <div className="flex items-center justify-between px-3 py-2 bg-black/20">
              <span className="text-sm font-semibold text-purple-300">
                Chapter {chapter.chapterNumber}
              </span>
              {chapter.changes.timeline?.chapter_end_date && (
                <span className="text-xs text-cyan-400">
                  {chapter.changes.timeline.chapter_end_date}
                </span>
              )}
            </div>

            <div className="p-3 space-y-3">
              {/* Summary */}
              {chapter.summary && (
                <p className="text-xs text-gray-400 italic line-clamp-2">
                  {chapter.summary}
                </p>
              )}

              {/* Stakes Added */}
              {chapter.changes.stakes_tracking && (
                <EvolutionSection
                  title="Stakes"
                  icon="⚡"
                  color="red"
                >
                  {chapter.changes.stakes_tracking.costs_paid?.length > 0 && (
                    <div className="mb-2">
                      <span className="text-xs text-red-400">Costs:</span>
                      <ul className="mt-1 space-y-0.5">
                        {chapter.changes.stakes_tracking.costs_paid.slice(0, 2).map((cost, i) => (
                          <li key={i} className="text-xs text-gray-400 flex items-start gap-1">
                            <span className="text-red-500">-</span>
                            {typeof cost === 'string' ? cost : cost.cost}
                          </li>
                        ))}
                        {chapter.changes.stakes_tracking.costs_paid.length > 2 && (
                          <li className="text-xs text-gray-600">
                            +{chapter.changes.stakes_tracking.costs_paid.length - 2} more
                          </li>
                        )}
                      </ul>
                    </div>
                  )}

                  {chapter.changes.stakes_tracking.near_misses?.length > 0 && (
                    <div>
                      <span className="text-xs text-yellow-400">Near Misses:</span>
                      <ul className="mt-1 space-y-0.5">
                        {chapter.changes.stakes_tracking.near_misses.slice(0, 2).map((miss, i) => (
                          <li key={i} className="text-xs text-gray-400 flex items-start gap-1">
                            <span className="text-yellow-500">!</span>
                            {typeof miss === 'string' ? miss : miss.what_almost_happened}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {Object.keys(chapter.changes.stakes_tracking.power_debt_incurred || {}).length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {Object.entries(chapter.changes.stakes_tracking.power_debt_incurred).map(([power, level]) => (
                        <span key={power} className="text-xs bg-purple-500/20 text-purple-300 px-1.5 py-0.5 rounded-full">
                          {power}: {typeof level === 'string' ? level : level.strain_level || 'used'}
                        </span>
                      ))}
                    </div>
                  )}
                </EvolutionSection>
              )}

              {/* Timeline Changes */}
              {(chapter.changes.divergences_created?.length > 0 ||
                chapter.changes.canon_events_addressed?.length > 0) && (
                <EvolutionSection
                  title="Timeline"
                  icon="📅"
                  color="cyan"
                >
                  {chapter.changes.canon_events_addressed?.length > 0 && (
                    <div className="mb-2">
                      <span className="text-xs text-green-400">Canon Events:</span>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {chapter.changes.canon_events_addressed.map((event, i) => (
                          <span key={i} className="text-xs bg-green-500/20 text-green-300 px-1.5 py-0.5 rounded-full">
                            {event}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {chapter.changes.divergences_created?.length > 0 && (
                    <div>
                      <span className="text-xs text-orange-400">Divergences:</span>
                      <ul className="mt-1 space-y-0.5">
                        {chapter.changes.divergences_created.map((div, i) => (
                          <li key={i} className="text-xs text-gray-400 flex items-start gap-1">
                            <span className="text-orange-500">→</span>
                            {div}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </EvolutionSection>
              )}

              {/* Character Voices Used */}
              {chapter.changes.character_voices_used?.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {chapter.changes.character_voices_used.map((voice, i) => (
                    <span key={i} className="text-xs bg-white/10 text-gray-400 px-1.5 py-0.5 rounded-full">
                      {voice}
                    </span>
                  ))}
                </div>
              )}

              {/* No Data State */}
              {!chapter.hasData && !chapter.summary && (
                <p className="text-xs text-gray-600 text-center py-2">
                  No structured metadata available
                </p>
              )}
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

function EvolutionSection({ title, icon, color, children }) {
  const colorClasses = {
    red: 'border-red-500/30',
    yellow: 'border-yellow-500/30',
    green: 'border-green-500/30',
    cyan: 'border-cyan-500/30',
    purple: 'border-purple-500/30',
  };

  return (
    <div className={`border-l-2 ${colorClasses[color] || colorClasses.purple} pl-2`}>
      <div className="flex items-center gap-1 mb-1">
        <span className="text-xs">{icon}</span>
        <span className="text-xs font-medium text-gray-500">{title}</span>
      </div>
      {children}
    </div>
  );
}
