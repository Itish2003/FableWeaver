/**
 * Data Leverage Components - Display rich metadata from World Bible
 *
 * Aligned with existing component patterns:
 * - Severity colors: green (low), yellow (medium), orange (high), red (critical)
 * - Typography: text-lg white headers with colored dot indicators
 * - Cards: Better visual hierarchy with grouped metadata
 * - Animation: 0.2s duration + 2ms stagger (consistent with TimelineComparison)
 * - Empty states: Formal tone without ellipsis
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
// Color System - Aligned with existing patterns
// ─────────────────────────────────────────────────────────────────────────────

const severityColors = {
  low: 'bg-green-500/15 text-green-300 border-green-500/40',
  minor: 'bg-green-500/15 text-green-300 border-green-500/40',
  moderate: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/40',
  medium: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/40',
  high: 'bg-orange-500/15 text-orange-300 border-orange-500/40',
  major: 'bg-orange-500/15 text-orange-300 border-orange-500/40',
  critical: 'bg-red-500/15 text-red-300 border-red-500/40',
};

const severityDotColors = {
  low: 'bg-green-500',
  minor: 'bg-green-500',
  moderate: 'bg-yellow-500',
  medium: 'bg-yellow-500',
  high: 'bg-orange-500',
  major: 'bg-orange-500',
  critical: 'bg-red-500',
};

const severityTextColors = {
  low: 'text-green-300',
  minor: 'text-green-300',
  moderate: 'text-yellow-300',
  medium: 'text-yellow-300',
  high: 'text-orange-300',
  major: 'text-orange-300',
  critical: 'text-red-300',
};

// ─────────────────────────────────────────────────────────────────────────────
// 1. STAKES DASHBOARD
// ─────────────────────────────────────────────────────────────────────────────

function CostCard({ cost, index }) {
  const severity = cost.severity || 'moderate';

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: index * 0.02 }}
      className={`p-3 rounded-lg border cursor-pointer hover:bg-white/5 transition-colors ${severityColors[severity]}`}
    >
      <div className="flex items-start gap-2">
        <span className={`w-2 h-2 rounded-full ${severityDotColors[severity]} flex-shrink-0 mt-1`}></span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-500 font-mono">[Ch {cost.chapter}]</span>
            <span className={`text-xs px-1.5 py-0.5 rounded-full font-bold ${severityColors[severity]}`}>
              {severity.toUpperCase()}
            </span>
          </div>
          <p className="text-sm mt-1 text-gray-200">{cost.cost}</p>
        </div>
      </div>
    </motion.div>
  );
}

function NearMissCard({ nearMiss, index }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: index * 0.02 }}
      className="p-3 rounded-lg border border-green-500/40 bg-green-500/10 cursor-pointer hover:bg-green-500/20 transition-colors"
    >
      <div className="flex items-start gap-2">
        <span className="w-2 h-2 rounded-full bg-green-500 flex-shrink-0 mt-1"></span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 font-mono">[Ch {nearMiss.chapter}]</span>
            <span className="text-xs px-1.5 py-0.5 rounded-full bg-green-500/30 text-green-300 font-bold">SAVED</span>
          </div>
          <p className="text-sm mt-1 text-gray-200">Almost: {nearMiss.what_almost_happened}</p>
          <p className="text-xs mt-1 text-green-400 font-semibold">Saved by: {nearMiss.saved_by}</p>
        </div>
      </div>
    </motion.div>
  );
}

function ConsequenceCard({ consequence, index, currentChapter }) {
  // Extract chapter number from due_by (e.g., "Chapter 25")
  const dueChapter = parseInt(consequence.due_by?.match(/\d+/)?.[0] || '999');
  const chaptersLeft = Math.max(0, dueChapter - (currentChapter || 0));

  const urgency = chaptersLeft < 5 ? 'critical' : chaptersLeft < 10 ? 'high' : 'moderate';
  const urgencySeverity = urgency === 'critical' ? 'critical' : urgency === 'high' ? 'high' : 'moderate';

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: index * 0.02 }}
      className={`p-3 rounded-lg border cursor-pointer hover:bg-white/5 transition-colors ${severityColors[urgencySeverity]}`}
    >
      <div className="flex items-start gap-2">
        <span className={`w-2 h-2 rounded-full ${severityDotColors[urgencySeverity]} flex-shrink-0 mt-1`}></span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-500 font-mono">[Due: {consequence.due_by}]</span>
            <span className={`text-xs px-1.5 py-0.5 rounded-full font-bold ${severityColors[urgencySeverity]}`}>
              {chaptersLeft} CHAPTERS
            </span>
          </div>
          <p className="text-sm mt-1 text-gray-200 font-semibold">{consequence.action}</p>
          <p className="text-xs mt-1 text-gray-400">{consequence.predicted_consequence}</p>
        </div>
      </div>
    </motion.div>
  );
}

export function StakesDashboard({ bible, currentChapter = 0 }) {
  const stakes = bible?.stakes_tracking || bible?.stakes_and_consequences || {};
  const costsPaid = stakes.costs_paid || [];
  const nearMisses = stakes.near_misses || [];
  const pendingConsequences = stakes.pending_consequences || [];

  return (
    <div className="bg-white/5 rounded-lg border border-white/10 p-6 space-y-6">
      <h2 className="text-lg font-bold text-white">Stakes & Consequences</h2>

      {/* Costs Paid */}
      <div>
        <h3 className="text-sm font-semibold text-red-300 mb-4">
          Costs Paid ({costsPaid.length})
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {costsPaid.length > 0 ? (
            costsPaid.map((cost, i) => <CostCard key={i} cost={cost} index={i} />)
          ) : (
            <p className="text-sm text-gray-500 col-span-2">No costs recorded yet.</p>
          )}
        </div>
      </div>

      {/* Near Misses */}
      <div>
        <h3 className="text-sm font-semibold text-yellow-300 mb-4">
          Close Calls ({nearMisses.length})
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {nearMisses.length > 0 ? (
            nearMisses.map((miss, i) => <NearMissCard key={i} nearMiss={miss} index={i} />)
          ) : (
            <p className="text-sm text-gray-500 col-span-2">No close calls recorded.</p>
          )}
        </div>
      </div>

      {/* Pending Consequences */}
      <div>
        <h3 className="text-sm font-semibold text-purple-300 mb-4">
          Pending Consequences ({pendingConsequences.length})
        </h3>
        <div className="space-y-3">
          {pendingConsequences.length > 0 ? (
            pendingConsequences.map((cons, i) => (
              <ConsequenceCard key={i} consequence={cons} index={i} currentChapter={currentChapter} />
            ))
          ) : (
            <p className="text-sm text-gray-500">No pending consequences.</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. CANON IMPACT TRACKER
// ─────────────────────────────────────────────────────────────────────────────

function DivergenceTimelineNode({ divergence, butterflyEffects, isSelected, onSelect }) {
  const relatedButterflies = butterflyEffects.filter(
    (b) => b.source_divergence === divergence.id
  );

  const severity = divergence.severity || 'major';
  const severityColor = severity === 'critical' || severity === 'major'
    ? 'border-red-500/70 bg-red-500/10'
    : 'border-yellow-500/70 bg-yellow-500/10';

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={`border-l-4 pl-4 py-3 cursor-pointer transition-colors ${severityColor} hover:bg-white/5 rounded-r-lg`}
      onClick={() => onSelect(divergence.id)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-gray-500 font-mono">[Ch {divergence.chapter}]</span>
            <span className="text-xs px-1.5 py-0.5 rounded-full font-bold bg-white/10 text-gray-300">
              {severity.toUpperCase()}
            </span>
          </div>
          <p className="text-sm mt-1 text-gray-200 font-semibold">{divergence.what_changed}</p>
          <p className="text-xs mt-1 text-gray-400">Cause: {divergence.cause}</p>
        </div>
      </div>

      {/* Related Butterfly Effects */}
      {relatedButterflies.length > 0 && (
        <div className="mt-2 pt-2 border-t border-white/10">
          <div className="text-xs font-semibold text-purple-400 mb-1">Predicted Effects:</div>
          <div className="space-y-1">
            {relatedButterflies.map((b, i) => (
              <div key={i} className="text-xs text-gray-400">
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
    <div className="bg-white/5 rounded-lg border border-white/10 p-6">
      <h2 className="text-lg font-bold text-white mb-4">Canon Impact Timeline</h2>

      {/* Stats Bar */}
      <div className="grid grid-cols-3 gap-4 mb-6 p-4 bg-white/5 rounded-lg border border-white/10">
        <div className="text-center">
          <div className="text-2xl font-bold text-gray-200">{stats.total}</div>
          <div className="text-xs text-gray-500">Total Divergences</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-red-400">{stats.major}</div>
          <div className="text-xs text-gray-500">Major Impact</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-yellow-400">{stats.minor}</div>
          <div className="text-xs text-gray-500">Minor Impact</div>
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
          <p className="text-sm text-gray-500">No divergences recorded.</p>
        )}
      </div>

      {/* Detailed View */}
      {selectedDiv && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
          className="border border-blue-500/30 rounded-lg p-4 bg-blue-500/10"
        >
          <h3 className="font-bold text-gray-200 mb-3">Impact Details: {selectedDiv.id}</h3>

          {/* Ripple Effects */}
          {selectedDiv.ripple_effects && selectedDiv.ripple_effects.length > 0 && (
            <div className="mb-3">
              <div className="text-sm font-semibold text-gray-300 mb-2">Ripple Effects:</div>
              <ul className="text-sm space-y-1">
                {selectedDiv.ripple_effects.map((effect, i) => (
                  <li key={i} className="text-gray-400">
                    • {typeof effect === 'string' ? effect : effect.effect || 'Effect recorded'}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Affected Canon Events */}
          {selectedDiv.affected_canon_events && selectedDiv.affected_canon_events.length > 0 && (
            <div>
              <div className="text-sm font-semibold text-gray-300 mb-2">Affected Canon Events:</div>
              <ul className="text-sm space-y-1">
                {selectedDiv.affected_canon_events.map((event, i) => (
                  <li key={i} className="text-gray-400">
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
// 3. STORY INTELLIGENCE SIDEBAR
// ─────────────────────────────────────────────────────────────────────────────

export function StoryIntelligenceSidebar({ chapterMetadata }) {
  if (!chapterMetadata) return null;

  const canonElements = chapterMetadata.canon_elements_used || [];
  const characters = chapterMetadata.character_voices_used || [];
  const powerLimitations = chapterMetadata.power_limitations_shown || [];

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2 }}
      className="bg-white/5 rounded-lg border border-indigo-500/20 p-4 space-y-4"
    >
      <h3 className="text-lg font-bold text-indigo-300">
        Chapter Intelligence
      </h3>

      {/* Canon Used */}
      {canonElements.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-indigo-400 mb-2">Canon References ({canonElements.length})</h4>
          <div className="space-y-1">
            {canonElements.map((elem, i) => (
              <div key={i} className="text-xs bg-white/5 border border-white/10 rounded px-2 py-1 text-gray-300">
                {elem}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Characters */}
      {characters.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-indigo-400 mb-2">Characters Spoken ({characters.length})</h4>
          <div className="space-y-1">
            {characters.map((char, i) => (
              <div key={i} className="text-xs bg-white/5 border border-white/10 rounded px-2 py-1 text-gray-300">
                {char}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Power Limitations */}
      {powerLimitations.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-indigo-400 mb-2">Power Limitations Shown ({powerLimitations.length})</h4>
          <div className="space-y-1">
            {powerLimitations.map((limit, i) => (
              <div key={i} className="text-xs bg-white/5 border border-white/10 rounded px-2 py-1 text-gray-300">
                {limit}
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. INTERACTIVE TIMELINE
// ─────────────────────────────────────────────────────────────────────────────

export function InteractiveTimeline({ timeline }) {
  const events = timeline?.events || [];
  const chapterDates = timeline?.chapter_dates || [];
  const [hoveredIndex, setHoveredIndex] = useState(null);

  if (events.length === 0 && chapterDates.length === 0) {
    return <p className="text-sm text-gray-500">No timeline events recorded.</p>;
  }

  return (
    <div className="bg-white/5 rounded-lg border border-white/10 p-6 space-y-6">
      <h2 className="text-lg font-bold text-white">Story Timeline</h2>

      {/* Chapter Timeline */}
      {chapterDates.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-300 mb-3">
            Chapters
          </h3>
          <div className="flex items-center gap-2 overflow-x-auto pb-4">
            {chapterDates.map((cd, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, delay: i * 0.02 }}
                className="flex-shrink-0 text-center"
              >
                <div className="bg-cyan-500/10 rounded-lg px-3 py-2 border border-cyan-500/30">
                  <div className="font-bold text-sm text-cyan-300">Ch {cd.chapter}</div>
                  <div className="text-xs text-cyan-400 whitespace-nowrap">{cd.date}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      )}

      {/* Events Timeline */}
      {events.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-300 mb-3">
            Events
          </h3>
          <div className="space-y-3">
            {events.map((event, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2, delay: i * 0.02 }}
                className="flex gap-3 p-3 rounded-lg border-l-4 border-purple-500/70 bg-purple-500/10 hover:bg-purple-500/20 transition-colors"
                onMouseEnter={() => setHoveredIndex(i)}
                onMouseLeave={() => setHoveredIndex(null)}
              >
                <div className="flex-shrink-0 text-purple-400 font-bold text-lg mt-0.5">•</div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm text-gray-200">{event.event}</div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {event.date}
                    {event.chapter && ` • Ch ${event.chapter}`}
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
// 5. CHOICE IMPACT PREVIEW
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
        className="w-full text-left px-4 py-3 rounded-lg border border-blue-500/40 bg-blue-500/10 hover:bg-blue-500/20 transition-colors text-gray-200 font-semibold"
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
            transition={{ duration: 0.15 }}
            className="absolute top-full mt-2 left-0 right-0 bg-yellow-500/15 border border-yellow-500/40 rounded-lg p-3 z-10 shadow-lg"
          >
            <div className="text-xs font-semibold text-yellow-300 mb-1">Impact Preview:</div>
            <div className="text-xs text-yellow-200/80">{impact}</div>
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
