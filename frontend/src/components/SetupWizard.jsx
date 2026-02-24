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
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-panel p-8 max-w-3xl mx-auto">
      <div className="mb-8">
        <h2 className="text-3xl font-bold text-white mb-2">Welcome to FableWeaver</h2>
        <p className="text-gray-300">Let's set up your story through a quick conversation.</p>
      </div>

      <form onSubmit={onSubmit} className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-400 mb-3">
            Describe your story idea (rough outline is fine!)
          </label>
          <textarea
            className="input-field min-h-[150px]"
            placeholder="E.g., 'Wormverse story with OC who has Gojo's Six Eyes and Infinity powers from Jujutsu Kaisen. Want strict canon adherence...'"
            value={value}
            onChange={e => onChange(e.target.value)}
            disabled={loading}
          />
        </div>

        <motion.button
          type="submit"
          disabled={loading || !value.trim()}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="btn-primary w-full"
        >
          {loading ? 'Analyzing...' : 'Next: Tell me about your story'}
        </motion.button>
      </form>

      <p className="text-xs text-gray-500 mt-6 text-center">
        I'll ask a few clarifying questions to make sure we're on the same page.
      </p>
    </motion.div>
  );
}

function ClarificationDialog({ conversation, currentQuestion, userAnswer, onAnswerChange, onSubmit, loading }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass-panel p-8 max-w-3xl mx-auto max-h-[80vh] flex flex-col">
      <h2 className="text-2xl font-bold text-white mb-6">Let's clarify a few things...</h2>

      {/* Conversation history */}
      <div className="flex-1 overflow-y-auto mb-6 space-y-4">
        <AnimatePresence>
          {conversation.map((msg, idx) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, x: msg.role === 'user' ? 20 : -20 }}
              animate={{ opacity: 1, x: 0 }}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div className={`max-w-[70%] p-4 rounded-lg ${msg.role === 'user' ? 'bg-blue-900/50 text-blue-100' : 'bg-gray-800/50 text-gray-100'}`}>
                {msg.content}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {currentQuestion && (
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex justify-start"
          >
            <div className="bg-gray-800/50 text-gray-100 p-4 rounded-lg max-w-[70%]">
              {currentQuestion}
            </div>
          </motion.div>
        )}
      </div>

      {/* Answer input */}
      <form onSubmit={onSubmit} className="space-y-4">
        <textarea
          className="input-field min-h-[80px]"
          placeholder="Your answer..."
          value={userAnswer}
          onChange={e => onAnswerChange(e.target.value)}
          disabled={loading}
        />

        <motion.button
          type="submit"
          disabled={loading || !userAnswer.trim()}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="btn-primary w-full"
        >
          {loading ? 'Processing...' : 'Continue'}
        </motion.button>
      </form>
    </motion.div>
  );
}

function ReviewStep({ config, summary, onConfirm, onRevise, loading }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass-panel p-8 max-w-3xl mx-auto">
      <h2 className="text-2xl font-bold text-white mb-6">Here's my understanding...</h2>

      {/* Summary from AI */}
      <div className="bg-gray-800/50 p-6 rounded-lg mb-8 text-gray-100 leading-relaxed">
        {summary}
      </div>

      {/* Config display */}
      <div className="grid grid-cols-2 gap-4 mb-8">
        <div className="bg-gray-900/50 p-4 rounded">
          <p className="text-sm text-gray-400">Story Universe</p>
          <p className="text-white font-semibold">{config.story_universe}</p>
        </div>
        <div className="bg-gray-900/50 p-4 rounded">
          <p className="text-sm text-gray-400">Power Level</p>
          <p className="text-white font-semibold capitalize">{config.power_level}</p>
        </div>
        <div className="bg-gray-900/50 p-4 rounded">
          <p className="text-sm text-gray-400">Powerset Isolation</p>
          <p className="text-white font-semibold">{config.isolate_powerset ? 'Yes (Pure mechanics)' : 'No (With context)'}</p>
        </div>
        <div className="bg-gray-900/50 p-4 rounded">
          <p className="text-sm text-gray-400">Story Tone</p>
          <p className="text-white font-semibold capitalize">{config.story_tone}</p>
        </div>
        <div className="bg-gray-900/50 p-4 rounded col-span-2">
          <p className="text-sm text-gray-400">Chapter Length</p>
          <p className="text-white font-semibold">{config.chapter_min_words}-{config.chapter_max_words} words</p>
        </div>
      </div>

      {/* Buttons */}
      <div className="flex gap-4">
        <motion.button
          onClick={onRevise}
          disabled={loading}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="btn-secondary flex-1"
        >
          Let me clarify something
        </motion.button>
        <motion.button
          onClick={onConfirm}
          disabled={loading}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="btn-primary flex-1"
        >
          {loading ? 'Creating...' : 'Perfect! Start my story'}
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
      className="glass-panel p-8 max-w-2xl mx-auto text-center"
    >
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
        className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-6"
      />
      <h2 className="text-2xl font-bold text-white mb-4">Creating your story...</h2>
      <p className="text-gray-400">Initializing World Bible and preparing narrative generation.</p>
    </motion.div>
  );
}
