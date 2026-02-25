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
    """Inject dynamic chapter context and hard enforcement data into the Storyteller's LLM request.

    Performs a single consolidated DB read to fetch chapter count, story config,
    and the World Bible. From the Bible it extracts:
    - Knowledge base index (for search_lore)
    - Forbidden knowledge prohibitions
    - Character secrets
    - Upcoming canon events / timeline context
    - Power combat reference (techniques, styles, weaknesses)

    Each enforcement block is capped to limit token overhead and only injected
    when non-empty.
    """
    state = callback_context.state
    story_id = state.get("story_id")
    if not story_id:
        return None

    settings = get_settings()
    bible_content: dict | None = None

    # --- Single consolidated DB read ---
    try:
        async with AsyncSessionLocal() as session:
            # Chapter count
            count_stmt = select(func.count()).select_from(History).where(
                History.story_id == story_id
            )
            count_result = await session.execute(count_stmt)
            chapter_count = count_result.scalar() or 0

            # Story config (per-story word-count overrides)
            story_stmt = select(Story).where(Story.id == story_id)
            story_result = await session.execute(story_stmt)
            story = story_result.scalar_one_or_none()

            min_words = story.chapter_min_words_override if story and story.chapter_min_words_override else settings.chapter_min_words
            max_words = story.chapter_max_words_override if story and story.chapter_max_words_override else settings.chapter_max_words

            # World Bible
            bible_stmt = select(WorldBible).where(WorldBible.story_id == story_id)
            bible_result = await session.execute(bible_stmt)
            bible = bible_result.scalar_one_or_none()
            if bible and bible.content:
                bible_content = bible.content

    except Exception:
        logger.exception("Consolidated DB query failed in model callback")
        min_words = settings.chapter_min_words
        max_words = settings.chapter_max_words
        chapter_count = 0

    next_chapter = chapter_count + 1

    # --- Build instruction blocks from Bible ---
    instructions: list[str] = [
        f"Current chapter number: {next_chapter}",
        f"Word target: {min_words}-{max_words} words",
    ]

    if bible_content:
        # 1. Knowledge base index
        kb = bible_content.get("world_state", {}).get("knowledge_base", {})
        if kb:
            keys = sorted(kb.keys())
            instructions.append(
                f"\n\nAVAILABLE LORE ({len(keys)} entries in knowledge_base) — "
                f"use search_lore(topic) to retrieve details:\n"
                + ", ".join(keys)
            )

        # 2. FORBIDDEN KNOWLEDGE
        instructions.append(
            _build_forbidden_knowledge_block(bible_content)
        )

        # 3. CHARACTER SECRETS
        instructions.append(
            _build_character_secrets_block(bible_content)
        )

        # 4. UPCOMING CANON EVENTS / TIMELINE CONTEXT
        instructions.append(
            _build_timeline_block(bible_content)
        )

        # 5. POWER COMBAT REFERENCE
        instructions.append(
            _build_power_reference_block(bible_content)
        )

        # 6. PROTECTED CHARACTERS / ANTI-WORFING
        instructions.append(
            _build_protected_characters_block(bible_content)
        )

    # Filter out empty strings (blocks that had no data)
    instructions = [blk for blk in instructions if blk]

    llm_request.append_instructions(instructions)
    return None  # never skip the model call


# ---------------------------------------------------------------------------
# 4a. Enforcement block builders (pure functions, no I/O)
# ---------------------------------------------------------------------------

_MAX_FORBIDDEN = 30
_MAX_SECRETS_CHARACTERS = 15
_MAX_TIMELINE_EVENTS = 10
_MAX_POWER_SOURCES = 5

# Statuses that mean an event has already happened or been removed from play
_PAST_STATUSES = frozenset({
    "occurred", "modified", "prevented",
    "completed", "completed —",  # prefix match handled separately
})


def _is_past_event(status: str) -> bool:
    """Return True if the event status indicates it already happened or was removed."""
    if not status:
        return False
    lower = status.strip().lower()
    # Exact match
    if lower in _PAST_STATUSES:
        return True
    # Prefix match for statuses like "Completed — aftermath is active"
    if lower.startswith("completed"):
        return True
    return False


def _build_forbidden_knowledge_block(bible: dict) -> str:
    """Build the FORBIDDEN KNOWLEDGE enforcement block."""
    kb_boundaries = bible.get("knowledge_boundaries", {})
    forbidden = kb_boundaries.get("meta_knowledge_forbidden", [])
    if not forbidden:
        return ""

    items = forbidden[:_MAX_FORBIDDEN]
    lines = [
        "\n\n══ FORBIDDEN KNOWLEDGE — ABSOLUTE PROHIBITION ══",
        "NO character may know, reference, discuss, or hint at:",
    ]
    for item in items:
        lines.append(f'- "{item}"')
    lines.append(
        "If a character would logically know this, they STILL cannot — "
        "this is reader-only knowledge.\n"
        "Violation of this rule invalidates the chapter."
    )
    return "\n".join(lines)


