import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import MetaSection from './sections/MetaSection';
import CharacterSheetSection from './sections/CharacterSheetSection';
import StakesSection from './sections/StakesSection';
import TimelineSection from './sections/TimelineSection';
import DivergencesSection from './sections/DivergencesSection';
import VoicesSection from './sections/VoicesSection';
import KnowledgeSection from './sections/KnowledgeSection';
import PowerOriginsSection from './sections/PowerOriginsSection';
import ChapterEvolutionView from './ChapterEvolutionView';

const API_BASE = 'http://localhost:8000';

const SECTIONS = [
  { id: 'meta', label: 'Meta', icon: '📋' },
  { id: 'character_sheet', label: 'Character', icon: '👤' },
  { id: 'stakes_and_consequences', label: 'Stakes', icon: '⚡' },
  { id: 'story_timeline', label: 'Timeline', icon: '📅' },
  { id: 'divergences', label: 'Divergences', icon: '🔀' },
  { id: 'character_voices', label: 'Voices', icon: '💬' },
  { id: 'knowledge_boundaries', label: 'Knowledge', icon: '🧠' },
  { id: 'power_origins', label: 'Powers', icon: '✨' },
];

export default function WorldBibleEditor({
  isOpen,
  onClose,
  worldBible,
  activeGameId,
  history,
  refreshBible,
}) {
  const [activeSection, setActiveSection] = useState('meta');
  const [saveStatus, setSaveStatus] = useState('idle');
  const [showEvolution, setShowEvolution] = useState(false);

  // Handle escape key
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape' && isOpen) onClose();
    };
    window.addEventListener('keydown', handleEscape);
    return () => window.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  // Save a single field
  const saveBibleEdit = useCallback(async (path, value) => {
    if (!activeGameId) return;
    setSaveStatus('saving');
    try {
      const res = await fetch(`${API_BASE}/stories/${activeGameId}/bible`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, value }),
      });
      if (res.ok) {
        setSaveStatus('saved');
        refreshBible?.();
        setTimeout(() => setSaveStatus('idle'), 2000);
      } else {
        setSaveStatus('error');
        setTimeout(() => setSaveStatus('idle'), 3000);
      }
    } catch (e) {
      console.error('Failed to save Bible edit:', e);
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 3000);
    }
  }, [activeGameId, refreshBible]);

  // Render the active section
  const renderSection = () => {
    const sectionData = worldBible?.[activeSection];
    const props = { data: sectionData, onSave: saveBibleEdit, worldBible };

    switch (activeSection) {
      case 'meta':
        return <MetaSection {...props} />;
      case 'character_sheet':
        return <CharacterSheetSection {...props} />;
      case 'stakes_and_consequences':
        return <StakesSection {...props} />;
      case 'story_timeline':
        return <TimelineSection {...props} />;
      case 'divergences':
        return <DivergencesSection {...props} />;
      case 'character_voices':
        return <VoicesSection {...props} />;
      case 'knowledge_boundaries':
        return <KnowledgeSection {...props} />;
      case 'power_origins':
        return <PowerOriginsSection {...props} />;
      default:
        return <div className="text-gray-400">Select a section</div>;
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 bg-black/95 backdrop-blur-xl z-50 flex flex-col"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
            <div className="flex items-center gap-4">
              <button
                onClick={onClose}
                className="p-2 rounded-lg bg-white/5 hover:bg-white/10 transition-colors"
              >
                <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
              <h1 className="text-xl font-bold text-white">World Bible Editor</h1>
            </div>

            <div className="flex items-center gap-4">
              {/* Evolution Toggle */}
              <button
                onClick={() => setShowEvolution(!showEvolution)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  showEvolution
                    ? 'bg-purple-500/30 text-purple-300 border border-purple-500/50'
                    : 'bg-white/5 text-gray-400 hover:bg-white/10'
                }`}
              >
                {showEvolution ? 'Hide' : 'Show'} Evolution
              </button>

              {/* Save Status */}
              <div className={`px-3 py-1.5 rounded-lg text-sm ${
                saveStatus === 'saving' ? 'bg-yellow-500/20 text-yellow-300' :
                saveStatus === 'saved' ? 'bg-green-500/20 text-green-300' :
                saveStatus === 'error' ? 'bg-red-500/20 text-red-300' :
                'bg-white/5 text-gray-500'
              }`}>
                {saveStatus === 'saving' ? 'Saving...' :
                 saveStatus === 'saved' ? 'Saved' :
                 saveStatus === 'error' ? 'Error saving' :
                 'Auto-save enabled'}
              </div>
            </div>
          </div>

          {/* Tab Navigation */}
          <div className="flex gap-1 px-6 py-3 border-b border-white/10 overflow-x-auto custom-scrollbar">
            {SECTIONS.map((section) => (
              <button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                className={`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-all ${
                  activeSection === section.id
                    ? 'bg-purple-500/30 text-purple-300 border border-purple-500/50'
                    : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-gray-300'
                }`}
              >
                <span className="mr-2">{section.icon}</span>
                {section.label}
              </button>
            ))}
          </div>

          {/* Main Content */}
          <div className="flex-1 flex overflow-hidden">
            {/* Section Content */}
            <div className={`flex-1 overflow-y-auto custom-scrollbar p-6 ${showEvolution ? 'w-2/3' : 'w-full'}`}>
              <AnimatePresence mode="wait">
                <motion.div
                  key={activeSection}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  transition={{ duration: 0.2 }}
                >
                  {renderSection()}
                </motion.div>
              </AnimatePresence>
            </div>

            {/* Evolution Panel */}
            <AnimatePresence>
              {showEvolution && (
                <motion.div
                  initial={{ width: 0, opacity: 0 }}
                  animate={{ width: '33.333%', opacity: 1 }}
                  exit={{ width: 0, opacity: 0 }}
                  transition={{ duration: 0.3 }}
                  className="border-l border-white/10 overflow-hidden"
                >
                  <div className="h-full overflow-y-auto custom-scrollbar p-4">
                    <ChapterEvolutionView history={history} />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
