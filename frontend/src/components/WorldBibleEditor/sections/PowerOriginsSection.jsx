import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export default function PowerOriginsSection({ data, onSave }) {
  const [expandedPower, setExpandedPower] = useState(null);

  // Handle sources as either array or object
  const rawSources = data?.sources || [];
  const sourcesArray = Array.isArray(rawSources) ? rawSources : Object.values(rawSources);
  const interactions = data?.power_interactions || [];
  const evolutions = data?.theoretical_evolutions || [];
  const usageTracking = data?.usage_tracking || {};

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h2 className="text-lg font-bold text-white mb-2">Power Origins</h2>
        <p className="text-sm text-gray-500">Track crossover powers, their origins, and potential evolutions.</p>
      </div>

      {/* Power Sources */}
      <div className="bg-white/5 rounded-xl p-4 border border-white/10">
        <h3 className="text-sm font-semibold text-purple-300 mb-4">
          Power Sources ({sourcesArray.length})
        </h3>

        {sourcesArray.length === 0 ? (
          <p className="text-sm text-gray-600 text-center py-4">No power sources defined</p>
        ) : (
          <div className="space-y-2">
            {sourcesArray.map((power, idx) => {
              const powerKey = power?.power_name || `power-${idx}`;
              return (
              <div key={powerKey} className="bg-black/20 rounded-lg overflow-hidden">
                <button
                  onClick={() => setExpandedPower(expandedPower === powerKey ? null : powerKey)}
                  className="w-full flex items-center justify-between p-3 hover:bg-white/5 transition-colors"
                >
                  <div>
                    <span className="text-sm text-white font-medium">{power?.power_name || powerKey}</span>
                    {(power?.source_universe || power?.universe_origin) && (
                      <span className="text-xs text-cyan-400 ml-2">({power.source_universe || power.universe_origin})</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {(power?.oc_current_mastery || power?.mastery_level) && (
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        (power.oc_current_mastery || power.mastery_level)?.toLowerCase().includes('master') ? 'bg-purple-500/30 text-purple-300' :
                        (power.oc_current_mastery || power.mastery_level)?.toLowerCase().includes('advanced') ? 'bg-blue-500/30 text-blue-300' :
                        (power.oc_current_mastery || power.mastery_level)?.toLowerCase().includes('intermediate') ? 'bg-green-500/30 text-green-300' :
                        'bg-gray-500/30 text-gray-300'
                      }`}>
                        {power.oc_current_mastery || power.mastery_level}
                      </span>
                    )}
                    <svg
                      className={`w-4 h-4 text-gray-500 transition-transform ${expandedPower === powerKey ? 'rotate-180' : ''}`}
                      fill="none" stroke="currentColor" viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </div>
                </button>

                <AnimatePresence>
                  {expandedPower === powerKey && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="border-t border-white/10 p-4 space-y-3"
                    >
                      {power?.original_wielder && (
                        <div>
                          <label className="text-xs text-gray-500">Original Wielder</label>
                          <p className="text-sm text-gray-300">
                            {power.original_wielder}
                            {power.source_universe && <span className="text-cyan-400 ml-1">({power.source_universe})</span>}
                          </p>
                        </div>
                      )}

                      {power?.combat_style && (
                        <div>
                          <label className="text-xs text-gray-500">Combat Style</label>
                          <p className="text-sm text-orange-300">{power.combat_style}</p>
                        </div>
                      )}

                      {power?.signature_moves?.length > 0 && (
                        <div>
                          <label className="text-xs text-gray-500 block mb-1">Signature Moves ({power.signature_moves.length})</label>
                          <div className="flex flex-wrap gap-1">
                            {power.signature_moves.map((move, i) => (
                              <span key={i} className="text-xs bg-amber-500/20 text-amber-300 px-2 py-1 rounded">
                                {move}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {power?.canon_scene_examples?.length > 0 && (
                        <div>
                          <label className="text-xs text-gray-500 block mb-2">Canon Scene Examples ({power.canon_scene_examples.length})</label>
                          <div className="space-y-3 max-h-80 overflow-y-auto">
                            {power.canon_scene_examples.map((example, i) => (
                              <div key={i} className="bg-gradient-to-r from-purple-500/10 to-cyan-500/10 rounded-lg p-3 border border-purple-500/20">
                                <div className="flex items-start justify-between mb-2">
                                  <span className="text-sm text-white font-medium">{example.scene}</span>
                                  {example.source && (
                                    <span className="text-xs text-gray-500 bg-black/30 px-2 py-0.5 rounded">{example.source}</span>
                                  )}
                                </div>
                                {example.opponent_or_context && (
                                  <p className="text-xs text-cyan-400 mb-1">vs {example.opponent_or_context}</p>
                                )}
                                {example.power_used && (
                                  <p className="text-xs text-purple-300 mb-1">
                                    <span className="text-gray-500">Power:</span> {example.power_used}
                                  </p>
                                )}
                                {example.how_deployed && (
                                  <p className="text-xs text-gray-300 mb-1">
                                    <span className="text-gray-500">How:</span> {example.how_deployed}
                                  </p>
                                )}
                                {example.outcome && (
                                  <p className="text-xs text-green-400">
                                    <span className="text-gray-500">Outcome:</span> {example.outcome}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {power?.canon_techniques?.length > 0 && (
                        <div>
                          <label className="text-xs text-gray-500 block mb-1">Canon Techniques ({power.canon_techniques.length})</label>
                          <div className="space-y-2 max-h-60 overflow-y-auto">
                            {power.canon_techniques.map((tech, i) => (
                              <div key={i} className="bg-purple-500/10 rounded p-2">
                                <div className="flex items-center gap-2">
                                  <span className="text-sm text-purple-300 font-medium">
                                    {typeof tech === 'string' ? tech : tech.name}
                                  </span>
                                  {tech.source && (
                                    <span className="text-xs text-gray-500">{tech.source}</span>
                                  )}
                                </div>
                                {tech.description && (
                                  <p className="text-xs text-gray-400 mt-1">{tech.description}</p>
                                )}
                                {tech.limitations && (
                                  <p className="text-xs text-red-400/70 mt-1">⚠ {tech.limitations}</p>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {power?.mastery_progression?.length > 0 && (
                        <div>
                          <label className="text-xs text-gray-500 block mb-1">Mastery Progression</label>
                          <ol className="text-xs text-gray-400 space-y-1 list-decimal list-inside">
                            {power.mastery_progression.map((step, i) => (
                              <li key={i}>{step}</li>
                            ))}
                          </ol>
                        </div>
                      )}

                      {power?.training_methods?.length > 0 && (
                        <div>
                          <label className="text-xs text-gray-500 block mb-1">Training Methods</label>
                          <ul className="text-xs text-blue-300/80 space-y-1">
                            {power.training_methods.map((method, i) => (
                              <li key={i} className="flex items-start gap-2">
                                <span className="text-blue-400">•</span>
                                {method}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {power?.technique_combinations?.length > 0 && (
                        <div>
                          <label className="text-xs text-gray-500 block mb-1">Technique Combinations</label>
                          <div className="space-y-2">
                            {power.technique_combinations.map((combo, i) => (
                              <div key={i} className="bg-cyan-500/10 rounded p-2">
                                <span className="text-sm text-cyan-300 font-medium">{combo.name}</span>
                                {combo.components && (
                                  <div className="flex flex-wrap gap-1 mt-1">
                                    {combo.components.map((c, j) => (
                                      <span key={j} className="text-xs bg-cyan-500/20 text-cyan-400 px-1.5 py-0.5 rounded">
                                        {c}
                                      </span>
                                    ))}
                                  </div>
                                )}
                                {combo.description && (
                                  <p className="text-xs text-gray-400 mt-1">{combo.description}</p>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {power?.unexplored_potential?.length > 0 && (
                        <div>
                          <label className="text-xs text-gray-500 block mb-1">Unexplored Potential</label>
                          <div className="space-y-2">
                            {power.unexplored_potential.map((potential, i) => (
                              <div key={i} className="bg-yellow-500/10 rounded p-2">
                                <div className="flex items-center gap-2">
                                  <span className="text-sm text-yellow-300 font-medium">{potential.name}</span>
                                  {potential.source && (
                                    <span className="text-xs text-gray-500">{potential.source}</span>
                                  )}
                                </div>
                                {potential.description && (
                                  <p className="text-xs text-gray-400 mt-1">{potential.description}</p>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {(power?.weaknesses_and_counters?.length > 0 || power?.weaknesses?.length > 0) && (
                        <div>
                          <label className="text-xs text-gray-500 block mb-1">Weaknesses & Counters</label>
                          <ul className="text-sm text-red-300 space-y-1 max-h-40 overflow-y-auto">
                            {(power.weaknesses_and_counters || power.weaknesses || []).map((weakness, i) => (
                              <li key={i} className="flex items-start gap-2 text-xs">
                                <span className="text-red-500 mt-0.5">⚠</span>
                                <span className="text-gray-400">{weakness}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
            })}
          </div>
        )}
      </div>

      {/* Power Interactions */}
      {interactions.length > 0 && (
        <div className="bg-white/5 rounded-xl p-4 border border-white/10">
          <h3 className="text-sm font-semibold text-cyan-300 mb-4">
            Power Interactions ({interactions.length})
          </h3>
          <div className="space-y-2">
            {interactions.map((interaction, idx) => (
              <div key={idx} className="bg-black/20 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-sm text-purple-300">{interaction.power1}</span>
                  <span className="text-gray-500">+</span>
                  <span className="text-sm text-cyan-300">{interaction.power2}</span>
                </div>
                <p className="text-xs text-gray-400">{interaction.effect || interaction.result}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Theoretical Evolutions */}
      {evolutions.length > 0 && (
        <div className="bg-white/5 rounded-xl p-4 border border-yellow-500/30">
          <h3 className="text-sm font-semibold text-yellow-300 mb-4">
            Theoretical Evolutions ({evolutions.length})
          </h3>
          <div className="space-y-2">
            {evolutions.map((evolution, idx) => (
              <div key={idx} className="bg-black/20 rounded-lg p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-white font-medium">{evolution.name || evolution.evolution}</span>
                  {evolution.unlocked !== undefined && (
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      evolution.unlocked
                        ? 'bg-green-500/30 text-green-300'
                        : 'bg-gray-500/30 text-gray-400'
                    }`}>
                      {evolution.unlocked ? 'Unlocked' : 'Locked'}
                    </span>
                  )}
                </div>
                {evolution.requirements && (
                  <p className="text-xs text-gray-500">Requirements: {evolution.requirements}</p>
                )}
                {evolution.description && (
                  <p className="text-xs text-gray-400 mt-1">{evolution.description}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Usage Tracking */}
      {Object.keys(usageTracking).length > 0 && (
        <div className="bg-white/5 rounded-xl p-4 border border-green-500/30">
          <h3 className="text-sm font-semibold text-green-300 mb-4">
            Power Usage Tracking ({Object.keys(usageTracking).length} powers)
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {Object.entries(usageTracking).map(([powerName, usage]) => (
              <div key={powerName} className="bg-black/20 rounded-lg p-2">
                <span className="text-xs text-white font-medium block truncate" title={powerName}>
                  {powerName}
                </span>
                <div className="flex items-center justify-between mt-1">
                  <span className="text-xs text-gray-500">Ch.{usage.last_chapter}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    usage.strain_level === 'high' ? 'bg-red-500/30 text-red-300' :
                    usage.strain_level === 'medium' ? 'bg-yellow-500/30 text-yellow-300' :
                    'bg-green-500/30 text-green-300'
                  }`}>
                    {usage.strain_level}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
