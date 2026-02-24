import { useState, useEffect, useRef, useCallback } from 'react';

const API_BASE = 'http://localhost:8000';
const WS_BASE = 'ws://localhost:8000/ws';

export function useFableEngine() {
  const [status, setStatus] = useState('disconnected');
  const [error, setError] = useState(null);
  
  // Games list now fetched from DB
  const [games, setGames] = useState([]);
  
  // Active Game ID
  const [activeGameId, setActiveGameId] = useState(null);

  // World Bible data for active game
  const [worldBible, setWorldBible] = useState(null);
  const [bibleLoading, setBibleLoading] = useState(false);

  useEffect(() => {
    console.log("useFableEngine initialized. Games:", games.length, "Active:", activeGameId);
  }, [games.length, activeGameId]);

  // Derived Active Game State
  const activeGame = games.find(g => g.id === activeGameId);
  const history = activeGame?.history || [];
  const choices = activeGame?.choices || null;
  
  const [currentText, setCurrentText] = useState('');
  const [questions, setQuestions] = useState(null);  // Optional clarifying questions from AI
  const [systemMessages, setSystemMessages] = useState([]);  // System log (research, enrich, etc.)

  const ws = useRef(null);
  const bufferRef = useRef('');
  
  // Payload to send upon connection (for new games)
  const initPayloadRef = useRef(null);

  // User's answers to clarifying questions
  const questionAnswersRef = useRef({});

  // Ref to track active ID for WS callbacks
  const activeGameIdRef = useRef(activeGameId);
  useEffect(() => {
    activeGameIdRef.current = activeGameId;
  }, [activeGameId]);

  // 1. Fetch Stories on Mount
  useEffect(() => {
    fetch(`${API_BASE}/stories`)
      .then(res => res.json())
      .then(data => setGames(data))
      .catch(err => console.error("Failed to fetch stories:", err));
  }, []);

  // Fetch World Bible for active game
  const fetchWorldBible = async (gameId) => {
    if (!gameId) {
      setWorldBible(null);
      return;
    }
    setBibleLoading(true);
    try {
      const res = await fetch(`${API_BASE}/stories/${gameId}/bible`);
      if (res.ok) {
        const data = await res.json();
        setWorldBible(data.bible);
      } else {
        setWorldBible(null);
      }
    } catch (err) {
      console.error("Failed to fetch World Bible:", err);
      setWorldBible(null);
    } finally {
      setBibleLoading(false);
    }
  };

  // 2. Connect & Load Details when Active Game Changes
  useEffect(() => {
    if (!activeGameId) {
        if (ws.current) {
            ws.current.close();
            ws.current = null;
        }
        setWorldBible(null);
        return;
    }

    // Fetch full details (history) and World Bible
    fetch(`${API_BASE}/stories/${activeGameId}`)
      .then(res => res.json())
      .then(details => {
        // Extract choices from last chapter in history (for display when loading existing story)
        const lastChapter = details.history?.[details.history.length - 1];
        // Handle both {choices: [...]} object format and direct array format
        const lastChoices = lastChapter?.choices?.choices || lastChapter?.choices || null;

        // Update local state with fetched history AND last chapter's choices
        setGames(prev => prev.map(g => g.id === activeGameId ? { ...g, ...details, choices: lastChoices } : g));

        // Connect WS
        connect(activeGameId);

        // Fetch World Bible
        fetchWorldBible(activeGameId);
      })
      .catch(err => console.error("Failed to load story details:", err));

    return () => {
      if (ws.current) {
        ws.current.close();
        ws.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeGameId]);

  const connect = useCallback((gameId) => {
    if (ws.current) {
        ws.current.close();
    }
    
    setStatus('connecting');
    const socket = new WebSocket(`${WS_BASE}/${gameId}`);
    ws.current = socket;
    
    socket.onopen = () => {
        setStatus('connected');
        // If we have a pending init payload (new game), send it now
        if (initPayloadRef.current) {
            socket.send(JSON.stringify({
                action: 'init',
                payload: { ...initPayloadRef.current, session_id: gameId }
            }));
            initPayloadRef.current = null;
        }
    };
    
    socket.onmessage = (event) => handleMessage(JSON.parse(event.data));
    socket.onclose = () => { 
        setStatus('disconnected'); 
        ws.current = null; 
    };
    socket.onerror = () => setStatus('error');
  }, []);

  const handleMessage = (data) => {
    switch (data.type) {
      case 'status':
        if (data.status === 'processing') {
          setStatus('processing');
          setCurrentText('');
          bufferRef.current = '';
          setQuestions(null);
          setSystemMessages([]);  // Clear system log on new turn
        }
        break;
      case 'content_delta':
        // Route system messages to separate log, narrative to buffer
        if (data.sender === 'system') {
          const text = (data.text || '').replace(/\n+$/, '');
          if (text.trim()) {
            setSystemMessages(prev => [...prev, text]);
          }
        } else {
          bufferRef.current += data.text;
          const jsonStart = bufferRef.current.search(/\{(?:[\s\n]*"summary"|[\s\n]*"choices")/);
          if (jsonStart !== -1) {
              setCurrentText(bufferRef.current.substring(0, jsonStart).trim());
          } else {
              setCurrentText(bufferRef.current);
          }
        }
        break;
      case 'turn_complete':
        setStatus('connected');
        processTurnComplete();
        if (data.questions && Array.isArray(data.questions) && data.questions.length > 0) {
          setQuestions(data.questions);
        } else {
          setQuestions(null);
        }
        if (activeGameIdRef.current) {
          fetchWorldBible(activeGameIdRef.current);
        }
        break;
      case 'error':
        setError(data.message);
        setStatus('error');
        break;
    }
  };

  const processTurnComplete = () => {
    const fullText = bufferRef.current;
    
    // Improved JSON splitter
    const jsonMatch = fullText.match(/\{[\s\S]*"choices"[\s\S]*\}/);
    
    let turnChoices = null;
    let turnSummary = "New Chapter Added";
    let cleanText = fullText;

    if (jsonMatch) {
      try {
        let jsonStr = jsonMatch[0];
        jsonStr = jsonStr.replace(/```json|```/g, '').trim();
        
        const gameData = JSON.parse(jsonStr);
        turnChoices = gameData.choices;
        turnSummary = gameData.summary;
        
        // Robust split
        cleanText = fullText.substring(0, jsonMatch.index).trim();
      } catch (e) { 
        console.error("JSON Parse Error:", e);
      }
    }

    const currentId = activeGameIdRef.current;

    setGames(prev => prev.map(g => {
      if (g.id === currentId) {
        // We append locally for immediate feedback. 
        // Backend DB update is independent.
        // We generate a temp ID for the key, or use Date.now()
        return {
          ...g,
          history: [...(g.history || []), { id: `temp_${Date.now()}`, text: cleanText, summary: turnSummary }],
          choices: turnChoices,
          lastUpdated: new Date().toISOString()
        };
      }
      return g;
    }));
    setCurrentText('');
  };

  const createNewGame = async (universes, deviation, userInput) => {
    // 1. Create on Backend
    try {
        const res = await fetch(`${API_BASE}/stories`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: universes.join(', ') || "New Story" })
        });
        if (!res.ok) throw new Error("Failed to create story");
        
        const newStory = await res.json();
        
        // 2. Update List
        setGames(prev => [newStory, ...prev]);
        
        // 3. Set Init Payload for WS
        initPayloadRef.current = { universes, timeline_deviation: deviation, user_input: userInput };
        
        // 4. Set Active (triggers useEffect -> connect -> onopen -> send init)
        setActiveGameId(newStory.id);
        
    } catch (e) {
        console.error(e);
        setError("Failed to create new story");
    }
  };

  const resumeGame = (gameId) => {
    setActiveGameId(gameId);
  };

  const sendInit = (initPayload) => {
    // Set the payload to be sent when WebSocket connects
    initPayloadRef.current = initPayload;
    // If already connected, send immediately
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({
        action: 'init',
        payload: { ...initPayload, session_id: activeGameIdRef.current }
      }));
      initPayloadRef.current = null;
    }
  };

  const sendChoice = (choiceText) => {
    if (!ws.current || !activeGameId) return;
    const payload = { choice: choiceText, session_id: activeGameId };

    // Include any question answers
    if (Object.keys(questionAnswersRef.current).length > 0) {
      payload.question_answers = questionAnswersRef.current;
      questionAnswersRef.current = {};  // Clear after sending
    }

    ws.current.send(JSON.stringify({
      action: 'choice',
      payload
    }));
    setQuestions(null);  // Clear questions after choice is made
  };

  // Set answer to a specific question
  const setQuestionAnswer = (questionIndex, answer) => {
    questionAnswersRef.current[questionIndex] = answer;
  };

  // Clear all question answers
  const clearQuestionAnswers = () => {
    questionAnswersRef.current = {};
  };

  const sendResearch = (query) => {
    if (!ws.current) return;

    // Parse depth modifier from query: "deep <query>" or "quick <query>"
    let depth = 'quick';
    let cleanQuery = query;

    if (query.toLowerCase().startsWith('deep ')) {
      depth = 'deep';
      cleanQuery = query.slice(5).trim();
    } else if (query.toLowerCase().startsWith('quick ')) {
      depth = 'quick';
      cleanQuery = query.slice(6).trim();
    }

    ws.current.send(JSON.stringify({
      action: 'research',
      payload: { query: cleanQuery, depth, session_id: activeGameId }
    }));
  };

  // Send generic command (undo, etc.)
  const sendCommand = (command, args = {}) => {
    if (!ws.current || !activeGameId) return;
    ws.current.send(JSON.stringify({
      action: command,
      payload: { session_id: activeGameId, ...args }
    }));
  };

  // Delete a specific chapter
  const deleteChapter = async (chapterId) => {
    if (!activeGameId) return;
    try {
      const res = await fetch(`${API_BASE}/stories/${activeGameId}/chapters/${chapterId}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        // Update local state
        setGames(prev => prev.map(g => {
          if (g.id === activeGameId) {
            return {
              ...g,
              history: (g.history || []).filter(h => h.id !== chapterId)
            };
          }
          return g;
        }));
      }
    } catch (e) {
      console.error("Failed to delete chapter:", e);
    }
  };

  const deleteGame = async (id) => {
    try {
      await fetch(`${API_BASE}/stories/${id}`, { method: 'DELETE' });
      setGames(prev => prev.filter(g => g.id !== id));
      if (activeGameId === id) setActiveGameId(null);
    } catch (e) {
      console.error("Failed to delete story:", e);
    }
  };

  // Wrap refreshBible to use current activeGameId
  const refreshBible = useCallback(() => {
    if (activeGameId) {
      fetchWorldBible(activeGameId);
    }
  }, [activeGameId]);

  // === BRANCHING SUPPORT ===

  // State for branches
  const [branches, setBranches] = useState([]);
  const [branchInfo, setBranchInfo] = useState(null);

  // Fetch branches for active game
  const fetchBranches = async (gameId) => {
    if (!gameId) {
      setBranches([]);
      setBranchInfo(null);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/stories/${gameId}/branches`);
      if (res.ok) {
        const data = await res.json();
        setBranches(data.branches || []);
        setBranchInfo({
          isBranch: data.is_branch,
          parentStoryId: data.parent_story_id,
          branchName: data.branch_name,
          chapterCount: data.chapter_count
        });
      }
    } catch (err) {
      console.error("Failed to fetch branches:", err);
    }
  };

  // Fetch branches when active game changes
  useEffect(() => {
    if (activeGameId) {
      fetchBranches(activeGameId);
    }
  }, [activeGameId]);

  // Create a new branch from current story state
  const createBranch = async (branchName = "New Branch") => {
    if (!activeGameId) return null;
    try {
      const res = await fetch(`${API_BASE}/stories/${activeGameId}/branch?branch_name=${encodeURIComponent(branchName)}`, {
        method: 'POST'
      });
      if (res.ok) {
        const data = await res.json();
        // Refresh games list to include new branch
        const storiesRes = await fetch(`${API_BASE}/stories`);
        if (storiesRes.ok) {
          const storiesData = await storiesRes.json();
          setGames(storiesData);
        }
        // Refresh branches for current story
        await fetchBranches(activeGameId);
        return data;
      }
    } catch (err) {
      console.error("Failed to create branch:", err);
    }
    return null;
  };

  // Switch to a different branch/story
  const switchToBranch = (branchId) => {
    setActiveGameId(branchId);
  };

  // Go to parent story
  const goToParent = () => {
    if (branchInfo?.parentStoryId) {
      setActiveGameId(branchInfo.parentStoryId);
    }
  };

  return {
    status,
    games,
    activeGameId,
    activeGame,
    history,
    currentText,
    choices,
    questions,
    systemMessages,  // System log (research progress, enrich results, etc.)
    worldBible,
    bibleLoading,
    createNewGame,
    resumeGame,
    sendInit,
    sendChoice,
    sendResearch,
    sendCommand,
    deleteChapter,
    deleteGame,
    setActiveGameId,
    refreshBible,
    setQuestionAnswer,  // Set answer to a specific question
    clearQuestionAnswers,  // Clear all answers
    // Branching
    branches,
    branchInfo,
    createBranch,
    switchToBranch,
    goToParent,
    fetchBranches
  };
}
