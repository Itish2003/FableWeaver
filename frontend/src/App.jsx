import React, { useEffect, useState } from 'react';
import { useFableEngine } from './hooks/useFableEngine';
import ConfigForm from './components/ConfigForm';
import StoryView from './components/StoryView';
import { motion, AnimatePresence } from 'framer-motion';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    this.setState({ error, errorInfo });
    console.error("Uncaught error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-black text-red-500 p-10 font-mono text-sm whitespace-pre-wrap">
          <h1>Something went wrong.</h1>
          <br/>
          {this.state.error && this.state.error.toString()}
          <br/>
          {this.state.errorInfo && this.state.errorInfo.componentStack}
        </div>
      );
    }
    return this.props.children; 
  }
}

function App() {
  const engine = useFableEngine();
  const { status, connect, games, activeGameId, activeGame, history, currentText, deleteGame, resumeGame } = engine;
  const [isCreating, setIsCreating] = useState(false);



  const showDashboard = !activeGameId && !isCreating;

  return (
    <div className="min-h-screen flex flex-col items-center bg-[#050507] p-4 relative overflow-hidden text-slate-200">
      {/* Background Ambient Orbs */}
      <div className="absolute top-[-20%] left-[-20%] w-[50vw] h-[50vw] bg-purple-900/10 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute bottom-[-20%] right-[-20%] w-[50vw] h-[50vw] bg-cyan-900/10 rounded-full blur-[100px] pointer-events-none" />
      <ErrorBoundary>

      <header className="relative z-10 my-8 text-center w-full max-w-6xl flex justify-between items-center">
        <div className="text-left">
          <h1 className="text-4xl font-bold">
            <span className="text-gradient">FableWeaver</span>
          </h1>
          <p className="text-secondary opacity-60 text-sm">Architecture of Infinite Worlds</p>
        </div>
        
        <div className="flex items-center gap-6">
          {activeGameId && (
            <div className="flex items-center gap-2 text-xs text-secondary bg-white/5 px-3 py-1.5 rounded-full border border-white/10">
              <span className={`w-2 h-2 rounded-full ${status === 'connected' ? 'bg-green-500' : status === 'processing' ? 'bg-yellow-500 animate-pulse' : 'bg-red-500'}`} />
              <span>{status.toUpperCase()}</span>
            </div>
          )}
          {activeGameId && (
            <button 
              onClick={() => engine.setActiveGameId(null)}
              className="text-sm bg-white/5 hover:bg-white/10 px-4 py-1.5 rounded-lg transition-all border border-white/10"
            >
              Back to Library
            </button>
          )}
        </div>
      </header>
      
      <main className="relative z-10 w-full max-w-6xl">
        <AnimatePresence mode="wait">
          {showDashboard ? (
            <motion.div
              key="dashboard"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
            >
              <button
                onClick={() => setIsCreating(true)}
                className="h-64 flex flex-col items-center justify-center gap-4 bg-white/5 border-2 border-dashed border-white/10 rounded-2xl hover:bg-white/10 hover:border-purple-500/50 transition-all group"
              >
                <div className="w-12 h-12 rounded-full bg-purple-500/20 flex items-center justify-center text-purple-400 group-hover:scale-110 transition-transform">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" /></svg>
                </div>
                <span className="font-semibold text-lg">Weave New Fable</span>
              </button>

              {games.map(game => (
                <div 
                  key={game.id}
                  className="h-64 glass-panel p-6 flex flex-col justify-between group hover:border-purple-500/30 transition-all cursor-pointer relative overflow-hidden"
                  onClick={() => resumeGame(game.id)}
                >
                  <div className="absolute top-0 right-0 p-4 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button 
                      onClick={(e) => { e.stopPropagation(); deleteGame(game.id); }}
                      className="p-2 hover:bg-red-500/20 rounded-lg text-red-400 transition-all"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                    </button>
                  </div>
                  <div>
                    <h3 className="text-xl font-bold mb-2 text-purple-300 line-clamp-2">{game.title}</h3>
                    <p className="text-sm text-slate-400 line-clamp-3 italic">
                      {game.history?.[0]?.summary || "The first pages remain unwritten..."}
                    </p>
                  </div>
                  <div className="flex justify-between items-center mt-4">
                    <span className="text-[10px] uppercase tracking-widest text-slate-500">
                      {game.history?.length ? `${game.history.length} Chapters` : 'Not Started'}
                    </span>
                    <button className="text-xs text-purple-400 group-hover:text-purple-300 font-bold flex items-center gap-1">
                      CONTINUE <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" /></svg>
                    </button>
                  </div>
                </div>
              ))}
            </motion.div>
          ) : isCreating ? (
            <motion.div
              key="config"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
            >
              <div className="max-w-2xl mx-auto">
                <button 
                  onClick={() => setIsCreating(false)}
                  className="mb-6 text-sm flex items-center gap-2 text-slate-400 hover:text-white"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" /></svg>
                  Cancel
                </button>
                <ConfigForm onInit={(u, d, i) => { engine.createNewGame(u, d, i); setIsCreating(false); }} isConnecting={false} />
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="story"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="h-[80vh] w-full"
            >
              <StoryView engine={engine} />
            </motion.div>
          )}
        </AnimatePresence>
      </main>
      </ErrorBoundary>
    </div>
  );
}

export default App;
