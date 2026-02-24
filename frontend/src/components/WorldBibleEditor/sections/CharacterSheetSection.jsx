import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import EditableField from '../EditableField';
import EditableArray from '../EditableArray';

export default function CharacterSheetSection({ data, onSave }) {
  const [expandedRelationship, setExpandedRelationship] = useState(null);
  const [expandedIdentity, setExpandedIdentity] = useState(null);

  const relationships = data?.relationships || {};
  const identities = data?.identities || {};

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h2 className="text-lg font-bold text-white mb-2">Character Sheet</h2>
        <p className="text-sm text-gray-500">Protagonist details, relationships, and identities.</p>
      </div>

      {/* Basic Character Info */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white/5 rounded-xl p-4 border border-white/10">
          <h3 className="text-sm font-semibold text-purple-300 mb-4">Identity</h3>
          <EditableField
            path="character_sheet.name"
            value={data?.name}
            onSave={onSave}
            label="Name"
          />
          <EditableField
            path="character_sheet.cape_name"
            value={data?.cape_name}
            onSave={onSave}
            label="Cape Name"
          />
          <EditableField
            path="character_sheet.archetype"
            value={data?.archetype}
            onSave={onSave}
            label="Archetype"
          />
        </div>

        <div className="bg-white/5 rounded-xl p-4 border border-white/10">
          <h3 className="text-sm font-semibold text-cyan-300 mb-4">Status</h3>
          <EditableField
            path="character_sheet.status.health"
            value={data?.status?.health || data?.status?.condition}
            onSave={onSave}
            label="Health"
          />
          <EditableField
            path="character_sheet.status.mental"
            value={data?.status?.mental || data?.status?.mental_state}
            onSave={onSave}
            label="Mental State"
          />
          <EditableField
            path="character_sheet.status.current_location"
            value={data?.status?.current_location}
            onSave={onSave}
            label="Current Location"
          />
        </div>
      </div>

      {/* Description */}
      {data?.description && (
        <div className="bg-white/5 rounded-xl p-4 border border-white/10">
          <EditableField
            path="character_sheet.description"
            value={data?.description}
            onSave={onSave}
            label="Description"
            type="textarea"
          />
        </div>
      )}

      {/* Powers */}
      {data?.powers && (
        <div className="bg-white/5 rounded-xl p-4 border border-white/10">
          <h3 className="text-sm font-semibold text-amber-300 mb-4">Powers</h3>
          <div className="space-y-3">
            <EditableField
              path="character_sheet.powers.core_ability"
              value={data?.powers?.core_ability}
              onSave={onSave}
              label="Core Ability"
              type="textarea"
            />
            <EditableField
              path="character_sheet.powers.classification"
              value={data?.powers?.classification}
              onSave={onSave}
              label="Classification"
            />
            <EditableField
              path="character_sheet.powers.limitations"
              value={data?.powers?.limitations}
              onSave={onSave}
              label="Limitations"
              type="textarea"
            />
            {data?.powers?.trigger && (
              <EditableField
                path="character_sheet.powers.trigger"
                value={data?.powers?.trigger}
                onSave={onSave}
                label="Trigger Event"
                type="textarea"
              />
            )}
          </div>
        </div>
      )}

      {/* Knowledge */}
      <div className="bg-white/5 rounded-xl p-4 border border-white/10">
        <h3 className="text-sm font-semibold text-purple-300 mb-4">Knowledge</h3>
        <EditableArray
          path="character_sheet.knowledge"
          items={data?.knowledge}
          onSave={onSave}
          itemType="string"
          emptyMessage="No knowledge entries"
        />
      </div>

      {/* Relationships */}
      <div className="bg-white/5 rounded-xl p-4 border border-white/10">
        <h3 className="text-sm font-semibold text-cyan-300 mb-4">
          Relationships ({Object.keys(relationships).length})
        </h3>
        <div className="space-y-2">
          {Object.entries(relationships).map(([name, rel]) => (
            <div key={name} className="bg-black/20 rounded-lg overflow-hidden">
              <button
                onClick={() => setExpandedRelationship(expandedRelationship === name ? null : name)}
                className="w-full flex items-center justify-between p-3 hover:bg-white/5 transition-colors"
              >
                <span className="text-sm text-white font-medium">{name}</span>
                <div className="flex items-center gap-2">
                  {typeof rel === 'object' && rel?.trust && (
                    <span className={`text-xs px-2 py-0.5 rounded-full ${
                      rel.trust === 'high' ? 'bg-green-500/30 text-green-300' :
                      rel.trust === 'low' ? 'bg-red-500/30 text-red-300' :
                      'bg-yellow-500/30 text-yellow-300'
                    }`}>
                      {rel.trust}
                    </span>
                  )}
                  <svg
                    className={`w-4 h-4 text-gray-500 transition-transform ${expandedRelationship === name ? 'rotate-180' : ''}`}
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>
              <AnimatePresence>
                {expandedRelationship === name && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="border-t border-white/10"
                  >
                    <div className="p-3 space-y-2">
                      {typeof rel === 'string' ? (
                        <EditableField
                          path={`character_sheet.relationships.${name}`}
                          value={rel}
                          onSave={onSave}
                          label="Description"
                          type="textarea"
                        />
                      ) : (
                        <>
                          <EditableField
                            path={`character_sheet.relationships.${name}.type`}
                            value={rel?.type}
                            onSave={onSave}
                            label="Type"
                          />
                          <EditableField
                            path={`character_sheet.relationships.${name}.trust`}
                            value={rel?.trust}
                            onSave={onSave}
                            label="Trust Level"
                            type="select"
                            options={['high', 'medium', 'mixed', 'low', 'hostile']}
                          />
                          <EditableField
                            path={`character_sheet.relationships.${name}.dynamics`}
                            value={rel?.dynamics}
                            onSave={onSave}
                            label="Dynamics"
                            type="textarea"
                          />
                          <EditableField
                            path={`character_sheet.relationships.${name}.role_in_story`}
                            value={rel?.role_in_story}
                            onSave={onSave}
                            label="Role in Story"
                          />
                        </>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
          {Object.keys(relationships).length === 0 && (
            <p className="text-sm text-gray-600 text-center py-4">No relationships defined</p>
          )}
        </div>
      </div>

      {/* Identities */}
      <div className="bg-white/5 rounded-xl p-4 border border-white/10">
        <h3 className="text-sm font-semibold text-purple-300 mb-4">
          Identities ({Object.keys(identities).length})
        </h3>
        <div className="space-y-2">
          {Object.entries(identities).map(([name, identity]) => (
            <div key={name} className="bg-black/20 rounded-lg overflow-hidden">
              <button
                onClick={() => setExpandedIdentity(expandedIdentity === name ? null : name)}
                className="w-full flex items-center justify-between p-3 hover:bg-white/5 transition-colors"
              >
                <span className="text-sm text-white font-medium">{name}</span>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${
                    identity?.is_public ? 'bg-green-500/30 text-green-300' : 'bg-gray-500/30 text-gray-300'
                  }`}>
                    {identity?.is_public ? 'Public' : 'Secret'}
                  </span>
                  <svg
                    className={`w-4 h-4 text-gray-500 transition-transform ${expandedIdentity === name ? 'rotate-180' : ''}`}
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>
              <AnimatePresence>
                {expandedIdentity === name && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="border-t border-white/10"
                  >
                    <div className="p-3 space-y-2">
                      <EditableField
                        path={`character_sheet.identities.${name}.type`}
                        value={identity?.type}
                        onSave={onSave}
                        label="Type"
                      />
                      <EditableField
                        path={`character_sheet.identities.${name}.public_perception`}
                        value={identity?.public_perception}
                        onSave={onSave}
                        label="Public Perception"
                        type="textarea"
                      />
                      <EditableField
                        path={`character_sheet.identities.${name}.costume_description`}
                        value={identity?.costume_description}
                        onSave={onSave}
                        label="Costume"
                        type="textarea"
                      />
                      <div className="text-xs text-gray-500 mt-2">
                        Known by: {identity?.known_by?.join(', ') || 'None'}
                      </div>
                      <div className="text-xs text-gray-500">
                        Suspected by: {identity?.suspected_by?.join(', ') || 'None'}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
          {Object.keys(identities).length === 0 && (
            <p className="text-sm text-gray-600 text-center py-4">No identities defined</p>
          )}
        </div>
      </div>
    </div>
  );
}
