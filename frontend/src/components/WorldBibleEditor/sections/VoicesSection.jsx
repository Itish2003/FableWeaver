import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import EditableField from '../EditableField';
import EditableArray from '../EditableArray';

export default function VoicesSection({ data, onSave }) {
  const [expandedVoice, setExpandedVoice] = useState(null);

  const voices = data || {};
  const voiceEntries = Object.entries(voices);

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h2 className="text-lg font-bold text-white mb-2">Character Voices</h2>
        <p className="text-sm text-gray-500">Speech patterns and dialogue styles for canon characters.</p>
      </div>

      {voiceEntries.length === 0 ? (
        <div className="bg-white/5 rounded-xl p-8 border border-white/10 text-center">
          <p className="text-sm text-gray-600">No character voices defined yet</p>
        </div>
      ) : (
        <div className="space-y-3">
          {voiceEntries.map(([name, voice]) => (
            <div key={name} className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
              <button
                onClick={() => setExpandedVoice(expandedVoice === name ? null : name)}
                className="w-full flex items-center justify-between p-4 hover:bg-white/5 transition-colors text-left"
              >
                <div>
                  <h3 className="text-sm font-semibold text-white">{name}</h3>
                  {voice?.vocabulary_level && (
                    <span className="text-xs text-gray-500">
                      Vocabulary: {voice.vocabulary_level}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {voice?.speech_patterns && (
                    <span className="text-xs bg-purple-500/20 text-purple-300 px-2 py-0.5 rounded">
                      {Array.isArray(voice.speech_patterns) ? `${voice.speech_patterns.length} patterns` : '1 pattern'}
                    </span>
                  )}
                  <svg
                    className={`w-4 h-4 text-gray-500 transition-transform ${expandedVoice === name ? 'rotate-180' : ''}`}
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>

              <AnimatePresence>
                {expandedVoice === name && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="border-t border-white/10"
                  >
                    <div className="p-4 space-y-4">
                      <EditableField
                        path={`character_voices.${name}.vocabulary_level`}
                        value={voice?.vocabulary_level}
                        onSave={onSave}
                        label="Vocabulary Level"
                        placeholder="e.g., Advanced, Street-level, Academic..."
                      />

                      {/* Speech Patterns */}
                      <div>
                        <label className="text-xs text-gray-500 block mb-2">Speech Patterns</label>
                        <div className="space-y-1">
                          {voice?.speech_patterns ? (
                            Array.isArray(voice.speech_patterns) ? (
                              voice.speech_patterns.map((pattern, idx) => (
                                <div key={idx} className="text-sm text-gray-300 bg-black/20 rounded px-3 py-2">
                                  {pattern}
                                </div>
                              ))
                            ) : (
                              <div className="text-sm text-gray-300 bg-black/20 rounded px-3 py-2">
                                {voice.speech_patterns}
                              </div>
                            )
                          ) : (
                            <p className="text-xs text-gray-600">No speech patterns defined</p>
                          )}
                        </div>
                      </div>

                      {/* Verbal Tics */}
                      {voice?.verbal_tics && (
                        <div>
                          <label className="text-xs text-gray-500 block mb-2">Verbal Tics</label>
                          <div className="text-sm text-gray-300 bg-black/20 rounded px-3 py-2">
                            {Array.isArray(voice.verbal_tics)
                              ? voice.verbal_tics.join(', ')
                              : voice.verbal_tics
                            }
                          </div>
                        </div>
                      )}

                      {/* Emotional Tells */}
                      {voice?.emotional_tells && (
                        <EditableField
                          path={`character_voices.${name}.emotional_tells`}
                          value={voice?.emotional_tells}
                          onSave={onSave}
                          label="Emotional Tells"
                          type="textarea"
                        />
                      )}

                      {/* Topics They Discuss */}
                      {voice?.topics_they_discuss?.length > 0 && (
                        <div>
                          <label className="text-xs text-gray-500 block mb-2">Topics They Discuss</label>
                          <div className="flex flex-wrap gap-1">
                            {voice.topics_they_discuss.map((topic, idx) => (
                              <span key={idx} className="text-xs bg-green-500/20 text-green-300 px-2 py-1 rounded">
                                {topic}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Topics They Avoid */}
                      {voice?.topics_they_avoid?.length > 0 && (
                        <div>
                          <label className="text-xs text-gray-500 block mb-2">Topics They Avoid</label>
                          <div className="flex flex-wrap gap-1">
                            {voice.topics_they_avoid.map((topic, idx) => (
                              <span key={idx} className="text-xs bg-red-500/20 text-red-300 px-2 py-1 rounded">
                                {topic}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Dialogue Examples */}
                      {voice?.dialogue_examples?.length > 0 && (
                        <div>
                          <label className="text-xs text-gray-500 block mb-2">Dialogue Examples</label>
                          <div className="space-y-2">
                            {voice.dialogue_examples.map((example, idx) => (
                              <div key={idx} className="bg-black/20 rounded-lg p-3 border-l-2 border-purple-500/50">
                                <p className="text-sm text-gray-300 italic">"{example}"</p>
                              </div>
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
  );
}
