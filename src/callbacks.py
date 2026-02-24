"""
ADK agent callbacks for validation, lifecycle logging, and error handling.

Provides:
- ``before_storyteller_callback``: Bible validation + timing start for Storyteller
- ``make_timing_callbacks``: Factory for before/after timing pairs on any agent
- ``tool_error_fallback``: Graceful tool-error handler (returns fallback string)
- ``before_storyteller_model_callback``: Injects dynamic chapter context into LLM request
"""
from __future__ import annotations

import time
from typing import Any, Optional

from google.genai import types
from sqlalchemy import select, func

from src.database import AsyncSessionLocal
from src.models import WorldBible, History, Story
from src.config import get_settings
from src.utils.logging_config import get_logger

logger = get_logger("fable.callbacks")


# ---------------------------------------------------------------------------
# 1. Storyteller before-agent callback (validation + timing)
# ---------------------------------------------------------------------------

async def before_storyteller_callback(callback_context) -> Optional[types.Content]:
    """Validate Bible state before Storyteller runs; also start timing.

    During ``init`` pipelines the Bible is intentionally empty (Lore Keeper
    hasn't populated it yet), so we skip validation.  For game-loop turns we
    ensure the essential sections exist so the Storyteller has data to work
    with.

    Returns ``None`` to proceed normally, or a ``types.Content`` error message
    that short-circuits the Storyteller (the message surfaces in the event
    loop).
    """
    state = callback_context.state

    # --- timing start (always) ---
    # Key must match the display_name used in make_timing_callbacks("Storyteller")
    # so the after_timing closure can find the start time.
    timings = state.get("_agent_timings", {})
    timings["Storyteller"] = time.monotonic()
    state["_agent_timings"] = timings
    logger.info("agent starting", extra={"agent": "Storyteller"})

    # --- skip validation on init (Bible is empty by design) ---
    pipeline_type = state.get("_pipeline_type", "game")
    if pipeline_type == "init":
        return None

    # --- validate Bible has required data ---
    story_id = state.get("story_id")
    if not story_id:
        # No story_id in state — can't validate, proceed and let agent cope
        logger.warning("No story_id in state; skipping Bible validation")
        return None

    try:
        async with AsyncSessionLocal() as session:
            stmt = select(WorldBible).where(WorldBible.story_id == story_id)
            result = await session.execute(stmt)
            bible = result.scalar_one_or_none()
    except Exception:
        logger.exception("Bible validation DB query failed")
        return None  # proceed despite error — don't block the pipeline

    if not bible or not bible.content:
        logger.warning(
            "Bible missing or empty for story_id=%s; skipping Storyteller",
            story_id,
        )
        return types.Content(
            parts=[types.Part(text=(
                "[System] World Bible is empty — cannot generate a chapter. "
                "Please run /research or re-initialise the story first."
            ))],
            role="model",
        )

    content = bible.content
    # Check minimal required structure
    character_sheet = content.get("character_sheet", {})
    character_name = character_sheet.get("name", "")
    world_state = content.get("world_state")

    if not character_name or not world_state:
        missing = []
        if not character_name:
            missing.append("character_sheet.name")
        if not world_state:
            missing.append("world_state")
        logger.warning(
            "Bible incomplete for story_id=%s; missing: %s",
            story_id,
            ", ".join(missing),
        )
        return types.Content(
            parts=[types.Part(text=(
                "[System] World Bible is incomplete (missing: "
                f"{', '.join(missing)}). Run the Lore Keeper first."
            ))],
            role="model",
        )

    return None  # all checks passed — proceed normally


# ---------------------------------------------------------------------------
# 2. Generic timing callback factory
# ---------------------------------------------------------------------------

def make_timing_callbacks(display_name: str):
    """Return a ``(before_cb, after_cb)`` pair that logs agent duration.

    Usage::

        before_timing, after_timing = make_timing_callbacks("Archivist")
        Agent(..., before_agent_callback=before_timing, after_agent_callback=after_timing)
    """

    async def _before(callback_context) -> Optional[types.Content]:
        timings = callback_context.state.get("_agent_timings", {})
        timings[display_name] = time.monotonic()
        callback_context.state["_agent_timings"] = timings
        logger.info("agent starting", extra={"agent": display_name})
        return None

    async def _after(callback_context) -> Optional[types.Content]:
        timings = callback_context.state.get("_agent_timings", {})
        start = timings.get(display_name)
        duration_ms = round((time.monotonic() - start) * 1000) if start else None
        logger.info(
            "agent complete",
            extra={"agent": display_name, "duration_ms": duration_ms},
        )
        return None

    return _before, _after


# ---------------------------------------------------------------------------
# 3. Tool error fallback
# ---------------------------------------------------------------------------

async def tool_error_fallback(
    tool,
    args: dict[str, Any],
    tool_context,
    error: Exception,
) -> Optional[dict]:
    """Catch tool exceptions and return a fallback string so the LLM adapts.

    Used as ``on_tool_error_callback`` on Storyteller and Lore Keeper.  The
    LLM receives a polite "tool unavailable" message and continues with the
    information it already has.
    """
    args_preview = str(args)[:200]
    logger.warning(
        "Tool %s failed: %s (args: %s)",
        getattr(tool, "name", str(tool)),
        error,
        args_preview,
    )
    return {
        "result": (
            f"Tool '{getattr(tool, 'name', str(tool))}' temporarily unavailable: "
            f"{error}. Continue with available information."
        )
    }


# ---------------------------------------------------------------------------
# 4. Storyteller before-model callback (dynamic context injection)
# ---------------------------------------------------------------------------

async def before_storyteller_model_callback(callback_context, llm_request):
    """Inject dynamic chapter context into the Storyteller's LLM request.

    Reads the current chapter count from the DB and appends instructions so
    the model knows which chapter number to write and the word-count target.
    """
    state = callback_context.state
    story_id = state.get("story_id")
    if not story_id:
        return None

    settings = get_settings()

    try:
        async with AsyncSessionLocal() as session:
            stmt = select(func.count()).select_from(History).where(
                History.story_id == story_id
            )
            result = await session.execute(stmt)
            chapter_count = result.scalar() or 0

            # Fetch story to check for per-story chapter length overrides
            story_stmt = select(Story).where(Story.id == story_id)
            story_result = await session.execute(story_stmt)
            story = story_result.scalar_one_or_none()

            # Use per-story overrides if set, else fall back to global config
            min_words = story.chapter_min_words_override if story and story.chapter_min_words_override else settings.chapter_min_words
            max_words = story.chapter_max_words_override if story and story.chapter_max_words_override else settings.chapter_max_words

    except Exception:
        logger.exception("Chapter count/story query failed in model callback")
        min_words = settings.chapter_min_words
        max_words = settings.chapter_max_words
        chapter_count = 0

    next_chapter = chapter_count + 1
    llm_request.append_instructions([
        f"Current chapter number: {next_chapter}",
        f"Word target: {min_words}-{max_words} words",
    ])
    return None  # never skip the model call
