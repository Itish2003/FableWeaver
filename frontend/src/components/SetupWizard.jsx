import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const Steps = {
  INITIAL: 'initial',
  CLARIFICATION: 'clarification',
  REVIEW: 'review',
  CONFIRMING: 'confirming',
};

export default function SetupWizard({ onInit, isConnecting }) {
  const [step, setStep] = useState(Steps.INITIAL);
  const [initialInput, setInitialInput] = useState('');
  const [config, setConfig] = useState({
    title: '',
    universes: [],
    story_universe: '',
    character_origin: '',
    powers: [],
    power_level: 'city',
    isolate_powerset: true,
    story_tone: 'balanced',
    themes: [],
    chapter_min_words: 6000,
    chapter_max_words: 8000,
    research_focus: [],
    power_limitations: '',
    user_context: '',
  });

  const [conversation, setConversation] = useState([]);
  const [currentQuestion, setCurrentQuestion] = useState('');
  const [questionIndex, setQuestionIndex] = useState(0);
  const [userAnswer, setUserAnswer] = useState('');
  const [reviewSummary, setReviewSummary] = useState('');
  const [loading, setLoading] = useState(false);

  // Step 1: Initial Input
  const handleInitialSubmit = async (e) => {
    e.preventDefault();
    if (!initialInput.trim()) return;

    setLoading(true);
    setConversation([{ role: 'user', content: initialInput }]);

    try {
      const response = await fetch('/api/setup/clarify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_input: initialInput }),
      });

      const data = await response.json();
      setConfig(data.current_understanding);
      setStep(Steps.CLARIFICATION);
      setCurrentQuestion(data.questions[0] || '');
      setQuestionIndex(0);

      setConversation(prev => [
        ...prev,
        { role: 'ai', content: data.questions[0] },
      ]);
    } catch (error) {
      console.error('Error in initial clarification:', error);
      setConversation(prev => [
        ...prev,
        { role: 'ai', content: 'Error: Could not generate clarifying questions. Please try again.' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Clarification Turns
  const handleClarificationAnswer = async (e) => {
    e.preventDefault();
    if (!userAnswer.trim()) return;

    setLoading(true);
    const newConversation = [
      ...conversation,
      { role: 'user', content: userAnswer },
    ];
    setConversation(newConversation);
    setUserAnswer('');

    try {
      const response = await fetch('/api/setup/refine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_config: config,
          user_answer: userAnswer,
          question_index: questionIndex,
        }),
      });

      const data = await response.json();
      setConfig(data.updated_config);

      if (data.is_review_ready) {
        // Move to review
        setStep(Steps.REVIEW);
        const reviewResponse = await fetch('/api/setup/review', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            final_config: data.updated_config,
            confirmed: false,
          }),
        });
        const reviewData = await reviewResponse.json();
        setReviewSummary(reviewData.summary);
      } else {
        // Continue with next question
        setConversation(prev => [
          ...prev,
          { role: 'ai', content: data.next_question },
        ]);
        setCurrentQuestion(data.next_question);
        setQuestionIndex(questionIndex + 1);
      }
    } catch (error) {
      console.error('Error in refinement:', error);
      setConversation(prev => [
        ...prev,
        { role: 'ai', content: 'Error: Could not process your answer. Please try again.' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  // Step 3: Confirm and Create
  const handleConfirm = async () => {
    setLoading(true);
    setStep(Steps.CONFIRMING);

    try {
      const response = await fetch('/api/setup/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });

      const data = await response.json();
      onInit(data.story_id);
    } catch (error) {
      console.error('Error confirming setup:', error);
      setConversation(prev => [
        ...prev,
        { role: 'ai', content: 'Error: Could not create story. Please try again.' },
      ]);
      setStep(Steps.REVIEW);
    } finally {
      setLoading(false);
    }
  };

  // Render based on step
  if (step === Steps.INITIAL) {
    return <InitialInputForm onSubmit={handleInitialSubmit} value={initialInput} onChange={setInitialInput} loading={loading} />;
  }

  if (step === Steps.CLARIFICATION) {
    return (
      <ClarificationDialog
        conversation={conversation}
        currentQuestion={currentQuestion}
        userAnswer={userAnswer}
        onAnswerChange={setUserAnswer}
        onSubmit={handleClarificationAnswer}
        loading={loading}
      />
    );
  }

  if (step === Steps.REVIEW) {
    return (
      <ReviewStep
        config={config}
        summary={reviewSummary}
        onConfirm={handleConfirm}
        onRevise={() => {
          setStep(Steps.CLARIFICATION);
          setQuestionIndex(questionIndex - 1);
        }}
        loading={loading}
      />
    );
  }

  if (step === Steps.CONFIRMING) {
    return <ConfirmingStep />;
  }
}

// ============================================================================
//                       STEP COMPONENTS
// ============================================================================

function InitialInputForm({ onSubmit, value, onChange, loading }) {
  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-panel p-8 max-w-2xl mx-auto">
      <div className="mb-8">
        <h2 className="text-4xl font-bold text-white mb-3">Create Your Story</h2>
        <p className="text-gray-400">Tell me about your fanfiction idea. I'll ask clarifying questions to get it just right.</p>
      </div>

      <form onSubmit={onSubmit} className="space-y-6">
        <div>
          <label className="block text-sm font-semibold text-gray-300 mb-3">
            Your Story Idea
          </label>
          <textarea
            className="input-field min-h-[140px] resize-none"
            placeholder="E.g., 'Crossover story where Kudou gets powers from another universe. I want strict canon accuracy...'"
            value={value}
            onChange={e => onChange(e.target.value)}
            disabled={loading}
          />
        </div>

        <motion.button
          type="submit"
          disabled={loading || !value.trim()}
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}
          className="btn-primary w-full"
        >
          {loading ? 'Analyzing...' : 'Start Setup Conversation'}
        </motion.button>
      </form>

      <p className="text-xs text-gray-500 mt-6 text-center">
        I'll ask 5 clarifying questions to understand your story better
      </p>
    </motion.div>
  );
}

function ClarificationDialog({ conversation, currentQuestion, userAnswer, onAnswerChange, onSubmit, loading }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass-panel p-8 max-w-2xl mx-auto max-h-[85vh] flex flex-col">
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-white mb-2">Let's set this up</h2>
        <p className="text-gray-400 text-sm">Answer a few questions about your story</p>
      </div>

      {/* Conversation history */}
      <div className="flex-1 overflow-y-auto mb-8 space-y-6">
        <AnimatePresence mode="popLayout">
          {conversation.map((msg, idx) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`max-w-[85%] ${msg.role === 'user'
                ? 'bg-gradient-to-br from-blue-600 to-blue-700 text-white rounded-2xl rounded-tr-lg'
                : 'bg-gray-700/60 text-gray-50 rounded-2xl rounded-tl-lg'} p-4 shadow-lg`}>
                <p className="text-sm leading-relaxed">{msg.content}</p>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {currentQuestion && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex justify-start"
          >
            <div className="bg-gray-700/60 text-gray-50 rounded-2xl rounded-tl-lg p-4 max-w-[85%] shadow-lg">
              <p className="text-sm leading-relaxed font-medium">{currentQuestion}</p>
            </div>
          </motion.div>
        )}
      </div>

      {/* Answer input */}
      <form onSubmit={onSubmit} className="space-y-4 border-t border-gray-600/30 pt-6">
        <div>
          <label className="block text-xs font-medium text-gray-400 mb-2">Your response:</label>
          <textarea
            className="input-field min-h-[80px] resize-none"
            placeholder="Type your answer here..."
            value={userAnswer}
            onChange={e => onAnswerChange(e.target.value)}
            disabled={loading}
          />
        </div>

        <motion.button
          type="submit"
          disabled={loading || !userAnswer.trim()}
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}
          className="btn-primary w-full"
        >
          {loading ? 'Analyzing...' : 'Send'}
        </motion.button>
      </form>
    </motion.div>
  );
}

