import EditableArray from '../EditableArray';

const SEVERITY_OPTIONS = ['minor', 'moderate', 'severe', 'permanent'];

const costSchema = {
  cost: { type: 'text', label: 'Cost', placeholder: 'What was the cost?' },
  severity: { type: 'select', label: 'Severity', options: SEVERITY_OPTIONS, default: 'moderate' },
  chapter: { type: 'number', label: 'Chapter', placeholder: '#' },
};

const nearMissSchema = {
  what_almost_happened: { type: 'text', label: 'What Almost Happened', placeholder: 'Description...' },
  saved_by: { type: 'text', label: 'Saved By', placeholder: 'How was it prevented?' },
  chapter: { type: 'number', label: 'Chapter', placeholder: '#' },
};

const consequenceSchema = {
  action: { type: 'text', label: 'Action', placeholder: 'What action caused this?' },
  predicted_consequence: { type: 'text', label: 'Predicted Consequence', placeholder: 'What might happen?' },
  due_by: { type: 'text', label: 'Due By', placeholder: 'When should this trigger?', default: 'Ongoing' },
};

export default function StakesSection({ data, onSave }) {
  // Render power debt as a simple display (complex nested structure)
  const renderPowerDebt = () => {
    const debt = data?.power_usage_debt || {};
    const entries = Object.entries(debt);

    if (entries.length === 0) {
      return <p className="text-sm text-gray-600 text-center py-4">No power strain tracked</p>;
    }

    return (
      <div className="space-y-2">
        {entries.map(([power, info]) => (
          <div key={power} className="flex items-center justify-between bg-black/20 rounded-lg p-3">
            <span className="text-sm text-purple-300 font-medium">{power}</span>
            <div className="flex items-center gap-4">
              <span className={`text-xs px-2 py-1 rounded ${
                info.strain_level === 'critical' ? 'bg-red-500/30 text-red-300' :
                info.strain_level === 'high' ? 'bg-orange-500/30 text-orange-300' :
                info.strain_level === 'medium' ? 'bg-yellow-500/30 text-yellow-300' :
                'bg-green-500/30 text-green-300'
              }`}>
                {info.strain_level || 'low'}
              </span>
              {info.uses_this_chapter && (
                <span className="text-xs text-gray-500">
                  {info.uses_this_chapter} uses
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div className="mb-6">
        <h2 className="text-lg font-bold text-white mb-2">Stakes & Consequences</h2>
        <p className="text-sm text-gray-500">Track costs, near-misses, and pending consequences to maintain narrative tension.</p>
      </div>

      {/* Stats Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-red-400">{data?.costs_paid?.length || 0}</div>
          <div className="text-xs text-red-300/70">Costs Paid</div>
        </div>
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-yellow-400">{data?.near_misses?.length || 0}</div>
          <div className="text-xs text-yellow-300/70">Near Misses</div>
        </div>
        <div className="bg-purple-500/10 border border-purple-500/30 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-purple-400">{data?.pending_consequences?.length || 0}</div>
          <div className="text-xs text-purple-300/70">Pending</div>
        </div>
        <div className="bg-cyan-500/10 border border-cyan-500/30 rounded-xl p-4 text-center">
          <div className="text-2xl font-bold text-cyan-400">{Object.keys(data?.power_usage_debt || {}).length}</div>
          <div className="text-xs text-cyan-300/70">Power Debts</div>
        </div>
      </div>

      {/* Costs Paid */}
      <div className="bg-white/5 rounded-xl p-4 border border-white/10">
        <h3 className="text-sm font-semibold text-red-300 mb-4 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-red-500"></span>
          Costs Paid
        </h3>
        <EditableArray
          path="stakes_and_consequences.costs_paid"
          items={data?.costs_paid}
          onSave={onSave}
          itemType="object"
          itemSchema={costSchema}
          emptyMessage="No costs recorded yet"
        />
      </div>

      {/* Near Misses */}
      <div className="bg-white/5 rounded-xl p-4 border border-white/10">
        <h3 className="text-sm font-semibold text-yellow-300 mb-4 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-yellow-500"></span>
          Near Misses
        </h3>
        <EditableArray
          path="stakes_and_consequences.near_misses"
          items={data?.near_misses}
          onSave={onSave}
          itemType="object"
          itemSchema={nearMissSchema}
          emptyMessage="No near misses recorded"
        />
      </div>

      {/* Pending Consequences */}
      <div className="bg-white/5 rounded-xl p-4 border border-white/10">
        <h3 className="text-sm font-semibold text-purple-300 mb-4 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-purple-500"></span>
          Pending Consequences
        </h3>
        <EditableArray
          path="stakes_and_consequences.pending_consequences"
          items={data?.pending_consequences}
          onSave={onSave}
          itemType="object"
          itemSchema={consequenceSchema}
          emptyMessage="No pending consequences"
        />
      </div>

      {/* Power Usage Debt */}
      <div className="bg-white/5 rounded-xl p-4 border border-white/10">
        <h3 className="text-sm font-semibold text-cyan-300 mb-4 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-cyan-500"></span>
          Power Usage Debt
        </h3>
        {renderPowerDebt()}
      </div>
    </div>
  );
}
