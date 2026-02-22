import { useEffect, useRef, useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import TimelineComparison from './TimelineComparison';
import WorldBibleEditor from './WorldBibleEditor/WorldBibleEditor';

// Available slash commands
const SLASH_COMMANDS = [
  { cmd: '/research', args: '[deep|quick] <topic>', desc: 'Research lore and update World Bible. Use "deep" for multi-agent parallel research.', example: '/research deep Amon powers voicelines' },
  { cmd: '/research quick', args: '<topic>', desc: 'Quick single-agent research (default)', example: '/research quick Lung timeline' },
  { cmd: '/research deep', args: '<topic>', desc: 'Deep multi-agent research with query planning (3-5 parallel researchers)', example: '/research deep character relationships and personality' },
  { cmd: '/enrich', args: '[focus areas]', desc: 'Analyze World Bible gaps and fill via research. Runs in parallel.', example: '/enrich locations relations events' },
  { cmd: '/rewrite', args: '[instruction]', desc: 'Rewrite the last chapter with optional guidance', example: '/rewrite make it more dramatic' },
  { cmd: '/undo', args: '', desc: 'Undo last chapter and restore World Bible to previous state' },
  { cmd: '/bible-diff', args: '', desc: 'Show what Archivist changed in World Bible during last chapter' },
  { cmd: '/bible-snapshot', args: '<save|load|list|delete> [name]', desc: 'Save, load, list, or delete named Bible snapshots', example: '/bible-snapshot save before_battle' },
  { cmd: '/reset', args: '', desc: 'Reset session state (use to fix errors)' },
  { cmd: '/help', args: '', desc: 'Show this commands help' },
  { cmd: '/export', args: '', desc: 'Export full story as downloadable text' },
];

// Helper to count words
const countWords = (text) => {
  if (!text) return 0;
  return text.trim().split(/\s+/).filter(Boolean).length;
};

// Helper to safely get array from potentially stringified JSON
const safeArray = (value) => {
  if (!value) return [];
  if (Array.isArray(value)) return value;
  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
};

// Helper to strip JSON metadata block from chapter text for display
const stripJsonMetadata = (text) => {
  if (!text) return '';
  // Match JSON block containing "choices" or "summary" (chapter metadata)
  const jsonMatch = text.match(/```json[\s\S]*?```|\{[\s\S]*"(?:choices|summary)"[\s\S]*\}$/);
  if (jsonMatch) {
    return text.substring(0, jsonMatch.index).trim();
  }
  return text;
};

// API base for backend calls
const API_BASE = 'http://localhost:8000';

export default function StoryView({ engine }) {
  const { history = [], currentText, choices, questions, status, sendChoice, sendResearch, sendCommand, deleteChapter, worldBible, bibleLoading, activeGameId, refreshBible, setQuestionAnswer, branches = [], branchInfo, createBranch, switchToBranch, goToParent } = engine || {};
  const contentRef = useRef(null);
  const chapterRefs = useRef({});
  const [inputVal, setInputVal] = useState('');
  const [showHelp, setShowHelp] = useState(false);
  const [showCommandHint, setShowCommandHint] = useState(false);
  const [showBiblePanel, setShowBiblePanel] = useState(false);
  const [showWorldBibleEditor, setShowWorldBibleEditor] = useState(false);
  const [bibleTab, setBibleTab] = useState('overview'); // overview, powers, stakes, timeline, edit

  // Collapsible chapters
  const [collapsedChapters, setCollapsedChapters] = useState(new Set());

  // Editing state
  const [editingField, setEditingField] = useState(null);
  const [editValue, setEditValue] = useState('');

  // Branch creation state
  const [showBranchModal, setShowBranchModal] = useState(false);
  const [newBranchName, setNewBranchName] = useState('');
  const [showBranchList, setShowBranchList] = useState(false);

  // Question answers UI state
  const [questionAnswers, setQuestionAnswersLocal] = useState({});

  // Calculate total word count
  const totalWords = useMemo(() => {
    return history.reduce((sum, ch) => sum + countWords(ch.text), 0);
  }, [history]);

  // Auto-scroll to bottom of content
  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [currentText, history]);

  // Debug logging
  useEffect(() => {
    console.log("StoryView Mounted. History:", history?.length, "Status:", status);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Command suggestions based on input
  const commandSuggestions = useMemo(() => {
    if (!inputVal.startsWith('/')) return [];
    const typed = inputVal.toLowerCase();
    return SLASH_COMMANDS.filter(c => c.cmd.toLowerCase().startsWith(typed));
  }, [inputVal]);

  // Show hint when typing /
  useEffect(() => {
    setShowCommandHint(inputVal.startsWith('/') && commandSuggestions.length > 0);
  }, [inputVal, commandSuggestions]);

  const scrollToChapter = (index) => {
    const ref = chapterRefs.current[index];
    if (ref) {
      ref.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  const toggleChapterCollapse = (index) => {
    setCollapsedChapters(prev => {
      const newSet = new Set(prev);
      if (newSet.has(index)) {
        newSet.delete(index);
      } else {
        newSet.add(index);
      }
      return newSet;
    });
  };

  const collapseAll = () => {
    setCollapsedChapters(new Set(history.map((_, i) => i)));
  };

  const expandAll = () => {
    setCollapsedChapters(new Set());
  };

  // Save Bible field edit
  const saveBibleEdit = async (path, value) => {
    if (!activeGameId) return;
    try {
      const res = await fetch(`${API_BASE}/stories/${activeGameId}/bible`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, value })
      });
      if (res.ok && refreshBible) {
        refreshBible();
      }
    } catch (e) {
      console.error('Failed to save Bible edit:', e);
    }
    setEditingField(null);
    setEditValue('');
  };

  const startEditing = (path, currentValue) => {
    setEditingField(path);
    setEditValue(currentValue || '');
  };

  // Handle branch creation
  const handleCreateBranch = async () => {
    if (!newBranchName.trim()) return;
    const result = await createBranch(newBranchName.trim());
    if (result) {
      setShowBranchModal(false);
      setNewBranchName('');
      // Optionally switch to the new branch
      // switchToBranch(result.branch_id);
    }
  };

  const handleSend = (e) => {
    e.preventDefault();
    if (!inputVal.trim()) return;

    const trimmed = inputVal.trim();

    // Handle slash commands
    if (trimmed.startsWith('/')) {
      const parts = trimmed.split(' ');
      const cmd = parts[0].toLowerCase();
      const args = parts.slice(1).join(' ');

      switch (cmd) {
        case '/research':
          if (args) sendResearch(args);
          break;
        case '/enrich':
          // Send to backend - analyzes World Bible gaps and runs parallel research
          sendChoice(trimmed);
          break;
        case '/rewrite':
          // Send as choice with /rewrite prefix - backend handles it
          sendChoice(trimmed);
          break;
        case '/undo':
          // Send as choice - backend parses the /undo command
          sendChoice(trimmed);
          break;
        case '/reset':
          // Send as choice - backend parses the /reset command
          sendChoice(trimmed);
          break;
        case '/bible-diff':
          // Show Archivist changes in World Bible
          sendChoice(trimmed);
          break;
        case '/bible-snapshot':
          // Save/load/list/delete Bible snapshots
          sendChoice(trimmed);
          break;
        case '/help':
          setShowHelp(true);
          break;
        case '/export':
          handleExport();
          break;
        default:
          // Unknown command - send as choice anyway
          sendChoice(trimmed);
      }
    } else {
      sendChoice(trimmed);
    }
    setInputVal('');
    setShowCommandHint(false);
  };

  const handleExport = async () => {
    if (!activeGameId) {
      // Fallback to local export
      if (!history || history.length === 0) return;
      const storyText = history.map((ch, i) =>
        `=== Chapter ${ch.sequence || i + 1} ===\n\n${ch.text}\n\n`
      ).join('\n');
      const blob = new Blob([storyText], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'fable-story.txt';
      a.click();
      URL.revokeObjectURL(url);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/stories/${activeGameId}/export?format=markdown`);
      if (res.ok) {
        const data = await res.json();
        const blob = new Blob([data.content], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'fable-story.md';
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (e) {
      console.error('Export failed:', e);
    }
  };

  const handleDeleteChapter = (e, chapterId, index) => {
    e.stopPropagation();
    if (deleteChapter && window.confirm(`Delete Chapter ${index + 1}? This cannot be undone.`)) {
      deleteChapter(chapterId);
    }
  };

  const isProcessing = status === 'processing';

  return (
    <div className="flex h-full gap-6">
      {/* Sidebar: History / TOC */}
      <aside className="hidden md:flex flex-col w-1/4 glass-panel p-4 overflow-hidden border-r border-white/5 bg-black/20">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-bold text-accent">Chronicles</h3>
          {history.length > 0 && (
            <div className="text-xs text-gray-400">
              {totalWords.toLocaleString()} words
            </div>
          )}
        </div>

        {/* Branch Indicator */}
        {branchInfo?.isBranch && (
          <div className="mb-3 p-2 bg-violet-500/10 border border-violet-500/30 rounded-lg">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
              </svg>
              <span className="text-xs text-violet-300 font-medium">Branch: {branchInfo.branchName}</span>
            </div>
            <button
              onClick={goToParent}
              className="mt-2 w-full text-xs py-1 bg-white/5 hover:bg-white/10 rounded text-gray-400 hover:text-white transition-colors"
            >
              ← Return to Main Story
            </button>
          </div>
        )}

        {/* Branch Controls */}
        <div className="mb-3 flex gap-2">
          <button
            onClick={() => setShowBranchModal(true)}
            className="flex-1 text-xs py-1.5 px-2 bg-violet-500/10 hover:bg-violet-500/20 rounded border border-violet-500/20 text-violet-300 hover:text-violet-200 transition-colors flex items-center justify-center gap-1"
            title="Create a branch from this point"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
            </svg>
            Branch
          </button>
          {branches.length > 0 && (
            <button
              onClick={() => setShowBranchList(!showBranchList)}
              className="flex-1 text-xs py-1.5 px-2 bg-white/5 hover:bg-white/10 rounded border border-white/10 text-gray-400 hover:text-white transition-colors flex items-center justify-center gap-1"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
              {branches.length} Branch{branches.length !== 1 ? 'es' : ''}
            </button>
          )}
        </div>

        {/* Branch List Dropdown */}
        <AnimatePresence>
          {showBranchList && branches.length > 0 && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="mb-3 overflow-hidden"
            >
              <div className="bg-black/30 rounded-lg border border-white/10 p-2 space-y-1">
                {branches.map(branch => (
                  <button
                    key={branch.id}
                    onClick={() => {
                      switchToBranch(branch.id);
                      setShowBranchList(false);
                    }}
                    className="w-full text-left p-2 rounded hover:bg-white/10 transition-colors"
                  >
                    <div className="text-xs text-violet-300 font-medium">{branch.name}</div>
                    <div className="text-xs text-gray-500">
                      Branched at Ch. {branch.branch_point_chapter}
                    </div>
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Collapse/Expand All */}
        {history.length > 1 && (
          <div className="flex gap-2 mb-3">
            <button
              onClick={collapseAll}
              className="flex-1 text-xs py-1 px-2 bg-white/5 hover:bg-white/10 rounded border border-white/10 text-gray-400 hover:text-white transition-colors"
            >
              Collapse All
            </button>
            <button
              onClick={expandAll}
              className="flex-1 text-xs py-1 px-2 bg-white/5 hover:bg-white/10 rounded border border-white/10 text-gray-400 hover:text-white transition-colors"
            >
              Expand All
            </button>
          </div>
        )}

        <div className="overflow-y-auto flex-1 space-y-3 pr-2 custom-scrollbar">
          {(!history || history.length === 0) && (
            <div className="text-secondary text-sm italic">The chronicle has just begun...</div>
          )}
          {history && history.map((chapter, index) => {
            const wordCount = countWords(stripJsonMetadata(chapter.text));
            return (
              <motion.div
                key={chapter.id || index}
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                onClick={() => scrollToChapter(index)}
                className="p-3 bg-white/5 rounded-lg cursor-pointer hover:bg-white/10 transition-colors border border-white/5 group relative"
              >
                {/* Delete button - appears on hover */}
                {deleteChapter && (
                  <button
                    onClick={(e) => handleDeleteChapter(e, chapter.id, index)}
                    className="absolute top-2 right-2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-500/20 text-red-400 transition-all"
                    title="Delete chapter"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                )}
                <div className="flex justify-between items-center mb-1">
                  <div className="text-xs text-accent-glow font-bold uppercase tracking-wider">
                    Chapter {chapter.sequence || index + 1}
                  </div>
                  <div className="text-xs text-gray-500">
                    {wordCount.toLocaleString()} w
                  </div>
                </div>
                <div className="text-sm text-gray-300 line-clamp-3">
                  {chapter.summary || "No summary available."}
                </div>
              </motion.div>
            );
          })}
          {isProcessing && (
            <div className="p-3 animate-pulse bg-white/5 rounded-lg">
              <div className="h-2 bg-white/10 rounded w-1/2 mb-2"></div>
              <div className="h-2 bg-white/10 rounded w-3/4"></div>
            </div>
          )}
        </div>

        {/* Quick Commands */}
        <div className="mt-4 pt-4 border-t border-white/10">
          <button
            onClick={() => setShowHelp(true)}
            className="w-full text-xs text-secondary hover:text-white flex items-center justify-center gap-2 py-2 hover:bg-white/5 rounded transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Commands Help
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <section className="flex-1 flex flex-col glass-panel overflow-hidden relative bg-black/40">
        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar scroll-smooth" ref={contentRef}>
          <div className="max-w-3xl mx-auto space-y-8 pb-4">
            
            {history && history.map((chapter, index) => {
              const isCollapsed = collapsedChapters.has(index);
              const wordCount = countWords(stripJsonMetadata(chapter.text));
              return (
                <div
                  key={chapter.id || index}
                  ref={el => chapterRefs.current[index] = el}
                  className="prose prose-invert prose-lg max-w-none opacity-90 mb-12 border-b border-white/5 pb-8"
                >
                  <div
                    className="flex justify-between items-center cursor-pointer group"
                    onClick={() => toggleChapterCollapse(index)}
                  >
                    <h2 className="text-2xl font-display text-accent mb-4 flex items-center gap-3">
                      <span className={`transition-transform ${isCollapsed ? '' : 'rotate-90'}`}>
                        ▶
                      </span>
                      Chapter {chapter.sequence || index + 1}
                      <span className="text-sm text-gray-500 font-normal">
                        ({wordCount.toLocaleString()} words)
                      </span>
                    </h2>
                  </div>

                  <AnimatePresence>
                    {!isCollapsed && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <div className="whitespace-pre-wrap leading-relaxed font-serif text-gray-200">
                          {stripJsonMetadata(chapter.text)}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>

                  {isCollapsed && (
                    <div className="text-sm text-gray-500 italic mt-2">
                      {chapter.summary || 'Click to expand...'}
                    </div>
                  )}
                </div>
              );
            })}
            
            {(currentText || isProcessing) && (
              <div className="prose prose-invert prose-lg max-w-none">
                 <h2 className="text-2xl font-display text-accent mb-4">
                   Chapter {(history?.length || 0) + 1}
                   {isProcessing && <span className="animate-pulse ml-2 text-sm text-secondary">...Weaving</span>}
                 </h2>
                 <div className="whitespace-pre-wrap leading-relaxed font-serif text-gray-100 min-h-[100px]">
                   {currentText}
                   {isProcessing && <span className="inline-block w-2 h-4 bg-accent ml-1 animate-pulse"/>}
                 </div>
              </div>
            )}
            
            {/* Clarifying Questions - Rendered before choices */}
            <AnimatePresence>
                {questions && questions.length > 0 && !isProcessing && (
                  <motion.div
                    initial={{ y: 20, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    exit={{ y: 20, opacity: 0 }}
                    className="mt-8 mb-4 p-4 bg-amber-900/20 border border-amber-500/30 rounded-lg"
                  >
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-amber-400 text-sm uppercase tracking-wider font-bold">Clarifying Questions</span>
                      <span className="text-amber-400/60 text-xs">(Optional - helps shape the next chapter)</span>
                    </div>
                    <div className="space-y-4">
                      {questions.map((q, qIndex) => (
                        <div key={qIndex} className="space-y-2">
                          <div className="text-gray-200 text-sm font-medium">{q.question}</div>
                          {q.context && (
                            <div className="text-gray-400 text-xs italic">{q.context}</div>
                          )}
                          {q.options && q.options.length > 0 ? (
                            <div className="flex flex-wrap gap-2 mt-2">
                              {q.options.map((opt, optIndex) => (
                                <button
                                  key={optIndex}
                                  onClick={() => {
                                    const newAnswers = { ...questionAnswers, [qIndex]: opt };
                                    setQuestionAnswersLocal(newAnswers);
                                    setQuestionAnswer?.(qIndex, opt);
                                  }}
                                  className={`px-3 py-1.5 text-sm rounded border transition-all ${
                                    questionAnswers[qIndex] === opt
                                      ? 'bg-amber-500/30 border-amber-500 text-amber-200'
                                      : 'bg-white/5 border-white/10 text-gray-300 hover:border-amber-500/50 hover:text-amber-200'
                                  }`}
                                >
                                  {opt}
                                </button>
                              ))}
                            </div>
                          ) : (
                            <input
                              type="text"
                              placeholder="Type your answer..."
                              value={questionAnswers[qIndex] || ''}
                              onChange={(e) => {
                                const newAnswers = { ...questionAnswers, [qIndex]: e.target.value };
                                setQuestionAnswersLocal(newAnswers);
                                setQuestionAnswer?.(qIndex, e.target.value);
                              }}
                              className="w-full bg-black/40 border border-white/10 rounded px-3 py-2 text-sm text-gray-200 placeholder:text-gray-500 focus:outline-none focus:border-amber-500/50"
                            />
                          )}
                        </div>
                      ))}
                    </div>
                  </motion.div>
                )}
            </AnimatePresence>

            {/* Inline Choices - Rendered after questions */}
            <AnimatePresence>
                {choices && choices.length > 0 && !isProcessing && (
                  <motion.div
                    initial={{ y: 20, opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    exit={{ y: 20, opacity: 0 }}
                    className="mt-8 mb-4 grid gap-3 grid-cols-1 md:grid-cols-2"
                  >
                    {choices.map((choice, index) => (
                      <button
                        key={index}
                        onClick={() => {
                          sendChoice(choice);
                          setQuestionAnswersLocal({});  // Clear local answers after choice
                        }}
                        className="p-4 bg-white/5 hover:bg-violet-600/20 border border-white/10 hover:border-violet-500 rounded-lg text-left transition-all text-sm group"
                      >
                       <span className="block text-xs uppercase text-secondary group-hover:text-accent mb-1">Option {index + 1}</span>
                       <span className="text-gray-200 group-hover:text-white font-serif text-lg leading-snug">{choice}</span>
                      </button>
                    ))}
                  </motion.div>
                )}
            </AnimatePresence>

            {!currentText && (!history || history.length === 0) && !isProcessing && (
               <div className="flex items-center justify-center h-40 text-secondary italic">
                 Waiting for the Fate's decree...
               </div>
            )}
          </div>
        </div>

        {/* Input Area - Sticky Bottom */}
        <div className="p-4 bg-[#0a0a0c]/90 border-t border-white/10 z-10 shrink-0 backdrop-blur-lg">
          <div className="max-w-3xl mx-auto">
            {/* Command Suggestions */}
            <AnimatePresence>
              {showCommandHint && commandSuggestions.length > 0 && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 10 }}
                  className="mb-2 p-2 bg-black/60 border border-white/10 rounded-lg"
                >
                  <div className="text-xs text-secondary mb-1">Commands:</div>
                  <div className="flex flex-wrap gap-2">
                    {commandSuggestions.map(cmd => (
                      <button
                        key={cmd.cmd}
                        type="button"
                        onClick={() => setInputVal(cmd.cmd + ' ')}
                        className="text-xs bg-white/5 hover:bg-white/10 px-2 py-1 rounded border border-white/10 text-gray-300 hover:text-white transition-colors"
                      >
                        <span className="text-accent">{cmd.cmd}</span>
                        {cmd.args && <span className="text-gray-500 ml-1">{cmd.args}</span>}
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            <form onSubmit={handleSend} className="relative">
              <input
                type="text"
                value={inputVal}
                onChange={(e) => setInputVal(e.target.value)}
                disabled={isProcessing}
                placeholder={isProcessing ? "Fate is being written..." : "Enter action, choice, or type / for commands"}
                className="w-full bg-black/40 border border-white/10 rounded-lg px-4 py-3 pr-24 text-gray-200 placeholder:text-gray-600 focus:outline-none focus:border-accent transition-colors"
              />
              <button
                type="submit"
                disabled={isProcessing || !inputVal.trim()}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-xs bg-white/10 hover:bg-white/20 text-white px-4 py-2 rounded disabled:opacity-50 transition-colors uppercase tracking-wider font-bold"
              >
                Send
              </button>
            </form>
          </div>
        </div>
      </section>

      {/* Help Modal */}
      <AnimatePresence>
        {showHelp && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setShowHelp(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="bg-[#0a0a0c] border border-white/10 rounded-2xl p-6 max-w-lg w-full shadow-2xl"
              onClick={e => e.stopPropagation()}
            >
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-xl font-bold text-white">Available Commands</h3>
                <button
                  onClick={() => setShowHelp(false)}
                  className="p-1 hover:bg-white/10 rounded transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="space-y-3 max-h-[60vh] overflow-y-auto custom-scrollbar">
                {SLASH_COMMANDS.map(cmd => (
                  <div key={cmd.cmd} className="p-3 bg-white/5 rounded-lg border border-white/5">
                    <div className="flex items-baseline gap-2">
                      <code className="text-accent font-mono">{cmd.cmd}</code>
                      {cmd.args && <span className="text-gray-500 text-sm">{cmd.args}</span>}
                    </div>
                    <p className="text-sm text-gray-400 mt-1">{cmd.desc}</p>
                    {cmd.example && (
                      <code className="text-xs text-cyan-400/70 mt-1 block font-mono">
                        Example: {cmd.example}
                      </code>
                    )}
                  </div>
                ))}
              </div>

              <div className="mt-4 pt-4 border-t border-white/10">
                <h4 className="text-sm font-semibold text-gray-300 mb-2">Research Depth Modes:</h4>
                <div className="space-y-2 mb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2 py-0.5 bg-cyan-500/20 text-cyan-300 rounded font-mono">quick</span>
                    <span className="text-xs text-gray-400">Single researcher agent (fast, default)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2 py-0.5 bg-amber-500/20 text-amber-300 rounded font-mono">deep</span>
                    <span className="text-xs text-gray-400">3-5 parallel researchers (thorough, slower)</span>
                  </div>
                </div>

                <h4 className="text-sm font-semibold text-gray-300 mb-2">Focus Areas for /enrich:</h4>
                <div className="flex flex-wrap gap-1 mb-3">
                  {['locations', 'relations', 'voices', 'identities', 'events', 'timeline', 'canon'].map(area => (
                    <span key={area} className="text-xs px-2 py-0.5 bg-violet-500/20 text-violet-300 rounded">
                      {area}
                    </span>
                  ))}
                </div>
                <p className="text-xs text-gray-500">You can also click on a choice button or type any custom action.</p>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* World Bible Panel (Right Drawer) */}
      <AnimatePresence>
        {showBiblePanel && (
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            className="fixed right-0 top-0 h-full w-[520px] bg-[#0a0a0c]/95 backdrop-blur-xl border-l border-white/10 z-40 flex flex-col shadow-2xl"
          >
            {/* Header */}
            <div className="p-4 border-b border-white/10 flex justify-between items-center">
              <h3 className="text-lg font-bold text-accent">World Bible</h3>
              <button
                onClick={() => setShowBiblePanel(false)}
                className="p-1 hover:bg-white/10 rounded transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Tabs */}
            <div className="flex border-b border-white/10">
              {[
                { id: 'overview', label: 'Info' },
                { id: 'relations', label: 'Relations' },
                { id: 'powers', label: 'Powers' },
                { id: 'stakes', label: 'Stakes' },
                { id: 'locations', label: 'Locs' },
                { id: 'timeline', label: 'Time' },
                { id: 'comparison', label: 'Canon' },
                { id: 'knowledge', label: 'Know' },
                { id: 'edit', label: 'Edit' },
              ].map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setBibleTab(tab.id)}
                  className={`flex-1 px-1 py-2 text-xs font-medium transition-colors ${
                    bibleTab === tab.id
                      ? 'text-accent border-b-2 border-accent bg-white/5'
                      : 'text-gray-400 hover:text-white hover:bg-white/5'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Content - min-h-0 fixes flexbox overflow */}
            <div className="flex-1 min-h-0 overflow-y-auto p-4 custom-scrollbar">
              {bibleLoading ? (
                <div className="flex items-center justify-center h-32">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent"></div>
                </div>
              ) : !worldBible ? (
                <div className="text-gray-500 text-sm text-center py-8">
                  No World Bible data yet. Start a story to populate it.
                </div>
              ) : (
                <>
                  {/* Overview Tab */}
                  {bibleTab === 'overview' && (
                    <div className="space-y-4">
                      {/* Character Sheet */}
                      {worldBible.character_sheet && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-accent mb-2">Protagonist</h4>
                          <div className="text-sm text-gray-300">
                            <p><span className="text-gray-500">Name:</span> {worldBible.character_sheet.name || 'Unknown'}</p>
                            <p><span className="text-gray-500">Cape Name:</span> {worldBible.character_sheet.cape_name || 'None'}</p>
                            <p><span className="text-gray-500">Archetype:</span> {worldBible.character_sheet.archetype || 'Unknown'}</p>
                            {worldBible.character_sheet.status && (
                              <p><span className="text-gray-500">Status:</span> {
                                typeof worldBible.character_sheet.status === 'object'
                                  ? worldBible.character_sheet.status.condition || 'Normal'
                                  : worldBible.character_sheet.status
                              }</p>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Meta Info */}
                      {worldBible.meta && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-accent mb-2">Story Info</h4>
                          <div className="text-sm text-gray-300 space-y-1">
                            <p><span className="text-gray-500">Genre:</span> {worldBible.meta.genre || 'Not set'}</p>
                            <p><span className="text-gray-500">Theme:</span> {worldBible.meta.theme || 'Not set'}</p>
                            <p><span className="text-gray-500">Current Date:</span> {worldBible.meta.current_story_date || 'Not set'}</p>
                          </div>
                        </div>
                      )}

                      {/* Universes */}
                      {worldBible.meta?.universes && worldBible.meta.universes.length > 0 && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-accent mb-2">Universes</h4>
                          <div className="flex flex-wrap gap-2">
                            {worldBible.meta.universes.map((u, i) => (
                              <span key={i} className="px-2 py-1 bg-violet-500/20 text-violet-300 rounded text-xs">
                                {u}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Factions */}
                      {worldBible.world_state?.factions && Object.keys(worldBible.world_state.factions).length > 0 && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-accent mb-2">Factions & Organizations</h4>
                          <div className="space-y-3">
                            {Object.entries(worldBible.world_state.factions).filter(([_, faction]) => faction != null).map(([name, faction], i) => (
                              <div key={i} className="bg-black/30 rounded p-2">
                                <div className="flex items-center justify-between mb-1">
                                  <span className="text-sm font-medium text-violet-300">{name.replace(/_/g, ' ')}</span>
                                  {faction.type && (
                                    <span className="text-[10px] px-1.5 py-0.5 bg-violet-500/20 text-violet-400 rounded">
                                      {faction.type}
                                    </span>
                                  )}
                                </div>
                                {faction.description && (
                                  <p className="text-xs text-gray-400 mb-2">{faction.description}</p>
                                )}
                                {/* Members */}
                                {faction.complete_member_roster && faction.complete_member_roster.length > 0 && (
                                  <div className="mt-2">
                                    <p className="text-[10px] text-gray-500 uppercase mb-1">Members:</p>
                                    <div className="flex flex-wrap gap-1">
                                      {faction.complete_member_roster.slice(0, 8).map((member, j) => (
                                        <span key={j} className="text-[10px] bg-white/10 text-gray-300 px-1.5 py-0.5 rounded">
                                          {member.cape_name || member.name}
                                          {member.role === 'Leader' && ' 👑'}
                                        </span>
                                      ))}
                                      {faction.complete_member_roster.length > 8 && (
                                        <span className="text-[10px] text-gray-500">+{faction.complete_member_roster.length - 8} more</span>
                                      )}
                                    </div>
                                  </div>
                                )}
                                {/* Fallback to hierarchy/members list if no complete_member_roster */}
                                {!faction.complete_member_roster && faction.hierarchy && (
                                  <div className="mt-2">
                                    <p className="text-[10px] text-gray-500 uppercase mb-1">Hierarchy:</p>
                                    <p className="text-xs text-gray-400">{faction.hierarchy.join(' → ')}</p>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Character Voices */}
                      {worldBible.character_voices && Object.keys(worldBible.character_voices).length > 0 && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-emerald-400 mb-2">🗣️ Character Voices</h4>
                          <div className="space-y-3">
                            {Object.entries(worldBible.character_voices).slice(0, 6).map(([name, voice], i) => (
                              <div key={i} className="bg-black/30 rounded p-2">
                                <div className="flex items-center justify-between mb-1">
                                  <span className="text-sm font-medium text-emerald-300">{name}</span>
                                  {voice.vocabulary_level && (
                                    <span className="text-[10px] px-1.5 py-0.5 bg-emerald-500/20 text-emerald-400 rounded">
                                      {voice.vocabulary_level}
                                    </span>
                                  )}
                                </div>
                                {/* Speech Patterns - handle both string and array */}
                                {voice.speech_patterns && (
                                  <div className="flex flex-wrap gap-1 mb-2">
                                    {(Array.isArray(voice.speech_patterns)
                                      ? voice.speech_patterns
                                      : [voice.speech_patterns]
                                    ).slice(0, 4).map((pattern, j) => (
                                      <span key={j} className="text-[10px] bg-white/10 text-gray-400 px-1 py-0.5 rounded">
                                        {pattern}
                                      </span>
                                    ))}
                                  </div>
                                )}
                                {/* Verbal Tics */}
                                {voice.verbal_tics && (
                                  <p className="text-[10px] text-yellow-400/80 mb-1">
                                    💬 {typeof voice.verbal_tics === 'string' ? voice.verbal_tics : voice.verbal_tics.join(', ')}
                                  </p>
                                )}
                                {/* Example Dialogue - handle both field names */}
                                {(voice.dialogue_examples || voice.example_dialogue) && (
                                  <div className="text-xs text-gray-400 italic border-l-2 border-emerald-500/30 pl-2 mb-2">
                                    "{voice.dialogue_examples?.[0] || voice.example_dialogue}"
                                  </div>
                                )}
                                {/* Emotional Tells */}
                                {voice.emotional_tells && (
                                  <p className="text-[10px] text-pink-400/80 mb-1">
                                    😤 {voice.emotional_tells}
                                  </p>
                                )}
                                {/* Topics - handle both field name conventions and ensure arrays */}
                                {(() => {
                                  const toArray = (val) => Array.isArray(val) ? val : (typeof val === 'string' ? [val] : []);
                                  const discusses = toArray(voice.topics_they_discuss || voice.topics_to_discuss);
                                  const avoids = toArray(voice.topics_they_avoid || voice.topics_to_avoid);
                                  if (discusses.length === 0 && avoids.length === 0) return null;
                                  return (
                                    <div className="mt-2 flex flex-wrap gap-2 text-[10px]">
                                      {discusses.length > 0 && (
                                        <span className="text-green-400 bg-green-500/10 px-1 py-0.5 rounded"
                                              title={discusses.join(', ')}>
                                          ✓ discusses: {discusses.slice(0, 2).join(', ')}
                                        </span>
                                      )}
                                      {avoids.length > 0 && (
                                        <span className="text-red-400 bg-red-500/10 px-1 py-0.5 rounded"
                                              title={avoids.join(', ')}>
                                          ✗ avoids: {avoids.slice(0, 2).join(', ')}
                                        </span>
                                      )}
                                    </div>
                                  );
                                })()}
                              </div>
                            ))}
                            {Object.keys(worldBible.character_voices).length > 6 && (
                              <p className="text-xs text-gray-500 text-center">
                                +{Object.keys(worldBible.character_voices).length - 6} more characters...
                              </p>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Relations Tab - Comprehensive Relationships View */}
                  {bibleTab === 'relations' && (
                    <div className="space-y-4">
                      {/* Identities Section */}
                      {worldBible.character_sheet?.identities && Object.keys(worldBible.character_sheet.identities).length > 0 && (
                        <div className="bg-gradient-to-r from-cyan-500/10 to-violet-500/10 rounded-lg p-3 border border-cyan-500/20">
                          <h4 className="text-sm font-bold text-cyan-300 mb-3">🎭 Identities</h4>
                          <div className="space-y-3">
                            {Object.entries(worldBible.character_sheet.identities).map(([key, identity], i) => (
                              <div key={i} className="bg-black/30 rounded p-3">
                                <div className="flex items-center justify-between mb-2">
                                  <span className="text-sm font-bold text-cyan-200">{identity.name || key}</span>
                                  <div className="flex gap-1">
                                    {identity.type && (
                                      <span className="text-[10px] px-2 py-1 bg-cyan-500/30 text-cyan-300 rounded-full">
                                        {identity.type}
                                      </span>
                                    )}
                                    <span className={`text-[10px] px-2 py-1 rounded-full ${
                                      identity.is_public ? 'bg-green-500/30 text-green-300' : 'bg-red-500/30 text-red-300'
                                    }`}>
                                      {identity.is_public ? '🌐 Public' : '🔒 Secret'}
                                    </span>
                                  </div>
                                </div>
                                <div className="grid grid-cols-2 gap-2 text-xs">
                                  {identity.team_affiliation && (
                                    <div><span className="text-gray-500">Team:</span> <span className="text-gray-300">{identity.team_affiliation}</span></div>
                                  )}
                                  {identity.reputation && (
                                    <div><span className="text-gray-500">Rep:</span> <span className="text-gray-300">{identity.reputation}</span></div>
                                  )}
                                  {identity.base_of_operations && (
                                    <div><span className="text-gray-500">Base:</span> <span className="text-gray-300">{identity.base_of_operations}</span></div>
                                  )}
                                </div>
                                {identity.known_by && identity.known_by.length > 0 && (
                                  <div className="mt-2">
                                    <p className="text-[10px] text-gray-500 mb-1">Known by:</p>
                                    <div className="flex flex-wrap gap-1">
                                      {identity.known_by.map((p, j) => (
                                        <span key={j} className="text-[10px] bg-green-500/20 text-green-400 px-1.5 py-0.5 rounded">{p}</span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                {identity.suspected_by && identity.suspected_by.length > 0 && (
                                  <div className="mt-2">
                                    <p className="text-[10px] text-gray-500 mb-1">Suspected by:</p>
                                    <div className="flex flex-wrap gap-1">
                                      {identity.suspected_by.map((p, j) => (
                                        <span key={j} className="text-[10px] bg-yellow-500/20 text-yellow-400 px-1.5 py-0.5 rounded">{p}</span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                                {identity.vulnerabilities && identity.vulnerabilities.length > 0 && (
                                  <div className="mt-2">
                                    <p className="text-[10px] text-gray-500 mb-1">⚠️ Vulnerabilities:</p>
                                    <div className="flex flex-wrap gap-1">
                                      {identity.vulnerabilities.map((v, j) => (
                                        <span key={j} className="text-[10px] bg-red-500/20 text-red-400 px-1.5 py-0.5 rounded">
                                          {typeof v === 'object' ? (v.name || JSON.stringify(v)) : v}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Relationships */}
                      {worldBible.character_sheet?.relationships && Object.keys(worldBible.character_sheet.relationships).length > 0 && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-pink-400 mb-3">👥 Relationships</h4>
                          <div className="space-y-2">
                            {/* Family relationships (object format with type: family) */}
                            {Object.entries(worldBible.character_sheet.relationships)
                              .filter(([_, rel]) => rel && typeof rel === 'object' && rel.type === 'family')
                              .length > 0 && (
                              <>
                                <h5 className="text-xs font-bold text-pink-300 mb-2">👨‍👩‍👧‍👦 Family</h5>
                                {Object.entries(worldBible.character_sheet.relationships)
                                  .filter(([_, rel]) => rel && typeof rel === 'object' && rel.type === 'family')
                                  .map(([name, rel], i) => (
                                    <div key={i} className="bg-black/30 rounded p-2">
                                      <div className="flex items-center justify-between mb-1">
                                        <span className="text-sm font-medium text-pink-300">{name}</span>
                                        <div className="flex gap-1">
                                          {rel.relation && (
                                            <span className="text-[10px] px-1.5 py-0.5 bg-pink-500/20 text-pink-300 rounded">
                                              {rel.relation}
                                            </span>
                                          )}
                                          {rel.family_branch && (
                                            <span className="text-[10px] px-1.5 py-0.5 bg-violet-500/20 text-violet-300 rounded">
                                              {rel.family_branch}
                                            </span>
                                          )}
                                        </div>
                                      </div>
                                      <div className="flex flex-wrap gap-2 text-[10px] mb-1">
                                        {rel.trust && (
                                          <span className={`px-1.5 py-0.5 rounded ${
                                            rel.trust === 'complete' || rel.trust === 'high' ? 'bg-green-500/20 text-green-400' :
                                            rel.trust === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                                            'bg-red-500/20 text-red-400'
                                          }`}>
                                            Trust: {rel.trust}
                                          </span>
                                        )}
                                        {rel.knows_secret_identity !== undefined && (
                                          <span className={`px-1.5 py-0.5 rounded ${
                                            rel.knows_secret_identity ? 'bg-cyan-500/20 text-cyan-400' : 'bg-gray-500/20 text-gray-400'
                                          }`}>
                                            {rel.knows_secret_identity ? '🎭 Knows identity' : '❓ Unaware'}
                                          </span>
                                        )}
                                      </div>
                                      {rel.dynamics && <p className="text-[10px] text-gray-400 italic">{rel.dynamics}</p>}
                                      {rel.role_in_story && <p className="text-[10px] text-gray-500">Role: {rel.role_in_story}</p>}
                                    </div>
                                  ))}
                              </>
                            )}

                            {/* Other object-format relationships */}
                            {Object.entries(worldBible.character_sheet.relationships)
                              .filter(([_, rel]) => rel && typeof rel === 'object' && rel.type !== 'family')
                              .length > 0 && (
                              <>
                                <h5 className="text-xs font-bold text-blue-300 mt-3 mb-2">🤝 Allies & Others</h5>
                                {Object.entries(worldBible.character_sheet.relationships)
                                  .filter(([_, rel]) => rel && typeof rel === 'object' && rel.type !== 'family')
                                  .map(([name, rel], i) => (
                                    <div key={i} className="bg-black/30 rounded p-2">
                                      <div className="flex items-center justify-between mb-1">
                                        <span className="text-sm font-medium text-blue-300">{name}</span>
                                        {rel.type && (
                                          <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                                            rel.type === 'ally' ? 'bg-green-500/20 text-green-300' :
                                            rel.type === 'enemy' ? 'bg-red-500/20 text-red-300' :
                                            'bg-gray-500/20 text-gray-300'
                                          }`}>
                                            {rel.type}
                                          </span>
                                        )}
                                      </div>
                                      {rel.trust && (
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                                          rel.trust === 'complete' || rel.trust === 'high' ? 'bg-green-500/20 text-green-400' :
                                          rel.trust === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                                          'bg-red-500/20 text-red-400'
                                        }`}>
                                          Trust: {rel.trust}
                                        </span>
                                      )}
                                      {rel.dynamics && <p className="text-[10px] text-gray-400 italic mt-1">{rel.dynamics}</p>}
                                    </div>
                                  ))}
                              </>
                            )}

                            {/* String-format relationships (legacy format) */}
                            {Object.entries(worldBible.character_sheet.relationships)
                              .filter(([_, rel]) => typeof rel === 'string')
                              .length > 0 && (
                              <>
                                <h5 className="text-xs font-bold text-gray-400 mt-3 mb-2">📋 Relationship Notes</h5>
                                {Object.entries(worldBible.character_sheet.relationships)
                                  .filter(([_, rel]) => typeof rel === 'string')
                                  .map(([name, description], i) => (
                                    <div key={i} className="bg-black/30 rounded p-2">
                                      <span className="text-sm font-medium text-gray-300">{name}</span>
                                      <p className="text-[10px] text-gray-400 mt-1">{description}</p>
                                    </div>
                                  ))}
                              </>
                            )}
                          </div>
                        </div>
                      )}

                      {/* World State Characters */}
                      {worldBible.world_state?.characters && Object.keys(worldBible.world_state.characters).length > 0 && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-violet-400 mb-3">🎭 Known Characters</h4>
                          <div className="grid grid-cols-2 gap-2">
                            {Object.entries(worldBible.world_state.characters).slice(0, 12).map(([name, char], i) => (
                              <div key={i} className="bg-black/30 rounded p-2">
                                <p className="text-xs font-medium text-violet-300">{name.replace(/_/g, ' ')}</p>
                                {char && typeof char === 'object' && char.cape_name && (
                                  <p className="text-[10px] text-gray-500">{char.cape_name}</p>
                                )}
                                {char && typeof char === 'object' && char.affiliation && (
                                  <p className="text-[10px] text-gray-500">{char.affiliation}</p>
                                )}
                              </div>
                            ))}
                          </div>
                          {Object.keys(worldBible.world_state.characters).length > 12 && (
                            <p className="text-xs text-gray-500 text-center mt-2">
                              +{Object.keys(worldBible.world_state.characters).length - 12} more...
                            </p>
                          )}
                        </div>
                      )}

                      {!worldBible.character_sheet?.relationships && !worldBible.character_sheet?.identities && (
                        <div className="text-gray-500 text-sm text-center py-8">
                          No relationships or identities tracked yet.
                        </div>
                      )}
                    </div>
                  )}

                  {/* Powers Tab */}
                  {bibleTab === 'powers' && (
                    <div className="space-y-4">
                      {worldBible.power_origins?.sources && Object.keys(worldBible.power_origins.sources).length > 0 ? (
                        Object.entries(worldBible.power_origins.sources).map(([powerKey, power], i) => (
                          <div key={powerKey} className="bg-white/5 rounded-lg p-3 border border-white/5">
                            <h4 className="text-sm font-bold text-accent">{power.power_name || powerKey || 'Unknown Power'}</h4>
                            {power.original_wielder && (
                              <p className="text-xs text-gray-400 mb-2">
                                From: {power.original_wielder}
                                {power.source_universe && <span> ({power.source_universe})</span>}
                              </p>
                            )}

                            {power.canon_techniques && power.canon_techniques.length > 0 && (
                              <div className="mt-2">
                                <p className="text-xs text-gray-500 uppercase mb-1">Techniques:</p>
                                <div className="space-y-1">
                                  {power.canon_techniques.slice(0, 5).map((tech, j) => (
                                    <div key={j} className="text-xs bg-black/30 rounded px-2 py-1">
                                      <span className="text-violet-300">{tech.name}</span>
                                      {tech.limitations && (
                                        <span className="text-gray-500 ml-2">({tech.limitations})</span>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {power.oc_current_mastery && (
                              <p className="text-xs text-gray-400 mt-2">
                                <span className="text-gray-500">Mastery:</span> {power.oc_current_mastery}
                              </p>
                            )}
                          </div>
                        ))
                      ) : (
                        <div className="text-gray-500 text-sm text-center py-4">
                          No power origins documented yet.
                        </div>
                      )}

                      {/* Character Powers */}
                      {worldBible.character_sheet?.powers && Object.keys(worldBible.character_sheet.powers).length > 0 && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-accent mb-2">Current Abilities</h4>
                          <div className="space-y-2">
                            {Object.entries(worldBible.character_sheet.powers).map(([name, desc], i) => (
                              <div key={i} className="text-xs">
                                <div className="flex items-center gap-2">
                                  <span className="text-violet-300 font-semibold">{name}</span>
                                  {typeof desc === 'object' && desc?.mastery && (
                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-900/50 text-violet-300">{desc.mastery}</span>
                                  )}
                                </div>
                                {typeof desc === 'string' ? (
                                  <p className="text-gray-400 mt-0.5">{desc}</p>
                                ) : typeof desc === 'object' ? (
                                  <div className="text-gray-400 mt-0.5 pl-2 border-l border-white/10">
                                    {desc.type && <p><span className="text-gray-500">Type:</span> {desc.type}</p>}
                                    {(desc.techniques || desc.abilities) && (
                                      <p className="text-gray-500">
                                        {desc.techniques ? 'Techniques: ' : 'Abilities: '}
                                        <span className="text-gray-400">
                                          {(desc.techniques || desc.abilities).map(t =>
                                            typeof t === 'string' ? t : (t.name || JSON.stringify(t))
                                          ).join(', ')}
                                        </span>
                                      </p>
                                    )}
                                  </div>
                                ) : null}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Stakes Tab */}
                  {bibleTab === 'stakes' && (
                    <div className="space-y-4">
                      {/* Costs Paid */}
                      {safeArray(worldBible.stakes_and_consequences?.costs_paid).length > 0 && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-red-400 mb-2">Costs Paid</h4>
                          <div className="space-y-2">
                            {safeArray(worldBible.stakes_and_consequences?.costs_paid).slice(-5).map((cost, i) => {
                              // Handle both string and object formats
                              const costText = typeof cost === 'string' ? cost : cost.cost;
                              const severity = typeof cost === 'object' ? cost.severity : 'moderate';
                              return (
                                <div key={i} className="text-xs bg-red-500/10 rounded px-2 py-1 border border-red-500/20">
                                  <span className={`inline-block px-1 rounded mr-2 ${
                                    severity === 'severe' || severity === 'permanent' ? 'bg-red-500/30 text-red-300' :
                                    severity === 'moderate' ? 'bg-orange-500/30 text-orange-300' :
                                    'bg-yellow-500/30 text-yellow-300'
                                  }`}>
                                    {severity || 'minor'}
                                  </span>
                                  {costText}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {/* Near Misses */}
                      {safeArray(worldBible.stakes_and_consequences?.near_misses).length > 0 && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-yellow-400 mb-2">Near Misses</h4>
                          <div className="space-y-2">
                            {safeArray(worldBible.stakes_and_consequences?.near_misses).slice(-3).map((miss, i) => {
                              // Handle both string and object formats
                              const missText = typeof miss === 'string' ? miss : miss.what_almost_happened;
                              const savedBy = typeof miss === 'object' ? miss.saved_by : null;
                              return (
                                <div key={i} className="text-xs bg-yellow-500/10 rounded px-2 py-1 border border-yellow-500/20">
                                  <p className="text-yellow-200">{missText}</p>
                                  {savedBy && (
                                    <p className="text-gray-400 mt-1">Saved by: {savedBy}</p>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {/* Pending Consequences */}
                      {safeArray(worldBible.stakes_and_consequences?.pending_consequences).length > 0 && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-orange-400 mb-2">Pending Consequences</h4>
                          <div className="space-y-2">
                            {safeArray(worldBible.stakes_and_consequences?.pending_consequences).map((cons, i) => {
                              // Handle both string and object formats
                              const consText = typeof cons === 'string' ? cons : cons.predicted_consequence;
                              const dueBy = typeof cons === 'object' ? cons.due_by : null;
                              return (
                                <div key={i} className="text-xs bg-orange-500/10 rounded px-2 py-1 border border-orange-500/20">
                                  <p className="text-orange-200">{consText}</p>
                                  {dueBy && <p className="text-gray-500 mt-1">Due: {dueBy}</p>}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {/* Power Usage Debt */}
                      {worldBible.stakes_and_consequences?.power_usage_debt &&
                       Object.keys(worldBible.stakes_and_consequences.power_usage_debt || {}).length > 0 && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-purple-400 mb-2">Power Strain</h4>
                          <div className="space-y-2">
                            {Object.entries(worldBible.stakes_and_consequences.power_usage_debt || {}).map(([power, debt], i) => {
                              const strainLevel = typeof debt === 'string' ? debt : debt?.strain_level || 'low';
                              return (
                                <div key={i} className="text-xs flex justify-between items-center">
                                  <span className="text-gray-300">{power}</span>
                                  <span className={`px-2 py-0.5 rounded ${
                                    strainLevel === 'critical' ? 'bg-red-500/30 text-red-300' :
                                    strainLevel === 'high' ? 'bg-orange-500/30 text-orange-300' :
                                    strainLevel === 'medium' ? 'bg-yellow-500/30 text-yellow-300' :
                                    'bg-green-500/30 text-green-300'
                                  }`}>
                                    {strainLevel}
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {(!worldBible.stakes_and_consequences ||
                        (!safeArray(worldBible.stakes_and_consequences.costs_paid).length &&
                         !safeArray(worldBible.stakes_and_consequences.near_misses).length &&
                         !safeArray(worldBible.stakes_and_consequences.pending_consequences).length &&
                         !Object.keys(worldBible.stakes_and_consequences.power_usage_debt || {}).length)) && (
                        <div className="text-gray-500 text-sm text-center py-4">
                          No stakes recorded yet.
                        </div>
                      )}
                    </div>
                  )}

                  {/* Locations Tab */}
                  {bibleTab === 'locations' && (
                    <div className="space-y-4">
                      {/* Territory Map Summary */}
                      {worldBible.world_state?.territory_map && Object.keys(worldBible.world_state.territory_map).length > 0 && (
                        <div className="bg-gradient-to-r from-violet-500/10 to-cyan-500/10 rounded-lg p-3 border border-violet-500/20">
                          <h4 className="text-sm font-bold text-violet-300 mb-2">Territory Control</h4>
                          <div className="grid grid-cols-2 gap-2">
                            {Object.entries(worldBible.world_state.territory_map).map(([area, faction], i) => (
                              <div key={i} className="flex items-center justify-between bg-black/30 rounded px-2 py-1">
                                <span className="text-xs text-gray-300 truncate">{area}</span>
                                <span className={`text-[10px] px-1.5 py-0.5 rounded ml-1 ${
                                  faction === 'Contested' ? 'bg-red-500/30 text-red-300' :
                                  faction === 'Empire Eighty-Eight' ? 'bg-orange-500/30 text-orange-300' :
                                  faction === 'ABB' ? 'bg-green-500/30 text-green-300' :
                                  faction === 'PRT' ? 'bg-blue-500/30 text-blue-300' :
                                  faction === 'Merchants' ? 'bg-yellow-500/30 text-yellow-300' :
                                  'bg-gray-500/30 text-gray-300'
                                }`}>
                                  {faction}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Location Cards */}
                      {worldBible.world_state?.locations && Object.keys(worldBible.world_state.locations).length > 0 ? (
                        <div className="space-y-3">
                          {Object.entries(worldBible.world_state.locations).map(([name, loc], i) => (
                            <div key={i} className="bg-white/5 rounded-lg p-3 border border-white/5">
                              <div className="flex items-start justify-between mb-2">
                                <div>
                                  <h5 className="text-sm font-bold text-cyan-300">{name.replace(/_/g, ' ')}</h5>
                                  {loc.type && (
                                    <span className="text-[10px] text-gray-500 uppercase">{loc.type}</span>
                                  )}
                                </div>
                                {loc.controlled_by && (
                                  <span className="text-[10px] px-1.5 py-0.5 bg-violet-500/20 text-violet-300 rounded">
                                    {loc.controlled_by}
                                  </span>
                                )}
                              </div>

                              {/* Atmosphere */}
                              {loc.atmosphere && (
                                <p className="text-xs text-gray-400 italic mb-2">"{loc.atmosphere}"</p>
                              )}

                              {/* Security & Status Row */}
                              {(loc.security_level || loc.current_state) && (
                                <div className="flex flex-wrap gap-2 mb-2">
                                  {loc.security_level && (
                                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                                      loc.security_level === 'fortress' || loc.security_level === 'high' ? 'bg-red-500/30 text-red-300' :
                                      loc.security_level === 'medium' ? 'bg-yellow-500/30 text-yellow-300' :
                                      loc.security_level === 'low' ? 'bg-green-500/30 text-green-300' :
                                      'bg-gray-500/30 text-gray-300'
                                    }`}>
                                      🔒 {loc.security_level}
                                    </span>
                                  )}
                                  {loc.current_state && loc.current_state !== 'Normal' && (
                                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                                      loc.current_state === 'destroyed' ? 'bg-red-500/30 text-red-300' :
                                      loc.current_state === 'damaged' ? 'bg-orange-500/30 text-orange-300' :
                                      'bg-blue-500/30 text-blue-300'
                                    }`}>
                                      📍 {loc.current_state}
                                    </span>
                                  )}
                                </div>
                              )}

                              {/* Key Features */}
                              {loc.key_features && loc.key_features.length > 0 && (
                                <div className="mb-2">
                                  <p className="text-[10px] text-gray-500 uppercase mb-1">Features</p>
                                  <div className="flex flex-wrap gap-1">
                                    {loc.key_features.slice(0, 6).map((feat, j) => (
                                      <span key={j} className="text-[10px] bg-cyan-500/20 text-cyan-300 px-1.5 py-0.5 rounded">
                                        {typeof feat === 'object' ? (feat.name || JSON.stringify(feat)) : feat}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Typical Occupants */}
                              {loc.typical_occupants && loc.typical_occupants.length > 0 && (
                                <div className="mb-2">
                                  <p className="text-[10px] text-gray-500 uppercase mb-1">Usually Found Here</p>
                                  <div className="flex flex-wrap gap-1">
                                    {loc.typical_occupants.slice(0, 5).map((occ, j) => (
                                      <span key={j} className="text-[10px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded">
                                        {typeof occ === 'object' ? (occ.name || JSON.stringify(occ)) : occ}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Canon Events Here */}
                              {loc.canon_events_here && loc.canon_events_here.length > 0 && (
                                <div className="mb-2">
                                  <p className="text-[10px] text-gray-500 uppercase mb-1">Canon Events</p>
                                  <div className="flex flex-wrap gap-1">
                                    {loc.canon_events_here.slice(0, 3).map((evt, j) => (
                                      <span key={j} className="text-[10px] bg-violet-500/20 text-violet-300 px-1.5 py-0.5 rounded">
                                        {typeof evt === 'object' ? (evt.event || evt.name || JSON.stringify(evt)) : evt}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Story Hooks */}
                              {loc.story_hooks && loc.story_hooks.length > 0 && (
                                <div className="mb-2">
                                  <p className="text-[10px] text-gray-500 uppercase mb-1">Story Hooks</p>
                                  <ul className="space-y-1">
                                    {loc.story_hooks.slice(0, 3).map((hook, j) => (
                                      <li key={j} className="text-xs text-yellow-400/80 flex items-start gap-1">
                                        <span className="text-yellow-500">•</span>
                                        {typeof hook === 'object' ? (hook.description || hook.name || JSON.stringify(hook)) : hook}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}

                              {/* Adjacent Areas */}
                              {loc.adjacent_to && loc.adjacent_to.length > 0 && (
                                <div className="pt-2 border-t border-white/5">
                                  <p className="text-[10px] text-gray-500">
                                    Adjacent to: {loc.adjacent_to.slice(0, 3).join(', ')}
                                  </p>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-gray-500 text-sm text-center py-4">
                          No locations documented yet. Research locations to populate this tab.
                        </div>
                      )}
                    </div>
                  )}

                  {/* Timeline Tab */}
                  {bibleTab === 'timeline' && (
                    <div className="space-y-4">
                      {/* Current Position */}
                      {worldBible.canon_timeline?.current_position && (
                        <div className="bg-violet-500/10 rounded-lg p-3 border border-violet-500/20">
                          <h4 className="text-sm font-bold text-violet-300 mb-1">Current Position</h4>
                          <p className="text-sm text-gray-300">{worldBible.canon_timeline.current_position}</p>
                        </div>
                      )}

                      {/* Upcoming Canon Events */}
                      {worldBible.canon_timeline?.events && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-accent mb-2">Upcoming Canon Events</h4>
                          <div className="space-y-2">
                            {worldBible.canon_timeline.events
                              .filter(e => e.status === 'upcoming')
                              .slice(0, 5)
                              .map((event, i) => (
                                <div key={i} className="text-xs bg-black/30 rounded px-2 py-1">
                                  <span className="text-gray-400">[{event.date || '?'}]</span>{' '}
                                  <span className="text-gray-200">{event.event}</span>
                                  {event.importance === 'major' && (
                                    <span className="ml-2 text-red-400">●</span>
                                  )}
                                </div>
                              ))}
                          </div>
                        </div>
                      )}

                      {/* Divergences */}
                      {worldBible.divergences?.list && worldBible.divergences.list.length > 0 && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-orange-400 mb-2">Canon Divergences</h4>
                          <div className="space-y-2">
                            {worldBible.divergences.list.slice(-3).map((div, i) => (
                              <div key={i} className="text-xs bg-orange-500/10 rounded px-2 py-1 border border-orange-500/20">
                                <p className="text-gray-400 line-through">{div.canon_event}</p>
                                <p className="text-orange-200">→ {div.what_changed}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Story Events */}
                      {worldBible.story_timeline?.events && worldBible.story_timeline.events.length > 0 && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-accent mb-2">Story Events</h4>
                          <div className="space-y-1">
                            {worldBible.story_timeline.events.slice(-5).map((event, i) => (
                              <div key={i} className="text-xs">
                                <span className="text-gray-500">[{event.date || '?'}]</span>{' '}
                                <span className="text-gray-300">{event.event}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Comparison Tab - Canon vs Story Timeline */}
                  {bibleTab === 'comparison' && (
                    <TimelineComparison storyId={activeGameId} />
                  )}

                  {/* Knowledge Tab */}
                  {bibleTab === 'knowledge' && (
                    <div className="space-y-4">
                      {/* Meta-Knowledge Forbidden */}
                      {worldBible.knowledge_boundaries?.meta_knowledge_forbidden?.length > 0 && (
                        <div className="bg-red-500/10 rounded-lg p-3 border border-red-500/20">
                          <h4 className="text-sm font-bold text-red-400 mb-2">🚫 Forbidden Knowledge</h4>
                          <p className="text-xs text-gray-400 mb-2">Characters cannot know or discuss these concepts:</p>
                          <div className="flex flex-wrap gap-1">
                            {worldBible.knowledge_boundaries.meta_knowledge_forbidden.map((item, i) => (
                              <span key={i} className="text-xs bg-red-500/20 text-red-300 px-2 py-0.5 rounded">
                                {item}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Character Secrets */}
                      {worldBible.knowledge_boundaries?.character_secrets &&
                       Object.keys(worldBible.knowledge_boundaries.character_secrets).length > 0 && (
                        <div className="bg-purple-500/10 rounded-lg p-3 border border-purple-500/20">
                          <h4 className="text-sm font-bold text-purple-400 mb-2">🤫 Character Secrets</h4>
                          <div className="space-y-2">
                            {Object.entries(worldBible.knowledge_boundaries.character_secrets).map(([char, data], i) => (
                              <div key={i} className="text-xs bg-black/30 rounded p-2">
                                <p className="text-purple-300 font-medium">{char.replace(/_/g, ' ')}</p>
                                <p className="text-gray-400 mt-1">{typeof data === 'object' ? data.secret : data}</p>
                                {data.absolutely_hidden_from?.length > 0 && (
                                  <p className="text-red-400 mt-1 text-[10px]">
                                    Hidden from: {data.absolutely_hidden_from.join(', ')}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Character Knowledge Limits */}
                      {worldBible.knowledge_boundaries?.character_knowledge_limits &&
                       Object.keys(worldBible.knowledge_boundaries.character_knowledge_limits).length > 0 && (
                        <div className="bg-blue-500/10 rounded-lg p-3 border border-blue-500/20">
                          <h4 className="text-sm font-bold text-blue-400 mb-2">📚 Character Knowledge</h4>
                          <div className="space-y-2">
                            {Object.entries(worldBible.knowledge_boundaries.character_knowledge_limits).map(([char, data], i) => (
                              <div key={i} className="text-xs bg-black/30 rounded p-2">
                                <p className="text-blue-300 font-medium">{char.replace(/_/g, ' ')}</p>
                                {data.knows?.length > 0 && (
                                  <div className="mt-1">
                                    <span className="text-green-400">Knows: </span>
                                    <span className="text-gray-400">{data.knows.slice(0, 5).join(', ')}</span>
                                  </div>
                                )}
                                {data.doesnt_know?.length > 0 && (
                                  <div className="mt-1">
                                    <span className="text-red-400">Doesn't know: </span>
                                    <span className="text-gray-400">{data.doesnt_know.slice(0, 5).join(', ')}</span>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Common Knowledge */}
                      {worldBible.knowledge_boundaries?.common_knowledge?.length > 0 && (
                        <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                          <h4 className="text-sm font-bold text-gray-300 mb-2">🌍 Common Knowledge</h4>
                          <p className="text-xs text-gray-400 mb-2">Public facts everyone in-universe knows:</p>
                          <div className="flex flex-wrap gap-1">
                            {worldBible.knowledge_boundaries.common_knowledge.map((item, i) => (
                              <span key={i} className="text-xs bg-white/10 text-gray-300 px-2 py-0.5 rounded">
                                {item}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Empty state */}
                      {(!worldBible.knowledge_boundaries ||
                        (!worldBible.knowledge_boundaries.meta_knowledge_forbidden?.length &&
                         !Object.keys(worldBible.knowledge_boundaries.character_secrets || {}).length &&
                         !Object.keys(worldBible.knowledge_boundaries.character_knowledge_limits || {}).length)) && (
                        <div className="text-gray-500 text-sm text-center py-4">
                          No knowledge boundaries set yet. Run /research to populate.
                        </div>
                      )}
                    </div>
                  )}

                  {/* Edit Tab */}
                  {bibleTab === 'edit' && (
                    <div className="space-y-4">
                      <div className="text-xs text-gray-400 mb-4">
                        Click any field to edit. Changes are saved immediately.
                      </div>

                      {/* Character Sheet Editing */}
                      <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                        <h4 className="text-sm font-bold text-accent mb-3">Character Sheet</h4>

                        {/* Name */}
                        <div className="mb-3">
                          <label className="text-xs text-gray-500 block mb-1">Name</label>
                          {editingField === 'character_sheet.name' ? (
                            <div className="flex gap-2">
                              <input
                                type="text"
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                                className="flex-1 bg-black/40 border border-white/20 rounded px-2 py-1 text-sm text-white"
                                autoFocus
                              />
                              <button
                                onClick={() => saveBibleEdit('character_sheet.name', editValue)}
                                className="px-2 py-1 bg-accent text-black rounded text-xs"
                              >
                                Save
                              </button>
                              <button
                                onClick={() => setEditingField(null)}
                                className="px-2 py-1 bg-white/10 rounded text-xs"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <div
                              onClick={() => startEditing('character_sheet.name', worldBible?.character_sheet?.name)}
                              className="text-sm text-gray-200 bg-black/20 rounded px-2 py-1 cursor-pointer hover:bg-black/40 transition-colors"
                            >
                              {worldBible?.character_sheet?.name || 'Click to set...'}
                            </div>
                          )}
                        </div>

                        {/* Cape Name */}
                        <div className="mb-3">
                          <label className="text-xs text-gray-500 block mb-1">Cape Name</label>
                          {editingField === 'character_sheet.cape_name' ? (
                            <div className="flex gap-2">
                              <input
                                type="text"
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                                className="flex-1 bg-black/40 border border-white/20 rounded px-2 py-1 text-sm text-white"
                                autoFocus
                              />
                              <button
                                onClick={() => saveBibleEdit('character_sheet.cape_name', editValue)}
                                className="px-2 py-1 bg-accent text-black rounded text-xs"
                              >
                                Save
                              </button>
                              <button
                                onClick={() => setEditingField(null)}
                                className="px-2 py-1 bg-white/10 rounded text-xs"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <div
                              onClick={() => startEditing('character_sheet.cape_name', worldBible?.character_sheet?.cape_name)}
                              className="text-sm text-gray-200 bg-black/20 rounded px-2 py-1 cursor-pointer hover:bg-black/40 transition-colors"
                            >
                              {worldBible?.character_sheet?.cape_name || 'Click to set...'}
                            </div>
                          )}
                        </div>

                        {/* Archetype */}
                        <div className="mb-3">
                          <label className="text-xs text-gray-500 block mb-1">Archetype</label>
                          {editingField === 'character_sheet.archetype' ? (
                            <div className="flex gap-2">
                              <input
                                type="text"
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                                className="flex-1 bg-black/40 border border-white/20 rounded px-2 py-1 text-sm text-white"
                                autoFocus
                              />
                              <button
                                onClick={() => saveBibleEdit('character_sheet.archetype', editValue)}
                                className="px-2 py-1 bg-accent text-black rounded text-xs"
                              >
                                Save
                              </button>
                              <button
                                onClick={() => setEditingField(null)}
                                className="px-2 py-1 bg-white/10 rounded text-xs"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <div
                              onClick={() => startEditing('character_sheet.archetype', worldBible?.character_sheet?.archetype)}
                              className="text-sm text-gray-200 bg-black/20 rounded px-2 py-1 cursor-pointer hover:bg-black/40 transition-colors"
                            >
                              {worldBible?.character_sheet?.archetype || 'Click to set...'}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Meta Editing */}
                      <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                        <h4 className="text-sm font-bold text-accent mb-3">Story Meta</h4>

                        {/* Genre */}
                        <div className="mb-3">
                          <label className="text-xs text-gray-500 block mb-1">Genre</label>
                          {editingField === 'meta.genre' ? (
                            <div className="flex gap-2">
                              <input
                                type="text"
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                                className="flex-1 bg-black/40 border border-white/20 rounded px-2 py-1 text-sm text-white"
                                autoFocus
                              />
                              <button
                                onClick={() => saveBibleEdit('meta.genre', editValue)}
                                className="px-2 py-1 bg-accent text-black rounded text-xs"
                              >
                                Save
                              </button>
                              <button
                                onClick={() => setEditingField(null)}
                                className="px-2 py-1 bg-white/10 rounded text-xs"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <div
                              onClick={() => startEditing('meta.genre', worldBible?.meta?.genre)}
                              className="text-sm text-gray-200 bg-black/20 rounded px-2 py-1 cursor-pointer hover:bg-black/40 transition-colors"
                            >
                              {worldBible?.meta?.genre || 'Click to set...'}
                            </div>
                          )}
                        </div>

                        {/* Theme */}
                        <div className="mb-3">
                          <label className="text-xs text-gray-500 block mb-1">Theme</label>
                          {editingField === 'meta.theme' ? (
                            <div className="flex gap-2">
                              <input
                                type="text"
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                                className="flex-1 bg-black/40 border border-white/20 rounded px-2 py-1 text-sm text-white"
                                autoFocus
                              />
                              <button
                                onClick={() => saveBibleEdit('meta.theme', editValue)}
                                className="px-2 py-1 bg-accent text-black rounded text-xs"
                              >
                                Save
                              </button>
                              <button
                                onClick={() => setEditingField(null)}
                                className="px-2 py-1 bg-white/10 rounded text-xs"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <div
                              onClick={() => startEditing('meta.theme', worldBible?.meta?.theme)}
                              className="text-sm text-gray-200 bg-black/20 rounded px-2 py-1 cursor-pointer hover:bg-black/40 transition-colors"
                            >
                              {worldBible?.meta?.theme || 'Click to set...'}
                            </div>
                          )}
                        </div>

                        {/* Current Story Date */}
                        <div className="mb-3">
                          <label className="text-xs text-gray-500 block mb-1">Current Story Date</label>
                          {editingField === 'meta.current_story_date' ? (
                            <div className="flex gap-2">
                              <input
                                type="text"
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                                className="flex-1 bg-black/40 border border-white/20 rounded px-2 py-1 text-sm text-white"
                                placeholder="YYYY-MM-DD"
                                autoFocus
                              />
                              <button
                                onClick={() => saveBibleEdit('meta.current_story_date', editValue)}
                                className="px-2 py-1 bg-accent text-black rounded text-xs"
                              >
                                Save
                              </button>
                              <button
                                onClick={() => setEditingField(null)}
                                className="px-2 py-1 bg-white/10 rounded text-xs"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <div
                              onClick={() => startEditing('meta.current_story_date', worldBible?.meta?.current_story_date)}
                              className="text-sm text-gray-200 bg-black/20 rounded px-2 py-1 cursor-pointer hover:bg-black/40 transition-colors"
                            >
                              {worldBible?.meta?.current_story_date || 'Click to set...'}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="bg-white/5 rounded-lg p-3 border border-white/5">
                        <h4 className="text-sm font-bold text-accent mb-3">Actions</h4>
                        <button
                          onClick={() => {
                            if (refreshBible) refreshBible();
                          }}
                          className="w-full py-2 bg-white/10 hover:bg-white/20 rounded text-sm text-gray-300 transition-colors"
                        >
                          🔄 Refresh Bible
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Bible Toggle Button (Fixed) */}
      <button
        onClick={() => setShowBiblePanel(!showBiblePanel)}
        className={`fixed right-4 top-1/2 -translate-y-1/2 z-30 p-3 rounded-full transition-all shadow-lg ${
          showBiblePanel
            ? 'bg-accent text-black'
            : 'bg-white/10 hover:bg-white/20 text-white border border-white/10'
        }`}
        title="Toggle World Bible"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
        </svg>
      </button>

      {/* World Bible Editor Button (Fixed) */}
      <button
        onClick={() => setShowWorldBibleEditor(true)}
        className="fixed right-4 top-1/2 translate-y-8 z-30 p-3 rounded-full transition-all shadow-lg bg-violet-500/20 hover:bg-violet-500/40 text-violet-300 border border-violet-500/30"
        title="Open World Bible Editor"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
        </svg>
      </button>

      {/* World Bible Editor Modal */}
      <WorldBibleEditor
        isOpen={showWorldBibleEditor}
        onClose={() => setShowWorldBibleEditor(false)}
        worldBible={worldBible}
        activeGameId={activeGameId}
        history={history}
        refreshBible={refreshBible}
      />

      {/* Branch Creation Modal */}
      <AnimatePresence>
        {showBranchModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4"
            onClick={() => setShowBranchModal(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="bg-[#0a0a0c] border border-white/10 rounded-2xl p-6 max-w-md w-full shadow-2xl"
              onClick={e => e.stopPropagation()}
            >
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-xl font-bold text-white flex items-center gap-2">
                  <svg className="w-5 h-5 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                  </svg>
                  Create Branch
                </h3>
                <button
                  onClick={() => setShowBranchModal(false)}
                  className="p-1 hover:bg-white/10 rounded transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <p className="text-sm text-gray-400 mb-4">
                Create a branch to explore an alternate path. The current story state will be copied to a new timeline.
              </p>

              <div className="mb-4">
                <label className="text-xs text-gray-500 block mb-2">Branch Name</label>
                <input
                  type="text"
                  value={newBranchName}
                  onChange={(e) => setNewBranchName(e.target.value)}
                  placeholder="e.g., What if I chose Option B?"
                  className="w-full bg-black/40 border border-white/20 rounded-lg px-4 py-2 text-white placeholder:text-gray-600 focus:outline-none focus:border-violet-500 transition-colors"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleCreateBranch();
                  }}
                />
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setShowBranchModal(false)}
                  className="flex-1 py-2 bg-white/5 hover:bg-white/10 rounded-lg text-gray-400 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreateBranch}
                  disabled={!newBranchName.trim()}
                  className="flex-1 py-2 bg-violet-600 hover:bg-violet-500 rounded-lg text-white font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Create Branch
                </button>
              </div>

              <div className="mt-4 pt-4 border-t border-white/10 text-xs text-gray-500">
                <p>💡 Tip: Branches let you explore "what if" scenarios without losing your main story progress.</p>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
