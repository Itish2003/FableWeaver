"""Tests for _trim_to_current_turn and _strip_orphaned_fc_pairs.

Validates that session history trimming correctly handles:
- Real user messages vs function_response-only messages
- Orphaned function_call/response pairs after trimming
- Init pipeline history (research swarm → lore keeper → storyteller)
- Game loop history (archivist → storyteller, multi-turn)
"""

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers: build fake Content/Part objects matching Gemini's wire format
# ---------------------------------------------------------------------------

def _part(text=None, function_call=None, function_response=None):
    """Create a mock Part with optional text/function_call/function_response."""
    p = MagicMock()
    p.text = text
    p.function_call = function_call
    p.function_response = function_response
    return p


def _msg(role, parts):
    """Create a mock Content message."""
    m = MagicMock()
    m.role = role
    m.parts = parts
    return m


def user_text(text="hello"):
    """User message with real text."""
    return _msg("user", [_part(text=text)])


def model_text(text="response"):
    """Model message with text."""
    return _msg("model", [_part(text=text)])


def model_fc(name="google_search"):
    """Model message with a function_call."""
    return _msg("model", [_part(function_call={"name": name})])


def user_fr(name="google_search"):
    """User message with a function_response (no text)."""
    return _msg("user", [_part(function_response={"name": name, "response": "ok"})])


# ---------------------------------------------------------------------------
# Import the functions under test
# ---------------------------------------------------------------------------

from src.callbacks import _trim_to_current_turn, _strip_orphaned_fc_pairs


# ---------------------------------------------------------------------------
# Tests: _trim_to_current_turn
# ---------------------------------------------------------------------------

class TestTrimToCurrentTurn:
    """Tests for the main trim function."""

    def test_empty_contents(self):
        assert _trim_to_current_turn([], "test") == []

    def test_single_message(self):
        msgs = [user_text("init")]
        assert _trim_to_current_turn(msgs, "test") == msgs

    def test_two_messages(self):
        msgs = [user_text("init"), model_text("chapter")]
        assert _trim_to_current_turn(msgs, "test") == msgs

    def test_simple_multi_turn(self):
        """Two user turns — trim to the second."""
        msgs = [
            user_text("turn 1"),
            model_text("chapter 1"),
            user_text("turn 2"),       # <- last real user msg
            model_text("chapter 2"),
        ]
        result = _trim_to_current_turn(msgs, "test")
        assert len(result) == 2
        assert result[0].parts[0].text == "turn 2"
        assert result[1].parts[0].text == "chapter 2"

    def test_function_response_not_treated_as_real_user(self):
        """function_response messages (role=user) must not be mistaken for real input.

        This is THE critical bug: after lore keeper tool calls, the last
        role='user' message is a function_response.  Trimming from there
        produces a list starting with model → Gemini 400 error.
        """
        msgs = [
            user_text("init input"),           # 0: real user message
            model_fc("google_search"),         # 1: researcher tool call
            user_fr("google_search"),          # 2: tool response (role=user!)
            model_text("research findings"),   # 3: researcher output
            model_fc("update_bible"),          # 4: lore keeper tool call
            user_fr("update_bible"),           # 5: tool response (role=user!)
            model_text("bible updated"),       # 6: lore keeper output
        ]
        result = _trim_to_current_turn(msgs, "Storyteller")
        # Should return all contents since the only real user msg is at idx 0
        assert len(result) == len(msgs)
        assert result[0].parts[0].text == "init input"

    def test_game_loop_trims_to_current_turn(self):
        """Game loop: archivist tool calls followed by storyteller turn.

        Turn 1 history + Turn 2 user message → trim to Turn 2.
        """
        msgs = [
            # Turn 1
            user_text("player chose A"),
            model_fc("update_bible"),
            user_fr("update_bible"),
            model_text("archivist delta"),
            model_text("Chapter 2 narrative..."),
            # Turn 2
            user_text("player chose B"),        # <- last real user msg
            model_fc("update_bible"),
            user_fr("update_bible"),
            model_text("archivist delta 2"),
        ]
        result = _trim_to_current_turn(msgs, "Storyteller")
        assert len(result) == 4
        assert result[0].parts[0].text == "player chose B"

    def test_preserves_tool_pairs_in_current_turn(self):
        """Tool call/response pairs within the current turn are preserved."""
        msgs = [
            user_text("old turn"),
            model_text("old response"),
            user_text("current turn"),          # <- last real user msg
            model_fc("search_lore"),            # current turn's tool call
            user_fr("search_lore"),             # current turn's tool response
            model_text("lore result applied"),
        ]
        result = _trim_to_current_turn(msgs, "Storyteller")
        assert len(result) == 4  # user + fc + fr + model
        assert result[0].parts[0].text == "current turn"

    def test_strips_orphaned_fc_after_trim(self):
        """If trimming leaves an orphaned function_call, it gets stripped."""
        msgs = [
            user_text("old turn"),
            model_text("old response"),
            user_text("current turn"),
            model_fc("broken_tool"),            # orphaned: no function_response after
            model_text("continued anyway"),
        ]
        result = _trim_to_current_turn(msgs, "Storyteller")
        # Should have: user("current turn"), model("continued anyway")
        # The orphaned fc should be stripped
        assert len(result) == 2
        assert result[0].parts[0].text == "current turn"
        assert result[1].parts[0].text == "continued anyway"

    def test_init_pipeline_full_history(self):
        """Simulates a full init pipeline: 3 researchers + lore keeper + storyteller.

        All tool call/response pairs from research phase should be preserved
        since the only real user message is at index 0.
        """
        msgs = [
            user_text("Create a story about..."),
            # Researcher 1
            model_fc("google_search"),
            user_fr("google_search"),
            model_text("Research 1 findings"),
            # Researcher 2
            model_fc("google_search"),
            user_fr("google_search"),
            model_text("Research 2 findings"),
            # Researcher 3
            model_fc("scrape_url"),
            user_fr("scrape_url"),
            model_text("Research 3 findings"),
            # Lore Keeper
            model_fc("update_bible"),
            user_fr("update_bible"),
            model_fc("update_bible"),
            user_fr("update_bible"),
            model_text("Bible populated"),
        ]
        result = _trim_to_current_turn(msgs, "Storyteller")
        # Only real user msg is at idx 0 → return everything
        assert len(result) == len(msgs)
        assert result[0].parts[0].text == "Create a story about..."

    def test_no_user_message_returns_as_is(self):
        """If no user message exists at all, return contents unchanged."""
        msgs = [model_text("orphan")]
        result = _trim_to_current_turn(msgs, "test")
        assert result == msgs

    def test_mixed_user_message_with_text_and_fr(self):
        """A user message that has BOTH text and function_response counts as real."""
        mixed = _msg("user", [
            _part(text="here's context"),
            _part(function_response={"name": "tool", "response": "ok"}),
        ])
        msgs = [
            user_text("old"),
            model_text("old response"),
            mixed,                              # <- has text, so it's "real"
            model_text("new response"),
        ]
        result = _trim_to_current_turn(msgs, "test")
        assert len(result) == 2
        assert result[0] is mixed