function ReviewStep({ config, summary, onConfirm, onRevise, loading }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass-panel p-8 max-w-2xl mx-auto">
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-white mb-2">Ready to create?</h2>
        <p className="text-gray-400 text-sm">Here's what I understand about your story</p>
      </div>

      {/* Summary from AI */}
      <div className="bg-gray-700/60 p-6 rounded-xl mb-8 text-gray-50 leading-relaxed border border-gray-600/30">
        <p className="text-sm">{summary}</p>
      </div>

      {/* Config display */}
      <div className="space-y-4 mb-8">
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-gray-800/40 p-4 rounded-lg border border-gray-700/50">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Universe</p>
            <p className="text-white font-medium">{config.story_universe || '—'}</p>
          </div>
          <div className="bg-gray-800/40 p-4 rounded-lg border border-gray-700/50">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Power Level</p>
            <p className="text-white font-medium capitalize">{config.power_level}</p>
          </div>
          <div className="bg-gray-800/40 p-4 rounded-lg border border-gray-700/50">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Isolation</p>
            <p className="text-white font-medium text-sm">{config.isolate_powerset ? 'Pure mechanics' : 'With context'}</p>
          </div>
          <div className="bg-gray-800/40 p-4 rounded-lg border border-gray-700/50">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Tone</p>
            <p className="text-white font-medium capitalize">{config.story_tone}</p>
          </div>
        </div>
        <div className="bg-gray-800/40 p-4 rounded-lg border border-gray-700/50">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">Chapter Length</p>
          <p className="text-white font-medium">{config.chapter_min_words.toLocaleString()}–{config.chapter_max_words.toLocaleString()} words</p>
        </div>
      </div>

      {/* Buttons */}
      <div className="flex gap-3">
        <motion.button
          onClick={onRevise}
          disabled={loading}
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}
          className="btn-secondary flex-1"
        >
          Go back & revise
        </motion.button>
        <motion.button
          onClick={onConfirm}
          disabled={loading}
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}
          className="btn-primary flex-1"
        >
          {loading ? 'Creating...' : 'Let's go!'}
        </motion.button>
      </div>
    </motion.div>
  );
}

function ConfirmingStep() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="glass-panel p-12 max-w-xl mx-auto text-center"
    >
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 2.5, repeat: Infinity, ease: 'linear' }}
        className="w-14 h-14 border-4 border-blue-500 border-t-blue-200 rounded-full mx-auto mb-8"
      />
      <h2 className="text-3xl font-bold text-white mb-3">Creating your story</h2>
      <p className="text-gray-400 text-sm">Setting up the World Bible and preparing narrative generation...</p>
    </motion.div>
  );
}
