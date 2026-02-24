import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import EditableArray from '../EditableArray';

export default function KnowledgeSection({ data, onSave }) {
  const [expandedCharacter, setExpandedCharacter] = useState(null);

  const metaForbidden = data?.meta_knowledge_forbidden || [];
  const characterSecrets = data?.character_secrets || {};
  const knowledgeLimits = data?.character_knowledge_limits || {};
  const commonKnowledge = data?.common_knowledge || [];

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h2 className="text-lg font-bold text-white mb-2">Knowledge Boundaries</h2>
        <p className="text-sm text-gray-500">Track what characters know and don't know to prevent meta-knowledge leaks.</p>
      </div>

      {/* Meta Knowledge Forbidden */}
      <div className="bg-white/5 rounded-xl p-4 border border-red-500/30">
        <h3 className="text-sm font-semibold text-red-300 mb-4 flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
          </svg>
          Meta-Knowledge Forbidden
        </h3>
        <p className="text-xs text-gray-500 mb-3">Things the reader knows but characters should NOT know.</p>
        <EditableArray
          path="knowledge_boundaries.meta_knowledge_forbidden"
          items={metaForbidden}
          onSave={onSave}
          itemType="string"
          emptyMessage="No meta-knowledge restrictions defined"
        />
      </div>

      {/* Common Knowledge */}
      <div className="bg-white/5 rounded-xl p-4 border border-green-500/30">
        <h3 className="text-sm font-semibold text-green-300 mb-4 flex items-center gap-2">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Common Knowledge
        </h3>
        <p className="text-xs text-gray-500 mb-3">Things that are publicly known in-universe.</p>
        <EditableArray
          path="knowledge_boundaries.common_knowledge"
          items={commonKnowledge}
          onSave={onSave}
          itemType="string"
          emptyMessage="No common knowledge defined"
        />
      </div>

      {/* Character Secrets */}
      <div className="bg-white/5 rounded-xl p-4 border border-white/10">
        <h3 className="text-sm font-semibold text-purple-300 mb-4">
          Character Secrets ({Object.keys(characterSecrets).length})
        </h3>

        {Object.keys(characterSecrets).length === 0 ? (
          <p className="text-sm text-gray-600 text-center py-4">No character secrets defined</p>
        ) : (
          <div className="space-y-2">
            {Object.entries(characterSecrets).map(([name, secret]) => (
              <div key={name} className="bg-black/20 rounded-lg overflow-hidden">
                <button
                  onClick={() => setExpandedCharacter(expandedCharacter === name ? null : name)}
                  className="w-full flex items-center justify-between p-3 hover:bg-white/5 transition-colors"
                >
                  <span className="text-sm text-white font-medium">{name}</span>
                  <svg
                    className={`w-4 h-4 text-gray-500 transition-transform ${expandedCharacter === name ? 'rotate-180' : ''}`}
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                <AnimatePresence>
                  {expandedCharacter === name && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="border-t border-white/10 p-3 space-y-2"
                    >
                      <div>
                        <label className="text-xs text-gray-500">Secret</label>
                        <p className="text-sm text-gray-300">{secret?.secret || secret}</p>
                      </div>
                      {secret?.absolutely_hidden_from && (
                        <div>
                          <label className="text-xs text-gray-500">Hidden From</label>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {secret.absolutely_hidden_from.map((char, i) => (
                              <span key={i} className="text-xs bg-red-500/20 text-red-300 px-2 py-0.5 rounded-full">
                                {char}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Character Knowledge Limits */}
      <div className="bg-white/5 rounded-xl p-4 border border-white/10">
        <h3 className="text-sm font-semibold text-cyan-300 mb-4">
          Character Knowledge Limits ({Object.keys(knowledgeLimits).length})
        </h3>

        {Object.keys(knowledgeLimits).length === 0 ? (
          <p className="text-sm text-gray-600 text-center py-4">No knowledge limits defined</p>
        ) : (
          <div className="space-y-2">
            {Object.entries(knowledgeLimits).map(([name, limits]) => (
              <div key={name} className="bg-black/20 rounded-lg p-3">
                <h4 className="text-sm text-white font-medium mb-2">{name}</h4>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-green-400 block mb-1">Knows</label>
                    <ul className="text-xs text-gray-400 space-y-0.5">
                      {(limits?.knows || []).map((item, i) => (
                        <li key={i} className="flex items-start gap-1">
                          <span className="text-green-500">+</span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <label className="text-xs text-red-400 block mb-1">Doesn't Know</label>
                    <ul className="text-xs text-gray-400 space-y-0.5">
                      {(limits?.doesnt_know || []).map((item, i) => (
                        <li key={i} className="flex items-start gap-1">
                          <span className="text-red-500">-</span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