# ---------------------------------------------------------------------------
# Tests: _strip_orphaned_fc_pairs
# ---------------------------------------------------------------------------

class TestStripOrphanedFcPairs:
    """Tests for the orphaned function_call/response stripping."""

    def test_empty(self):
        assert _strip_orphaned_fc_pairs([]) == []

    def test_no_function_calls(self):
        msgs = [user_text(), model_text()]
        result = _strip_orphaned_fc_pairs(msgs)
        assert len(result) == 2

    def test_proper_pair_preserved(self):
        msgs = [
            user_text(),
            model_fc("tool"),
            user_fr("tool"),
            model_text("result"),
        ]
        result = _strip_orphaned_fc_pairs(msgs)
        assert len(result) == 4

    def test_orphaned_fc_at_end(self):
        """function_call at the end with no response → stripped."""
        msgs = [
            user_text(),
            model_text("some text"),
            model_fc("broken"),                 # orphaned: at end of list
        ]
        result = _strip_orphaned_fc_pairs(msgs)
        assert len(result) == 2

    def test_orphaned_fc_followed_by_model(self):
        """function_call followed by model (not function_response) → stripped."""
        msgs = [
            user_text(),
            model_fc("broken"),                 # orphaned: next is model, not fr
            model_text("continued"),
        ]
        result = _strip_orphaned_fc_pairs(msgs)
        assert len(result) == 2
        assert result[1].parts[0].text == "continued"

    def test_multiple_proper_pairs(self):
        """Multiple consecutive tool call/response pairs all preserved."""
        msgs = [
            user_text(),
            model_fc("tool1"),
            user_fr("tool1"),
            model_fc("tool2"),
            user_fr("tool2"),
            model_text("all done"),
        ]
        result = _strip_orphaned_fc_pairs(msgs)
        assert len(result) == 6

    def test_mixed_orphaned_and_proper(self):
        """Mix of proper pairs and orphaned calls → only orphans stripped."""
        msgs = [
            user_text(),
            model_fc("good_tool"),
            user_fr("good_tool"),
            model_fc("bad_tool"),               # orphaned
            model_text("recovery"),
            model_fc("good_tool2"),
            user_fr("good_tool2"),
        ]
        result = _strip_orphaned_fc_pairs(msgs)
        # user, fc(good), fr(good), model(recovery), fc(good2), fr(good2)
        assert len(result) == 6
