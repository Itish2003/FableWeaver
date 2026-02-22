import EditableField from '../EditableField';
import EditableArray from '../EditableArray';

export default function MetaSection({ data, onSave }) {
  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h2 className="text-lg font-bold text-white mb-2">Story Metadata</h2>
        <p className="text-sm text-gray-500">Basic information about your story and its settings.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Basic Info */}
        <div className="bg-white/5 rounded-xl p-4 border border-white/10">
          <h3 className="text-sm font-semibold text-purple-300 mb-4">Basic Information</h3>
          <EditableField
            path="meta.title"
            value={data?.title}
            onSave={onSave}
            label="Title"
            placeholder="Enter story title..."
          />
          <EditableField
            path="meta.genre"
            value={data?.genre}
            onSave={onSave}
            label="Genre"
            placeholder="e.g., Action, Drama, Mystery..."
          />
          <EditableField
            path="meta.theme"
            value={data?.theme}
            onSave={onSave}
            label="Theme"
            placeholder="Central theme of the story..."
          />
        </div>

        {/* Timeline Info */}
        <div className="bg-white/5 rounded-xl p-4 border border-white/10">
          <h3 className="text-sm font-semibold text-cyan-300 mb-4">Timeline</h3>
          <EditableField
            path="meta.story_start_date"
            value={data?.story_start_date}
            onSave={onSave}
            label="Story Start Date"
            placeholder="e.g., April 11, 2011"
          />
          <EditableField
            path="meta.current_story_date"
            value={data?.current_story_date}
            onSave={onSave}
            label="Current Story Date"
            placeholder="Current in-story date..."
          />
          <EditableField
            path="meta.timeline_deviation"
            value={data?.timeline_deviation}
            onSave={onSave}
            label="Timeline Deviation"
            placeholder="How the story diverges from canon..."
            type="textarea"
          />
        </div>
      </div>

      {/* Universes */}
      <div className="bg-white/5 rounded-xl p-4 border border-white/10">
        <h3 className="text-sm font-semibold text-purple-300 mb-4">Universes</h3>
        <EditableArray
          path="meta.universes"
          items={data?.universes}
          onSave={onSave}
          itemType="string"
          emptyMessage="No universes defined"
        />
      </div>

      {/* Writing Style Guide */}
      {data?.writing_style_guide && (
        <div className="bg-white/5 rounded-xl p-4 border border-white/10">
          <h3 className="text-sm font-semibold text-cyan-300 mb-4">Writing Style Guide</h3>
          <EditableField
            path="meta.writing_style_guide.pov"
            value={data?.writing_style_guide?.pov}
            onSave={onSave}
            label="Point of View"
            placeholder="e.g., Third-person limited"
          />
          <EditableField
            path="meta.writing_style_guide.tone"
            value={data?.writing_style_guide?.tone}
            onSave={onSave}
            label="Tone"
            placeholder="e.g., Dark, gritty, hopeful undertones"
          />
          <EditableField
            path="meta.writing_style_guide.prose_style"
            value={data?.writing_style_guide?.prose_style}
            onSave={onSave}
            label="Prose Style"
            placeholder="Description of writing style..."
            type="textarea"
          />
        </div>
      )}

      {/* Narrative Conventions */}
      {data?.narrative_conventions && (
        <div className="bg-white/5 rounded-xl p-4 border border-white/10">
          <h3 className="text-sm font-semibold text-purple-300 mb-4">Narrative Conventions</h3>

          {data?.narrative_conventions?.dialogue_mechanics && (
            <div className="mb-4">
              <label className="text-xs text-gray-500 block mb-2">Dialogue Mechanics</label>
              <div className="space-y-2">
                {data.narrative_conventions.dialogue_mechanics.map((mech, i) => (
                  <div key={i} className="bg-black/20 rounded-lg p-3">
                    <div className="text-sm text-gray-300">{mech.style}</div>
                    <div className="text-xs text-gray-500 mt-1">{mech.description}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {data?.narrative_conventions?.interaction_archetypes && (
            <div>
              <label className="text-xs text-gray-500 block mb-2">Interaction Archetypes</label>
              <div className="space-y-2">
                {data.narrative_conventions.interaction_archetypes.map((arch, i) => (
                  <div key={i} className="bg-black/20 rounded-lg p-3">
                    <div className="text-sm text-purple-300 font-medium">{arch.name}</div>
                    <div className="text-xs text-gray-400 mt-1">{arch.description}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
