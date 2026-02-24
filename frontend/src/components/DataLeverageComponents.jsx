/**
 * Data Leverage Components - Display rich metadata from World Bible
 *
 * Components:
 * 1. StakesDashboard (HIGH) - Costs, near misses, pending consequences with severity
 * 2. CanonImpactTracker (HIGH) - Divergences timeline with ripple effects
 * 3. StoryIntelligenceSidebar (MEDIUM) - Canon facts, characters, power limitations
 * 4. InteractiveTimeline (MEDIUM) - Story timeline with events
 * 5. ChoiceImpactPreview (LOW) - Hover preview of choice timeline impact
 */

import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

// ─────────────────────────────────────────────────────────────────────────────
// 1. STAKES DASHBOARD - Show costs, near misses, pending consequences
// ─────────────────────────────────────────────────────────────────────────────

const severityColors = {
  low: 'bg-blue-100 text-blue-900 border-blue-300',
  medium: 'bg-yellow-100 text-yellow-900 border-yellow-300',
  high: 'bg-orange-100 text-orange-900 border-orange-300',
  critical: 'bg-red-100 text-red-900 border-red-300',
};

const severityBadgeColors = {
  low: 'bg-blue-500',
  medium: 'bg-yellow-500',
  high: 'bg-orange-500',
  critical: 'bg-red-500',
};

function CostCard({ cost, index }) {
  const [expanded, setExpanded] = useState(false);
  const severity = cost.severity || 'medium';

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className={`p-3 rounded-lg border-2 cursor-pointer transition-colors ${severityColors[severity]}`}
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="font-semibold text-sm">Chapter {cost.chapter}</div>
          <div className="text-xs opacity-75 mt-1">{cost.cost}</div>
        </div>
        <span className={`px-2 py-1 rounded text-white text-xs font-bold ${severityBadgeColors[severity]}`}>
          {severity.toUpperCase()}
        </span>
      </div>
    </motion.div>
  );
}

function ConsequenceCard({ consequence, index, currentChapter }) {
  const [expanded, setExpanded] = useState(false);

  // Extract chapter number from due_by (e.g., "Chapter 25")
  const dueChapter = parseInt(consequence.due_by?.match(/\d+/)?.[0] || '999');
  const chaptersLeft = Math.max(0, dueChapter - (currentChapter || 0));

  const urgency = chaptersLeft < 5 ? 'critical' : chaptersLeft < 10 ? 'high' : 'normal';
  const urgencyColor = urgency === 'critical' ? 'text-red-600' : urgency === 'high' ? 'text-orange-600' : 'text-yellow-600';

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="p-3 rounded-lg border-2 border-purple-300 bg-purple-50 cursor-pointer hover:bg-purple-100 transition-colors"
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex-1">
          <div className="font-semibold text-sm">{consequence.action}</div>
          <div className="text-xs opacity-75 mt-1">{consequence.predicted_consequence}</div>
        </div>
      </div>
      <div className={`text-xs font-bold ${urgencyColor}`}>
        Due by {consequence.due_by} ({chaptersLeft} chapters away)
      </div>
    </motion.div>
  );
}

function NearMissCard({ nearMiss, index }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="p-3 rounded-lg border-2 border-green-300 bg-green-50 cursor-pointer hover:bg-green-100 transition-colors"
      onClick={() => setExpanded(!expanded)}
    >
      <div className="font-semibold text-sm text-green-900">Chapter {nearMiss.chapter}</div>
      <div className="text-xs opacity-75 mt-2">Almost: {nearMiss.what_almost_happened}</div>
      <div className="text-xs font-semibold text-green-700 mt-2">Saved by: {nearMiss.saved_by}</div>
    </motion.div>
  );
}