def _build_character_secrets_block(bible: dict) -> str:
    """Build the CHARACTER SECRETS enforcement block."""
    kb_boundaries = bible.get("knowledge_boundaries", {})
    secrets = kb_boundaries.get("character_secrets", {})
    if not secrets:
        return ""

    lines = [
        "\n\n══ CHARACTER SECRETS — DO NOT LEAK ══",
    ]
    count = 0
    for char_name, secret_list in secrets.items():
        if count >= _MAX_SECRETS_CHARACTERS:
            break
        if not secret_list:
            continue

        # Handle both list-of-strings and list-of-dicts formats
        formatted_secrets: list[str] = []
        hidden_from: list[str] = []
        for entry in secret_list:
            if isinstance(entry, dict):
                formatted_secrets.append(entry.get("text", str(entry)))
                afh = entry.get("absolutely_hidden_from", [])
                if afh:
                    hidden_from.extend(afh if isinstance(afh, list) else [afh])
            else:
                formatted_secrets.append(str(entry))

        quoted = ", ".join(f'"{s}"' for s in formatted_secrets)
        line = f"{char_name}: HIDDEN — {quoted}"
        if hidden_from:
            line += f" [absolutely hidden from: {', '.join(hidden_from)}]"
        lines.append(line)
        count += 1

    lines.append(
        "Characters must NEVER reveal, discuss, or hint at secrets they "
        "don't canonically know."
    )
    return "\n".join(lines)


def _build_timeline_block(bible: dict) -> str:
    """Build the TIMELINE CONTEXT enforcement block with upcoming events."""
    meta = bible.get("meta", {})
    current_date = meta.get("current_story_date", "")

    # Gather upcoming events from canon_timeline
    canon_tl = bible.get("canon_timeline", {})
    all_events = canon_tl.get("events", [])

    upcoming: list[dict] = []
    for evt in all_events:
        status = evt.get("status", "")
        if _is_past_event(status):
            continue
        # Must have at minimum an event description
        if not evt.get("event"):
            continue
        upcoming.append(evt)

    if not upcoming and not current_date:
        return ""

    lines = ["\n\n══ TIMELINE CONTEXT ══"]
    if current_date:
        lines.append(f"Current story date: {current_date}")

    if upcoming:
        # Sort by date string if present (best-effort lexicographic sort)
        upcoming.sort(key=lambda e: e.get("date", "zzz"))
        upcoming = upcoming[:_MAX_TIMELINE_EVENTS]

        lines.append("UPCOMING / ACTIVE EVENTS (weave into narrative when relevant):")
        for evt in upcoming:
            date_str = evt.get("date", "TBD")
            event_name = evt.get("event", "")
            importance = evt.get("importance", "")
            imp_tag = f" — importance: {importance}" if importance else ""
            lines.append(f"- [{date_str}] {event_name}{imp_tag}")

        lines.append(
            "Do NOT skip events that are imminent. Address or foreshadow them."
        )

    return "\n".join(lines)


def _build_power_reference_block(bible: dict) -> str:
    """Build the POWER COMBAT REFERENCE enforcement block."""
    power_origins = bible.get("power_origins", {})
    sources = power_origins.get("sources", [])

    # Also gather top-level weaknesses list
    global_weaknesses = power_origins.get("weaknesses", [])

    if not sources and not global_weaknesses:
        return ""

    lines = ["\n\n══ POWER USAGE REFERENCE ══"]

    for src in sources[:_MAX_POWER_SOURCES]:
        name = src.get("name", "Unknown")
        lines.append(f"Source: {name}")

        combat_style = src.get("combat_style", "")
        if combat_style:
            lines.append(f"  Combat style: {combat_style}")

        # Try multiple field names for techniques
        techniques = (
            src.get("signature_moves")
            or src.get("canonical_techniques")
            or src.get("canon_techniques")
            or []
        )
        if techniques:
            tech_strs = []
            for t in techniques:
                tech_strs.append(str(t) if not isinstance(t, dict) else t.get("name", str(t)))
            lines.append(f"  Key techniques: {', '.join(tech_strs)}")

        limitations = src.get("limitations", "")
        if limitations:
            lines.append(f"  Limitations: {limitations}")

        # Per-source weaknesses (try multiple field names)
        src_weaknesses = (
            src.get("weaknesses_and_counters")
            or src.get("weaknesses")
            or []
        )
        if src_weaknesses:
            if isinstance(src_weaknesses, list):
                lines.append(f"  Weaknesses: {'; '.join(str(w) for w in src_weaknesses)}")
            else:
                lines.append(f"  Weaknesses: {src_weaknesses}")

    # Global weaknesses (shared across all sources)
    if global_weaknesses:
        lines.append("General weaknesses:")
        for w in global_weaknesses:
            lines.append(f"  - {w}")

    lines.append(
        "When writing combat, reference these specific techniques and styles. "
        "Show weaknesses being relevant."
    )
    return "\n".join(lines)


def _build_protected_characters_block(bible: dict) -> str:
    """Build the PROTECTED CHARACTERS / anti-Worfing enforcement block."""
    cci = bible.get("canon_character_integrity", {})
    protected = cci.get("protected_characters", [])
    jobber_rules = cci.get("jobber_prevention_rules", [])

    if not protected and not jobber_rules:
        return ""

    lines = ["\n\n══ PROTECTED CHARACTERS — ANTI-WORFING ══"]

    if protected:
        for p in protected[:10]:
            if isinstance(p, dict):
                name = p.get("name", "Unknown")
                competence = p.get("minimum_competence", "")
                notes = p.get("anti_worf_notes", "")
                lines.append(f"• {name}")
                if competence:
                    lines.append(f"  Minimum competence: {competence}")
                if notes:
                    lines.append(f"  Notes: {notes}")
            else:
                lines.append(f"• {p}")

    if jobber_rules:
        lines.append("RULES:")
        for rule in jobber_rules:
            lines.append(f"  - {rule}")

    lines.append(
        "NEVER make these characters lose to opponents below their level. "
        "If the OC wins, it MUST be justified by specific counter, ambush, "
        "or significant cost."
    )
    return "\n".join(lines)
