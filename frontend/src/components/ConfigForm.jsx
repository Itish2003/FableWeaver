import { useState } from 'react';

export default function ConfigForm({ onInit, isConnecting }) {
  const [universes, setUniverses] = useState('Marvel, DC, Harry Potter');
  const [deviation, setDeviation] = useState('What if magic was technology?');
  const [userInput, setUserInput] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    const universeList = universes.split(',').map(u => u.trim());
    onInit(universeList, deviation, userInput);
  };

  return (
    <div className="glass-panel p-8 max-w-2xl mx-auto">
      <h2 className="text-2xl font-bold mb-6 text-white border-b border-white/10 pb-4">Initialize World State</h2>
      
      <form onSubmit={handleSubmit} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-400 mb-2">Canonical Pillars (Universes)</label>
          <input 
            type="text" 
            className="input-field"
            value={universes}
            onChange={(e) => setUniverses(e.target.value)}
            placeholder="e.g. Wormverse, High School DxD"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-400 mb-2">Timeline Anchor & Deviations</label>
          <textarea 
            className="input-field min-h-[100px]"
            value={deviation}
            onChange={(e) => setDeviation(e.target.value)}
            placeholder="Specify the exact year or era and how the timeline deviates from canon."
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-400 mb-2">Protagonist Context & Motives</label>
          <input 
            type="text" 
            className="input-field"
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            placeholder="Detail your character's goals and hidden motives."
          />
        </div>

        <button 
          type="submit" 
          disabled={isConnecting}
          className="btn-primary w-full flex items-center justify-center gap-2"
        >
          {isConnecting ? 'Connecting...' : 'Weave the Fable'}
        </button>
      </form>
    </div>
  );
}