export function StakesDashboard({ bible, currentChapter = 0 }) {
  const stakes = bible?.stakes_tracking || bible?.stakes_and_consequences || {};
  const costsPaid = stakes.costs_paid || [];
  const nearMisses = stakes.near_misses || [];
  const pendingConsequences = stakes.pending_consequences || [];

  return (
    <div className="bg-white rounded-lg shadow-lg p-6 space-y-6">
      <h2 className="text-2xl font-bold text-gray-800">⚔️ Stakes & Consequences</h2>

      {/* Costs Paid Section */}
      <div>
        <h3 className="text-lg font-semibold text-gray-700 mb-3">
          💔 Costs Paid ({costsPaid.length})
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {costsPaid.length > 0 ? (
            costsPaid.map((cost, i) => <CostCard key={i} cost={cost} index={i} />)
          ) : (
            <div className="text-gray-500 text-sm col-span-2">No costs yet...</div>
          )}
        </div>
      </div>

      {/* Near Misses Section */}
      <div>
        <h3 className="text-lg font-semibold text-gray-700 mb-3">
          😰 Close Calls ({nearMisses.length})
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {nearMisses.length > 0 ? (
            nearMisses.map((miss, i) => <NearMissCard key={i} nearMiss={miss} index={i} />)
          ) : (
            <div className="text-gray-500 text-sm col-span-2">No close calls yet...</div>
          )}
        </div>
      </div>

      {/* Pending Consequences Section */}
      <div>
        <h3 className="text-lg font-semibold text-gray-700 mb-3">
          ⏰ Pending Consequences ({pendingConsequences.length})
        </h3>
        <div className="space-y-3">
          {pendingConsequences.length > 0 ? (
            pendingConsequences.map((cons, i) => (
              <ConsequenceCard key={i} consequence={cons} index={i} currentChapter={currentChapter} />
            ))
          ) : (
            <div className="text-gray-500 text-sm">No pending consequences yet...</div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. CANON IMPACT TRACKER - Divergences with ripple effects
// ─────────────────────────────────────────────────────────────────────────────

function DivergenceTimelineNode({ divergence, butterflyEffects, isSelected, onSelect }) {
  const relatedButterflies = butterflyEffects.filter(
    (b) => b.source_divergence === divergence.id
  );

  const severityColor =
    divergence.severity === 'major' || divergence.severity === 'critical'
      ? 'border-red-500 bg-red-50'
      : 'border-yellow-500 bg-yellow-50';

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={`border-l-4 pl-4 py-3 cursor-pointer transition-colors ${severityColor} hover:shadow-md rounded-r-lg`}
      onClick={() => onSelect(divergence.id)}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="font-semibold text-sm">
            Ch {divergence.chapter}: {divergence.what_changed}
          </div>
          <div className="text-xs text-gray-600 mt-1">Cause: {divergence.cause}</div>
        </div>
        <span className="text-xs px-2 py-1 rounded bg-gray-200 font-bold">
          {divergence.severity.toUpperCase()}
        </span>
      </div>

      {/* Related Butterfly Effects */}
      {relatedButterflies.length > 0 && (
        <div className="mt-2 pt-2 border-t border-gray-300">
          <div className="text-xs font-semibold text-purple-700 mb-1">Predicted Effects:</div>
          <div className="space-y-1">
            {relatedButterflies.map((b, i) => (
              <div key={i} className="text-xs text-gray-700">
                {b.materialized ? '✓' : '?'} {b.prediction}
                {b.probability && ` (${b.probability}%)`}
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}

export function CanonImpactTracker({ bible }) {
  const divergences = bible?.divergences || {};
  const divList = divergences.list || [];
  const butterflies = divergences.butterfly_effects || [];
  const stats = divergences.stats || { total: 0, major: 0, minor: 0 };
  const [selectedDivId, setSelectedDivId] = useState(null);

  const selectedDiv = divList.find((d) => d.id === selectedDivId) || divList[0];

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <h2 className="text-2xl font-bold text-gray-800 mb-4">◆ Canon Impact Timeline</h2>

      {/* Stats Bar */}
      <div className="grid grid-cols-3 gap-4 mb-6 p-4 bg-gray-50 rounded-lg">
        <div className="text-center">
          <div className="text-2xl font-bold text-gray-800">{stats.total}</div>
          <div className="text-xs text-gray-600">Total Divergences</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-red-600">{stats.major}</div>
          <div className="text-xs text-gray-600">Major Impact</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-yellow-600">{stats.minor}</div>
          <div className="text-xs text-gray-600">Minor Impact</div>
        </div>
      </div>

      {/* Timeline */}
      <div className="space-y-2 mb-6 max-h-96 overflow-y-auto">
        {divList.length > 0 ? (
          divList.map((div, i) => (
            <DivergenceTimelineNode
              key={div.id}
              divergence={div}
              butterflyEffects={butterflies}
              isSelected={selectedDivId === div.id}
              onSelect={setSelectedDivId}
            />
          ))
        ) : (
          <div className="text-gray-500 text-sm">No divergences recorded yet...</div>
        )}
      </div>

      {/* Detailed View */}
      {selectedDiv && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="border-2 border-blue-300 rounded-lg p-4 bg-blue-50"
        >
          <h3 className="font-bold text-gray-800 mb-3">Impact Details: {selectedDiv.id}</h3>

          {/* Ripple Effects */}
          {selectedDiv.ripple_effects && selectedDiv.ripple_effects.length > 0 && (
            <div className="mb-3">
              <div className="text-sm font-semibold text-gray-700 mb-2">Ripple Effects:</div>
              <ul className="text-sm space-y-1">
                {selectedDiv.ripple_effects.map((effect, i) => (
                  <li key={i} className="text-gray-700">
                    • {typeof effect === 'string' ? effect : effect.effect || 'Effect recorded'}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Affected Canon Events */}
          {selectedDiv.affected_canon_events && selectedDiv.affected_canon_events.length > 0 && (
            <div>
              <div className="text-sm font-semibold text-gray-700 mb-2">Affected Canon Events:</div>
              <ul className="text-sm space-y-1">
                {selectedDiv.affected_canon_events.map((event, i) => (
                  <li key={i} className="text-gray-700">
                    • {event}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. STORY INTELLIGENCE SIDEBAR - Canon used, characters, power limitations
// ─────────────────────────────────────────────────────────────────────────────

export function StoryIntelligenceSidebar({ chapterMetadata }) {
  if (!chapterMetadata) return null;

  const canonElements = chapterMetadata.canon_elements_used || [];
  const characters = chapterMetadata.character_voices_used || [];
  const powerLimitations = chapterMetadata.power_limitations_shown || [];

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      className="bg-gradient-to-b from-indigo-50 to-blue-50 rounded-lg shadow-lg p-4 space-y-4"
    >
      <h3 className="text-lg font-bold text-indigo-900">📚 Chapter Intelligence</h3>

      {/* Canon Used */}
      {canonElements.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-indigo-700 mb-2">Canon References ({canonElements.length})</h4>
          <div className="space-y-1">
            {canonElements.map((elem, i) => (
              <div key={i} className="text-xs bg-white rounded px-2 py-1 text-gray-700">
                📖 {elem}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Characters */}
      {characters.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-indigo-700 mb-2">Characters Spoken ({characters.length})</h4>
          <div className="space-y-1">
            {characters.map((char, i) => (
              <div key={i} className="text-xs bg-white rounded px-2 py-1 text-gray-700">
                🎭 {char}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Power Limitations */}
      {powerLimitations.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-indigo-700 mb-2">Power Limitations Shown</h4>
          <div className="space-y-1">
            {powerLimitations.map((limit, i) => (
              <div key={i} className="text-xs bg-white rounded px-2 py-1 text-gray-700">
                ⚡ {limit}
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. INTERACTIVE TIMELINE - Story timeline with events
// ─────────────────────────────────────────────────────────────────────────────

export function InteractiveTimeline({ timeline }) {
  const events = timeline?.events || [];
  const chapterDates = timeline?.chapter_dates || [];
  const [hoveredIndex, setHoveredIndex] = useState(null);

  if (events.length === 0 && chapterDates.length === 0) {
    return <div className="text-gray-500 text-sm">No timeline events yet...</div>;
  }

  return (
    <div className="bg-white rounded-lg shadow-lg p-6">
      <h2 className="text-2xl font-bold text-gray-800 mb-6">📅 Story Timeline</h2>

      {/* Chapter Timeline */}
      {chapterDates.length > 0 && (
        <div className="mb-8">
          <h3 className="text-lg font-semibold text-gray-700 mb-4">Chapters</h3>
          <div className="flex items-center gap-2 overflow-x-auto pb-4">
            {chapterDates.map((cd, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                className="flex-shrink-0 text-center"
              >
                <div className="bg-blue-100 rounded-lg px-3 py-2 border-2 border-blue-300">
                  <div className="font-bold text-sm text-blue-900">Ch {cd.chapter}</div>
                  <div className="text-xs text-blue-700 whitespace-nowrap">{cd.date}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      )}

      {/* Events Timeline */}
      {events.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-gray-700 mb-4">Events</h3>
          <div className="space-y-3">
            {events.map((event, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className="flex gap-4 p-3 rounded-lg border-l-4 border-purple-500 bg-purple-50 hover:bg-purple-100 transition-colors"
                onMouseEnter={() => setHoveredIndex(i)}
                onMouseLeave={() => setHoveredIndex(null)}
              >
                <div className="flex-shrink-0 text-purple-700 font-bold">📌</div>
                <div className="flex-1">
                  <div className="font-semibold text-sm text-gray-800">{event.event}</div>
                  <div className="text-xs text-gray-600 mt-1">
                    {event.date}{event.chapter && ` • Ch ${event.chapter}`}
                    {event.type && ` • [${event.type}]`}
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. CHOICE IMPACT PREVIEW - Show timeline impact on hover
// ─────────────────────────────────────────────────────────────────────────────

export function ChoiceWithImpactPreview({ choice, choiceIndex, timelineNotes }) {
  const [showPreview, setShowPreview] = useState(false);
  const impact = timelineNotes?.[`choice_${choiceIndex}`] || timelineNotes?.choices?.[choiceIndex];

  return (
    <div className="relative">
      <motion.button
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        onMouseEnter={() => setShowPreview(true)}
        onMouseLeave={() => setShowPreview(false)}
        className="w-full text-left px-4 py-3 rounded-lg border-2 border-blue-500 bg-blue-50 hover:bg-blue-100 transition-colors text-gray-800 font-semibold"
      >
        {choiceIndex + 1}. {choice}
      </motion.button>

      {/* Impact Preview Tooltip */}
      <AnimatePresence>
        {showPreview && impact && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="absolute top-full mt-2 left-0 right-0 bg-yellow-50 border-2 border-yellow-400 rounded-lg p-3 z-10 shadow-lg"
          >
            <div className="text-xs font-semibold text-yellow-900 mb-1">Impact Preview:</div>
            <div className="text-xs text-yellow-800">{impact}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default {
  StakesDashboard,
  CanonImpactTracker,
  StoryIntelligenceSidebar,
  InteractiveTimeline,
  ChoiceWithImpactPreview,
};
