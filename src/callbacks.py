"""
ADK agent callbacks for validation, lifecycle logging, and error handling.

Provides:
- ``before_storyteller_callback``: Bible validation + timing start for Storyteller
- ``make_timing_callbacks``: Factory for before/after timing pairs on any agent
- ``tool_error_fallback``: Graceful tool-error handler (returns fallback string)
- ``before_storyteller_model_callback``: Injects dynamic chapter context into LLM request
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime as dt
from typing import Any, Optional

from google.genai import types
from sqlalchemy import select, func, desc

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
# 4. Shared session history trimming (preserves function-call pairs)
# ---------------------------------------------------------------------------

def _trim_to_current_turn(contents: list, agent_label: str) -> list:
    """Trim session history to the current turn while preserving function-call pairs.

    The ADK session accumulates every prior agent's turns.  For both the
    Archivist and Storyteller the current turn's user message already
    contains everything needed (Bible state, chapter context, player choice),
    and enforcement blocks are rebuilt fresh by the model callback.

    Key invariant: Gemini requires that (1) conversations start with a
    ``user`` turn, and (2) every ``function_call`` model turn is immediately
    followed by a ``function_response`` user turn.

    Important: in Gemini's wire format ``function_response`` parts carry
    ``role="user"``.  A naive "find last user message" therefore matches tool
    responses from prior agents (research swarm, lore keeper) instead of the
    actual user input, producing a trimmed list that starts with a ``model``
    turn → 400 INVALID_ARGUMENT from Gemini.

    We fix this by scanning for the last user message that contains actual
    **text** (not just ``function_response`` parts), then keeping everything
    from that point onward.  A post-trim validation strips any orphaned
    ``function_call``/``function_response`` pairs that slipped through.
    """
    if not contents or len(contents) <= 2:
        return contents

    original_count = len(contents)

    # Find the last REAL user message — one with text, not just function_response.
    last_user_idx = None
    for i in range(len(contents) - 1, -1, -1):
        msg = contents[i]
        if getattr(msg, "role", None) != "user":
            continue
        parts = getattr(msg, "parts", None) or []
        has_real_text = any(
            getattr(p, "text", None)
            for p in parts
            if getattr(p, "function_response", None) is None
        )
        if has_real_text:
            last_user_idx = i
            break

    if last_user_idx is None or last_user_idx == 0:
        return contents

    trimmed = contents[last_user_idx:]

    # Post-trim validation: strip orphaned function_call/function_response pairs
    trimmed = _strip_orphaned_fc_pairs(trimmed)

    if len(trimmed) < original_count:
        logger.info(
            "Trimmed %s session history: %d → %d messages",
            agent_label, original_count, len(trimmed),
        )
    return trimmed


def _strip_orphaned_fc_pairs(contents: list) -> list:
    """Remove model messages with orphaned function_call parts.

    Walks the contents list and ensures every ``model`` message containing
    ``function_call`` parts is immediately followed by a ``user`` message
    with ``function_response`` parts.  Unpaired messages are dropped.
    """
    result: list = []
    i = 0
    while i < len(contents):
        msg = contents[i]
        parts = getattr(msg, "parts", None) or []
        has_fc = any(
            getattr(p, "function_call", None) is not None for p in parts
        )

        if getattr(msg, "role", None) == "model" and has_fc:
            # Model with function_call — keep only if next message is function_response
            if i + 1 < len(contents):
                next_msg = contents[i + 1]
                next_parts = getattr(next_msg, "parts", None) or []
                has_fr = any(
                    getattr(p, "function_response", None) is not None
                    for p in next_parts
                )
                if has_fr:
                    result.append(msg)
                    result.append(next_msg)
                    i += 2
                    continue
            # Orphaned function_call — drop it
            logger.debug("Stripped orphaned function_call from %s history", "trim")
            i += 1
            continue

        result.append(msg)
        i += 1

    return result


# ---------------------------------------------------------------------------
# 4a. Archivist before-model callback (session history trimming)
# ---------------------------------------------------------------------------

async def before_archivist_model_callback(callback_context, llm_request):
    """Trim accumulated session history to prevent exceeding Gemini's 1M token limit.

    The ADK session accumulates every previous turn (each containing a full
    World Bible JSON dump + chapter text + BibleDelta output).  After ~8-10
    chapters this easily exceeds 1 048 576 tokens.  The Archivist only needs
    the *current* turn's user message — which already contains the Bible
    snapshot, chapter metadata, and the player's choice — so we slice the
    contents list down to just that.
    """
    llm_request.contents = _trim_to_current_turn(
        llm_request.contents, "Archivist"
    )
    return None


# ---------------------------------------------------------------------------
# 5. Storyteller before-model callback (dynamic context injection)
# ---------------------------------------------------------------------------

async def before_storyteller_model_callback(callback_context, llm_request):
    """Trim session history then inject dynamic enforcement data into the Storyteller's LLM request.

    Session trimming: identical rationale to the Archivist callback — the ADK
    session accumulates every prior turn (Bible dumps, tool calls, full
    chapters).  The current turn's input_text already contains chapter
    summaries, Bible state, and the player choice, and enforcement blocks are
    rebuilt fresh below, so historical turns are redundant.

    Then performs a single consolidated DB read to fetch chapter count, story
    config, and the World Bible, injecting enforcement blocks for: forbidden
    knowledge, character secrets, upcoming canon events, power system, etc.
    """
    # --- Trim accumulated session history (preserves function-call pairs) ---
    llm_request.contents = _trim_to_current_turn(
        llm_request.contents, "Storyteller"
    )

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

    # --- Fetch last chapter's question_answers + questions for FK continuity ---
    last_qa: dict = {}
    last_questions: list | None = None
    try:
        async with AsyncSessionLocal() as session:
            qa_stmt = (
                select(History)
                .where(History.story_id == story_id)
                .order_by(desc(History.sequence))
                .limit(1)
            )
            qa_result = await session.execute(qa_stmt)
            last_history = qa_result.scalar_one_or_none()
            if last_history and last_history.choices and isinstance(last_history.choices, dict):
                last_qa = last_history.choices.get("question_answers", {})
                last_questions = last_history.choices.get("questions")
    except Exception:
        logger.debug("Could not fetch last chapter question_answers")

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

        # 2. FORBIDDEN KNOWLEDGE + CHARACTER SECRETS (merged enforcement block)
        instructions.append(
            _build_forbidden_knowledge_enforcement_block(bible_content)
        )

        # 2.5 CHARACTER IDENTITY CONSTRAINTS (hard rules from player setup)
        instructions.append(
            _build_character_identity_enforcement_block(bible_content)
        )

        # 3. UPCOMING CANON EVENTS / TIMELINE (enforcement-grade with pressure scores)
        instructions.append(
            _build_timeline_enforcement_block(bible_content, chapter_count)
        )

        # 4. POWER SYSTEM ENFORCEMENT
        instructions.append(
            _build_power_enforcement_block(bible_content, chapter_count)
        )

        # 5. PROTECTED CHARACTERS / ANTI-WORFING
        instructions.append(
            _build_protected_characters_block(bible_content)
        )

        # 6. CHARACTER BEHAVIOR & VOICES (personality, speech, mannerisms)
        instructions.append(
            _build_character_behavior_block(bible_content)
        )

        # 7. AUTO-ENRICH event playbooks from source text (lazy, one-time per event)
        try:
            await _maybe_enrich_event_playbooks(story_id, bible_content)
        except Exception:
            logger.debug("Event playbook auto-enrichment skipped", exc_info=True)

        # 7b. EVENT PLAYBOOK (narrative beats for upcoming major events)
        instructions.append(
            _build_event_playbook_block(bible_content, chapter_count)
        )

        # 8. Previous chapter's player FK/timeline answers (carry forward)
        if last_qa:
            instructions.append(
                _build_previous_qa_block(last_qa, last_questions)
            )

    # Filter out empty strings (blocks that had no data)
    instructions = [blk for blk in instructions if blk]

    llm_request.append_instructions(instructions)
    return None  # never skip the model call


# ---------------------------------------------------------------------------
# 4a. Enforcement block builders (pure functions, no I/O)
# ---------------------------------------------------------------------------

_MAX_FORBIDDEN = 30
_MAX_PER_CHARACTER_BLOCKS = 8
_MAX_COMMON_VIOLATIONS = 5
_MAX_POWER_SOURCES = 5
_MAX_PLAYBOOK_EVENTS = 3

# Timeline enforcement caps
_MAX_MANDATORY_EVENTS = 5
_MAX_HIGH_EVENTS = 5
_MAX_MEDIUM_EVENTS = 5

# Statuses that mean an event has already happened or been removed from play
_PAST_STATUSES = frozenset({
    "occurred", "modified", "prevented",
    "completed", "completed —",  # prefix match handled separately
    "historical", "past",        # pre-story lore events from init pipeline
})

# Category keywords for forbidden knowledge classification
_FK_CATEGORY_KEYWORDS = {
    "FUTURE_EVENTS": [
        "will", "future", "eventually", "later", "upcoming", "arc", "incident",
        "invasion", "war", "attack", "battle", "defeat", "death of", "dies",
        "falls", "betrayal", "reveal", "awakening",
    ],
    "HIDDEN_IDENTITIES": [
        "identity", "secretly", "true name", "real name", "is actually",
        "disguised", "alias", "undercover", "civilian", "cape name",
        "double life", "alter ego", "hidden role", "true form",
    ],
    "META_KNOWLEDGE": [
        "reader", "audience", "fourth wall", "meta", "narrative",
        "plot", "author", "story", "chapter", "canon", "original",
        "universe", "multiverse", "reincarnation", "transmigration",
    ],
    "POWER_SECRETS": [
        "power", "technique", "ability", "weakness", "limitation",
        "secret technique", "trump card", "domain", "cursed", "innate",
        "true power", "full potential", "sealed", "restricted", "hidden ability",
    ],
}

# Common violation patterns the Storyteller must avoid
_COMMON_VIOLATION_PATTERNS = [
    'No character may "sense" or "feel" forbidden knowledge through intuition, psychic ability, or vague premonition.',
    "The narrator must NOT reveal hidden identities in POV sections of characters who don't know them.",
    "Characters must NOT display knowledge they haven't acquired on-screen — even if it's 'common sense' to the reader.",
    "Do NOT write scenes where a character 'almost' discovers forbidden info unless the plan specifically approves it.",
    "No convenient info-dumps from NPCs that bypass established knowledge barriers.",
]


def _is_past_event(status: str) -> bool:
    """Return True if the event status indicates it already happened or was removed."""
    if not status:
        return False
    lower = status.strip().lower()
    if lower in _PAST_STATUSES:
        return True
    if lower.startswith("completed"):
        return True
    return False


def _is_pre_story_event(event: dict, story_start_dt) -> bool:
    """Return True if an event clearly happened before the story began.

    Catches lore events from the init pipeline (e.g., JJK Shibuya Incident
    from 2018 in a 2095 Mahouka story) that the Lore Keeper tagged with
    a wrong or missing status.  Uses a 7-day tolerance so events happening
    right around the story start (like enrollment ceremonies) are kept.
    """
    if not story_start_dt:
        return False
    event_dt = _parse_story_date(event.get("date", ""))
    if not event_dt:
        return False
    # If event is more than 7 days before story start, it's pre-story
    return (story_start_dt - event_dt).days > 7


# ---------------------------------------------------------------------------
# 4b. Date parsing and pressure scoring (pure functions for callback hot path)
# ---------------------------------------------------------------------------

def _parse_story_date(date_str: str) -> dt | None:
    """Parse story date strings into datetime, stripping parenthetical qualifiers.

    Handles: "April 11, 2095 (Evening)" → April 11, 2095
             "April 2095" → April 1, 2095
             "2095-04-11" → April 11, 2095
    Adapted from core_tools.py:_parse_date without DB I/O.
    """
    if not date_str:
        return None

    # Strip parenthetical qualifiers like "(Evening)", "(Morning)", "(Night)"
    cleaned = re.sub(r'\s*\([^)]*\)\s*', '', date_str).strip()

    formats = [
        "%B %d, %Y",       # "April 11, 2095"
        "%B %Y",            # "April 2095"
        "%Y-%m-%d",         # "2095-04-11"
        "%Y-%m",            # "2095-04"
        "%d %B %Y",         # "11 April 2095"
    ]

    for fmt in formats:
        try:
            return dt.strptime(cleaned, fmt)
        except ValueError:
            continue

    # Last resort: extract year
    year_match = re.search(r'(\d{4})', cleaned)
    if year_match:
        return dt(int(year_match.group(1)), 1, 1)

    return None


def _compute_pressure_score(
    event: dict,
    current_dt: dt | None,
    protagonist_name: str,
    all_events: list[dict],
) -> dict:
    """Compute pressure score for a canon event (pure function, no DB I/O).

    Replicates the formula from core_tools.py:calculate_event_pressure:
        P = (Ic * Td * Pd * Cd) / Nf

    Returns dict with: pressure_score, urgency, days_remaining, is_overdue
    """
    event_dt = _parse_story_date(event.get("date", ""))

    # Factor 1: Importance Coefficient (Ic)
    importance_map = {"major": 3.0, "minor": 1.0, "background": 0.5}
    Ic = importance_map.get(event.get("importance", "minor"), 1.0)

    # Factor 2: Time Distance (Td)
    if current_dt and event_dt:
        days_remaining = (event_dt - current_dt).days
    else:
        days_remaining = 30  # default if dates unparseable

    is_overdue = days_remaining < 0
    Td = max(0.1, 10 / (max(days_remaining, 0) + 1))

    # Factor 3: Plot Dependency (Pd)
    consequences = event.get("consequences", [])
    dependent_count = sum(
        1 for e in all_events
        if any(c in str(e) for c in consequences)
    ) if consequences else 0
    Pd = 1.0 + (dependent_count * 0.3)

    # Factor 4: Character Involvement (Cd)
    involved = event.get("characters_involved", [])
    Cd = 1.5 if protagonist_name and protagonist_name in involved else 1.0

    # Factor 5: Narrative Flexibility (Nf)
    Nf = 0.5 if len(involved) > 5 else 1.0

    pressure_score = min(10.0, (Ic * Td * Pd * Cd) / Nf)

    return {
        "pressure_score": round(pressure_score, 2),
        "days_remaining": days_remaining,
        "is_overdue": is_overdue,
    }


# ---------------------------------------------------------------------------
# 4c. Forbidden knowledge categorization
# ---------------------------------------------------------------------------

def _categorize_forbidden_item(item: str) -> str:
    """Categorize a forbidden knowledge item by keyword heuristic.

    Returns one of: FUTURE_EVENTS, HIDDEN_IDENTITIES, META_KNOWLEDGE, POWER_SECRETS
    Falls back to META_KNOWLEDGE if no match.
    """
    lower = item.lower()
    best_category = "META_KNOWLEDGE"
    best_score = 0

    for category, keywords in _FK_CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score > best_score:
            best_score = score
            best_category = category

    return best_category


_FK_CATEGORY_LANGUAGE = {
    "FUTURE_EVENTS": (
        "These are FUTURE EVENTS that have NOT happened yet in the story. "
        "No character may reference, foreshadow, or hint at these unless "
        "the plan explicitly approves it."
    ),
    "HIDDEN_IDENTITIES": (
        "These identities are SECRET. No character (including the narrator "
        "in that character's POV) may reveal, hint at, or 'sense' these."
    ),
    "META_KNOWLEDGE": (
        "This is OUT-OF-UNIVERSE information. No character may know, "
        "reference, or reason toward this knowledge."
    ),
    "POWER_SECRETS": (
        "These power-related secrets are UNDISCLOSED. No character may "
        "demonstrate awareness of these abilities or limitations."
    ),
}


# ---------------------------------------------------------------------------
# 4d. New enforcement block builders
# ---------------------------------------------------------------------------

def _deduplicate_forbidden_items(items: list[str]) -> list[str]:
    """Remove near-duplicate FK items, keeping the most complete version.

    If item A is a substring of a longer item B, drop A and keep B.
    O(n²) but n is capped at _MAX_FORBIDDEN (30).
    """
    if len(items) <= 1:
        return items

    normalized = [(item, item.lower().strip()) for item in items]
    keep = []
    for i, (item, norm) in enumerate(normalized):
        is_dup = False
        for j, (other_item, other_norm) in enumerate(normalized):
            if i != j and len(other_norm) > len(norm) and norm in other_norm:
                is_dup = True  # This item is a substring of a more complete one
                break
        if not is_dup:
            keep.append(item)
    return keep


def _build_forbidden_knowledge_enforcement_block(bible: dict) -> str:
    """Build the merged FORBIDDEN KNOWLEDGE + CHARACTER SECRETS enforcement block.

    Improvements over the old split blocks:
    - Categorizes forbidden items into FUTURE_EVENTS, HIDDEN_IDENTITIES, META_KNOWLEDGE, POWER_SECRETS
    - Groups items by category with category-specific enforcement language
    - Builds PER-CHARACTER RESTRICTIONS from character_knowledge_limits + character_secrets
    - Adds COMMON VIOLATION PATTERNS section
    - Thinness detection: warns if <10 forbidden items
    - Deduplicates near-duplicate items within each category (Fix 7)
    """
    kb_boundaries = bible.get("knowledge_boundaries", {})
    forbidden = kb_boundaries.get("meta_knowledge_forbidden", [])
    secrets = kb_boundaries.get("character_secrets", {})
    knowledge_limits = kb_boundaries.get("character_knowledge_limits", {})

    # Guard against double-serialized JSON strings from LLM agents
    if isinstance(secrets, str):
        try:
            secrets = json.loads(secrets)
        except (json.JSONDecodeError, TypeError):
            secrets = {}
    if isinstance(knowledge_limits, str):
        try:
            knowledge_limits = json.loads(knowledge_limits)
        except (json.JSONDecodeError, TypeError):
            knowledge_limits = {}

    if not forbidden and not secrets and not knowledge_limits:
        return ""

    lines = [
        "\n\n══ FORBIDDEN KNOWLEDGE & CHARACTER SECRETS — ENFORCEMENT ══",
        "[!!!] VIOLATION OF THESE RULES INVALIDATES THE CHAPTER.",
    ]

    # --- Section 1: Categorized forbidden items ---
    if forbidden:
        items = forbidden[:_MAX_FORBIDDEN]

        # Group by category
        categories: dict[str, list[str]] = {}
        for item in items:
            cat = _categorize_forbidden_item(str(item))
            categories.setdefault(cat, []).append(str(item))

        # Emit each category with its enforcement language (deduplicated)
        category_order = ["FUTURE_EVENTS", "HIDDEN_IDENTITIES", "POWER_SECRETS", "META_KNOWLEDGE"]
        for cat in category_order:
            cat_items = categories.get(cat, [])
            if not cat_items:
                continue
            # Fix 7: Deduplicate near-duplicate items within each category
            cat_items = _deduplicate_forbidden_items(cat_items)
            lines.append(f"\n▸ {cat.replace('_', ' ')} ({len(cat_items)} items):")
            lines.append(f"  {_FK_CATEGORY_LANGUAGE[cat]}")
            for item in cat_items:
                lines.append(f'  - "{item}"')

    # --- Section 2: Per-character restrictions ---
    char_blocks_emitted = 0
    all_character_names = set(secrets.keys()) | set(knowledge_limits.keys())

    if all_character_names:
        lines.append("\n▸ PER-CHARACTER RESTRICTIONS:")

        for char_name in sorted(all_character_names):
            if char_blocks_emitted >= _MAX_PER_CHARACTER_BLOCKS:
                lines.append(f"  ... and {len(all_character_names) - char_blocks_emitted} more characters")
                break

            char_lines = [f"  [{char_name}]"]

            # Character secrets — may be a single dict or a list of dicts
            char_secrets = secrets.get(char_name, [])
            if char_secrets:
                # Normalize to list: single dict → [dict], string → [string]
                if isinstance(char_secrets, dict):
                    char_secrets = [char_secrets]
                elif isinstance(char_secrets, str):
                    char_secrets = [char_secrets]

                for entry in char_secrets:
                    if isinstance(entry, dict):
                        secret_text = entry.get("text", entry.get("secret", str(entry)))
                        hidden_from = entry.get("absolutely_hidden_from", [])
                        if hidden_from:
                            hf = hidden_from if isinstance(hidden_from, list) else [hidden_from]
                            char_lines.append(f'    SECRET: "{secret_text}" [HIDDEN FROM: {", ".join(hf)}]')
                        else:
                            char_lines.append(f'    SECRET: "{secret_text}"')
                    else:
                        char_lines.append(f'    SECRET: "{entry}"')

            # Character knowledge limits
            char_limits = knowledge_limits.get(char_name, {})
            if isinstance(char_limits, dict):
                doesnt_know = char_limits.get("doesnt_know", [])
                suspects = char_limits.get("suspects", [])
                if doesnt_know:
                    dk_str = "; ".join(str(d) for d in doesnt_know[:5])
                    char_lines.append(f"    DOES NOT KNOW: {dk_str}")
                if suspects:
                    s_str = "; ".join(str(s) for s in suspects[:3])
                    char_lines.append(f"    SUSPECTS (may investigate but NOT confirm): {s_str}")

            if len(char_lines) > 1:  # has content beyond the header
                lines.extend(char_lines)
                char_blocks_emitted += 1

    # --- Section 3: Common violation patterns ---
    lines.append("\n▸ COMMON VIOLATION PATTERNS — DO NOT COMMIT THESE:")
    for pattern in _COMMON_VIOLATION_PATTERNS[:_MAX_COMMON_VIOLATIONS]:
        lines.append(f"  ✘ {pattern}")

    # --- Section 4: Thinness detection ---
    if len(forbidden) < 10:
        lines.append(
            "\n[SYSTEM WARNING] Forbidden knowledge list is THIN "
            f"({len(forbidden)} items). Consider calling discover_forbidden_knowledge() "
            "or trigger_research() to identify missing restrictions. "
            "A thin list means violations are likely to slip through."
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Identity constraint keywords — phrases indicating what the protagonist IS NOT
# ---------------------------------------------------------------------------
_IDENTITY_NEGATION_PATTERNS = [
    "no clan", "no lineage", "no political", "no family magic",
    "no bloodline", "no affiliation", "not an heir", "not a heir",
    "no one monitors", "no one suspects",
    "no ancient grimoires", "no backstory secret", "no drawback",
    "normal household", "no magical lineage", "no association",
    "orphan", "has no clan", "no clan claims",
]

# Lines matching these patterns are noise, not identity constraints
_IDENTITY_FALSE_POSITIVE_PATTERNS = [
    "operates independently",  # power system description, not identity
    "public record",           # metadata field label, not a constraint
]


def _build_character_identity_enforcement_block(bible: dict) -> str:
    """Build the CHARACTER IDENTITY CONSTRAINTS enforcement block.

    Extracts hard identity rules the player specified in their setup
    conversation and injects them as non-negotiable constraints.

    Data sources (all in Bible):
    - meta.setup_conversation[0].content — raw user framework
    - meta.user_intent — summarized character intent
    - meta.character_origin — e.g. "Original Character (Kageaki Ren)"
    - meta.power_limitations — power constraint text
    - character_sheet.name, .archetype, .identities — identity profile
    """
    meta = bible.get("meta", {})
    char_sheet = bible.get("character_sheet", {})

    protagonist_name = char_sheet.get("name", "")
    if not protagonist_name:
        return ""

    # --- Extract explicit player constraints from setup_conversation ---
    setup_conv = meta.get("setup_conversation", [])
    user_framework = ""
    if setup_conv and isinstance(setup_conv, list):
        # First user message contains the full character framework
        for msg in setup_conv:
            if isinstance(msg, dict) and msg.get("role") == "user":
                user_framework = msg.get("content", "")
                break

    explicit_constraints: list[str] = []
    if user_framework:
        for line in user_framework.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            # Skip false positives (power system descriptions, field labels)
            if any(fp in lower for fp in _IDENTITY_FALSE_POSITIVE_PATTERNS):
                continue
            # Check if this line contains an identity negation pattern
            for pattern in _IDENTITY_NEGATION_PATTERNS:
                if pattern in lower:
                    # Strip markdown formatting and list prefixes
                    clean = stripped.lstrip("*-# ").rstrip(".*")
                    if clean:
                        explicit_constraints.append(clean)
                    break

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for c in explicit_constraints:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(c)
    explicit_constraints = deduped

    # --- Build the block ---
    user_intent = meta.get("user_intent", "")
    character_origin = meta.get("character_origin", "")
    power_limitations = meta.get("power_limitations", "")
    identities = char_sheet.get("identities", {})

    # If we have nothing to say, skip
    if not explicit_constraints and not user_intent and not character_origin:
        return ""

    lines = [
        f"\n\n══ CHARACTER IDENTITY CONSTRAINTS — {protagonist_name} ══",
        "[!!!] THESE ARE HARD RULES FROM THE PLAYER. VIOLATION INVALIDATES THE CHAPTER.",
    ]

    # Character origin
    if character_origin:
        lines.append(f"\n▸ CHARACTER ORIGIN: {character_origin}")

    # Explicit player constraints (the core of this block)
    if explicit_constraints:
        lines.append(
            f"\n▸ EXPLICIT PLAYER CONSTRAINTS ({len(explicit_constraints)} rules):"
        )
        for c in explicit_constraints:
            lines.append(f"  ✘ {c}")
        lines.append(
            "  These constraints are ABSOLUTE. Do NOT contradict, soften, "
            "or narratively subvert any of them. They define who the character IS."
        )

    # Identity profile from character_sheet.identities
    if identities:
        lines.append("\n▸ IDENTITY PROFILE:")
        for identity_key, identity_data in identities.items():
            if isinstance(identity_data, dict):
                id_name = identity_data.get("name", "")
                is_public = identity_data.get("is_public", False)
                team = identity_data.get("team_affiliation", "")
                reputation = identity_data.get("reputation", "")
                visibility = "PUBLIC" if is_public else "SECRET"
                label = identity_key.upper()
                if team:
                    lines.append(f"  {label} ({visibility}): {team}")
                if reputation:
                    lines.append(f"    Reputation: {reputation}")

    # Player intent (treat as ground truth)
    if user_intent:
        lines.append(f"\n▸ PLAYER INTENT (treat as ground truth):")
        lines.append(f"  {user_intent}")

    # Power constraints
    if power_limitations:
        lines.append(f"\n▸ POWER CONSTRAINTS:")
        lines.append(f"  {power_limitations}")

    return "\n".join(lines)


def _build_timeline_enforcement_block(bible: dict, chapter_count: int) -> str:
    """Build the TIMELINE enforcement block with pressure-scored events.

    Improvements over the old _build_timeline_block:
    - Computes pressure scores inline (no DB I/O)
    - Categorizes into MANDATORY (pressure >= 7.0 or overdue), HIGH (>= 5.0), MEDIUM (>= 3.0)
    - Includes chapter-date context from story_timeline.chapter_dates
    - Flags OVERDUE events explicitly
    - Uses imperative mandate language
    """
    meta = bible.get("meta", {})
    current_date_str = meta.get("current_story_date", "")
    current_dt_parsed = _parse_story_date(current_date_str)

    protagonist_name = bible.get("character_sheet", {}).get("name", "")

    # Gather upcoming events from canon_timeline
    canon_tl = bible.get("canon_timeline", {})
    all_events = canon_tl.get("events", [])

    upcoming: list[dict] = []
    for evt in all_events:
        status = evt.get("status", "")
        if _is_past_event(status):
            continue
        if not evt.get("event"):
            continue
        # Fix 1: Skip events whose date is >1 year before current story date (historical)
        if current_dt_parsed:
            event_dt = _parse_story_date(evt.get("date", ""))
            if event_dt and (current_dt_parsed - event_dt).days > 365:
                continue
        upcoming.append(evt)

    # Fix 4: Deduplicate by normalized event name (keep most detailed entry)
    seen: dict[str, dict] = {}
    for evt in upcoming:
        normalized = evt.get("event", "").strip().lower().lstrip("the ")
        if normalized in seen:
            existing = seen[normalized]
            if len(evt.get("significance", "")) > len(existing.get("significance", "")):
                seen[normalized] = evt
        else:
            seen[normalized] = evt
    upcoming = list(seen.values())

    if not upcoming and not current_date_str:
        return ""

    lines = ["\n\n══ TIMELINE ENFORCEMENT ══"]
    if current_date_str:
        lines.append(f"Current story date: {current_date_str}")
        lines.append(f"Chapters completed: {chapter_count}")

    # Fix 5: FK cross-reference safety net
    forbidden = bible.get("knowledge_boundaries", {}).get("meta_knowledge_forbidden", [])
    if forbidden:
        lines.append(
            "NOTE: If a MANDATORY event involves concepts from FORBIDDEN KNOWLEDGE, "
            "address the event's consequences and impact WITHOUT revealing forbidden details."
        )

    # Add chapter-date context if available
    story_tl = bible.get("story_timeline", {})
    chapter_dates = story_tl.get("chapter_dates", [])
    if chapter_dates:
        recent = chapter_dates[-3:]  # last 3 chapters
        date_ctx = ", ".join(
            f"Ch.{cd.get('chapter', '?')}: {cd.get('date', '?')}"
            for cd in recent
        )
        lines.append(f"Recent chapter dates: {date_ctx}")

    if not upcoming:
        return "\n".join(lines)

    # Compute pressure scores for all upcoming events
    scored_events: list[tuple[dict, dict]] = []
    for evt in upcoming:
        pressure = _compute_pressure_score(evt, current_dt_parsed, protagonist_name, all_events)
        scored_events.append((evt, pressure))

    # Sort by pressure descending
    scored_events.sort(key=lambda x: x[1]["pressure_score"], reverse=True)

    # Categorize
    mandatory: list[tuple[dict, dict]] = []
    high: list[tuple[dict, dict]] = []
    medium: list[tuple[dict, dict]] = []

    for evt, pressure in scored_events:
        p = pressure["pressure_score"]
        if p >= 7.0 or pressure["is_overdue"]:
            mandatory.append((evt, pressure))
        elif p >= 5.0:
            high.append((evt, pressure))
        elif p >= 3.0:
            medium.append((evt, pressure))

    # Emit MANDATORY events
    if mandatory:
        lines.append(
            f"\n[!!!] MANDATORY — These events MUST appear in this chapter ({len(mandatory)}):"
        )
        for evt, pressure in mandatory[:_MAX_MANDATORY_EVENTS]:
            date_str = evt.get("date", "TBD")
            event_name = evt.get("event", "")
            p_score = pressure["pressure_score"]
            days = pressure["days_remaining"]
            overdue_tag = " ⚠ OVERDUE" if pressure["is_overdue"] else ""
            lines.append(
                f"  [!!!] [{date_str}] {event_name} "
                f"(pressure: {p_score}{overdue_tag}, days: {days})"
            )
            lines.append(
                "        → This event MUST be directly addressed: as a scene, "
                "a witnessed event, or a consequence felt by characters."
            )

    # Emit HIGH events
    if high:
        lines.append(
            f"\n[!!] HIGH PRIORITY — Foreshadow or address within 1-2 chapters ({len(high)}):"
        )
        for evt, pressure in high[:_MAX_HIGH_EVENTS]:
            date_str = evt.get("date", "TBD")
            event_name = evt.get("event", "")
            p_score = pressure["pressure_score"]
            lines.append(
                f"  [!!] [{date_str}] {event_name} (pressure: {p_score})"
            )
            lines.append(
                "       → Foreshadow this: rumors, character awareness, environmental signs."
            )

    # Emit MEDIUM events
    if medium:
        lines.append(
            f"\n[!] MEDIUM — Consider mentioning when narratively appropriate ({len(medium)}):"
        )
        for evt, pressure in medium[:_MAX_MEDIUM_EVENTS]:
            date_str = evt.get("date", "TBD")
            event_name = evt.get("event", "")
            p_score = pressure["pressure_score"]
            lines.append(
                f"  [!] [{date_str}] {event_name} (pressure: {p_score})"
            )

    lines.append(
        "\nTimeline compliance is NON-NEGOTIABLE. MANDATORY events that are "
        "ignored will cause the chapter to be rejected."
    )

    return "\n".join(lines)


def _build_previous_qa_block(
    last_qa: dict,
    last_questions: list[dict] | None = None,
) -> str:
    """Build a block carrying forward the player's FK/timeline answers from last chapter.

    When ``last_questions`` is provided (from ``History.choices.questions``),
    each answer is paired with its original question text so the Storyteller
    sees the full context.  FK answers are tagged with ``[FK]`` and
    breakthrough/confirmed answers add an Archivist note.
    """
    if not last_qa:
        return ""

    # Build a question-text lookup from last_questions (index-keyed)
    q_lookup: dict[str, str] = {}
    q_category: dict[str, str] = {}
    if last_questions and isinstance(last_questions, list):
        for i, q in enumerate(last_questions):
            if isinstance(q, dict):
                q_lookup[str(i)] = q.get("question", "")
                q_category[str(i)] = q.get("category", "")

    lines = [
        "\n\n══ PLAYER'S PREVIOUS CHAPTER DECISIONS ══",
        "The player made these FK/timeline decisions last chapter. RESPECT them:",
    ]

    _FK_CONFIRMED_KEYWORDS = {"yes", "clue", "breakthrough", "confirmed", "slips through"}

    for idx, answer in sorted(last_qa.items(), key=lambda x: (int(x[0]) if str(x[0]).isdigit() else float('inf'), str(x[0]))):
        idx_str = str(idx)
        is_fk = q_category.get(idx_str) == "forbidden_knowledge"
        tag = " [FK]" if is_fk else ""

        question_text = q_lookup.get(idx_str, "")
        if question_text:
            lines.append(f"  - Q: {question_text}")
            lines.append(f"    A{tag}: {answer}")
        else:
            lines.append(f"  - Q{idx}{tag}: {answer}")

        # If an FK answer indicates confirmation, tell the Archivist to update
        if is_fk and isinstance(answer, str):
            answer_lower = answer.lower()
            if any(kw in answer_lower for kw in _FK_CONFIRMED_KEYWORDS):
                lines.append(
                    "    → [ARCHIVIST NOTE] Player confirmed FK breakthrough. "
                    "Update knowledge_boundaries accordingly."
                )

    lines.append(
        "These decisions remain in effect unless the player explicitly changes them."
    )
    return "\n".join(lines)


_MAX_TECHNIQUES_PER_SOURCE = 8
_MAX_SCENE_EXAMPLES_PER_SOURCE = 3
_MAX_POWER_INTERACTIONS = 5
_MAX_MEDIUM_STRAIN_ENTRIES = 5

# Strain severity ordering for aggregation
_STRAIN_SEVERITY = {"critical": 4, "high": 3, "medium": 2, "low": 1, "none": 0}


def _compute_cumulative_strain(
    usage_tracking: dict,
    chapter_count: int,
) -> dict:
    """Analyze power_origins.usage_tracking to compute cumulative strain with recency weighting.

    Returns dict with:
      - high_critical: list of (key, strain_level, last_chapter) for HIGH/CRITICAL strain
      - medium: list of (key, strain_level, last_chapter) for MEDIUM strain
      - summary: human-readable summary string
    """
    high_critical: list[tuple[str, str, int]] = []
    medium: list[tuple[str, str, int]] = []

    for key, data in usage_tracking.items():
        if not isinstance(data, dict):
            continue
        raw_strain = data.get("strain_level", "none").strip().lower()
        last_ch = data.get("last_chapter", 0)

        # Recency weighting: strain from >10 chapters ago fades one tier
        chapters_ago = max(0, chapter_count - last_ch) if chapter_count and last_ch else 0
        effective_strain = raw_strain
        if chapters_ago > 10:
            # Fade two tiers
            severity = _STRAIN_SEVERITY.get(raw_strain, 0)
            effective_severity = max(0, severity - 2)
            for name, val in _STRAIN_SEVERITY.items():
                if val == effective_severity:
                    effective_strain = name
                    break
        elif chapters_ago > 5:
            # Fade one tier
            severity = _STRAIN_SEVERITY.get(raw_strain, 0)
            effective_severity = max(0, severity - 1)
            for name, val in _STRAIN_SEVERITY.items():
                if val == effective_severity:
                    effective_strain = name
                    break

        if effective_strain in ("high", "critical"):
            high_critical.append((key, effective_strain, last_ch))
        elif effective_strain == "medium":
            medium.append((key, effective_strain, last_ch))

    # Sort by last_chapter descending (most recent first)
    high_critical.sort(key=lambda x: x[2], reverse=True)
    medium.sort(key=lambda x: x[2], reverse=True)

    total_strained = len(high_critical) + len(medium)
    summary = f"{total_strained} powers strained"
    if high_critical:
        summary += f" ({len(high_critical)} at HIGH/CRITICAL)"

    return {
        "high_critical": high_critical,
        "medium": medium,
        "summary": summary,
    }


def _build_power_enforcement_block(bible: dict, chapter_count: int) -> str:
    """Build the POWER SYSTEM ENFORCEMENT block.

    Replaces the old passive _build_power_reference_block with an enforcement-grade
    block that surfaces:
    - Power scale from meta + character_sheet
    - Per-source techniques with costs, limitations, mastery, and strain
    - Canon scene examples as writing templates
    - Power interactions (hybrid synergies)
    - Cumulative strain status with recency weighting
    - Scaling rules from jobber_prevention_rules
    - Common power violation patterns
    """
    power_origins = bible.get("power_origins", {})
    sources = power_origins.get("sources", [])
    global_weaknesses = power_origins.get("weaknesses", [])

    # Normalize sources: some stories store as dict {"Limitless": {...}} instead of list
    if isinstance(sources, dict):
        sources = [
            {**v, "power_name": v.get("power_name", k)} if isinstance(v, dict) else {"power_name": k}
            for k, v in sources.items()
        ]

    if not sources and not global_weaknesses:
        return ""

    lines = [
        "\n\n══ POWER SYSTEM ENFORCEMENT ══",
        "[!!!] ALL power usage MUST follow these rules. Violations invalidate the chapter.",
    ]

    # --- Power scale from meta + character_sheet ---
    meta = bible.get("meta", {})
    char_sheet = bible.get("character_sheet", {})
    power_level = (
        char_sheet.get("status", {}).get("power_level")
        or meta.get("power_level")
        or ""
    )
    protagonist_name = char_sheet.get("name", "the protagonist")

    if power_level:
        level_upper = power_level.upper().split("/")[0].strip()
        lines.append(f"\n▸ POWER SCALE: [{level_upper}]-CLASS")
        lines.append(
            f"  {protagonist_name} operates at {level_upper} scale. DO NOT downplay."
        )
        lines.append(
            "  Opposition MUST use documented counters, not raw strength matching."
        )
        lines.append(
            "  Invented limitations not in power_origins are FORBIDDEN."
        )

    # --- Active power sources ---
    usage_tracking = power_origins.get("usage_tracking", {})

    if sources:
        lines.append(f"\n▸ ACTIVE POWER SOURCES ({len(sources[:_MAX_POWER_SOURCES])} sources):")

    for src in sources[:_MAX_POWER_SOURCES]:
        name = src.get("power_name", src.get("name", "Unknown"))
        short_name = name.split("(")[1].rstrip(")") if "(" in name else name[:12]

        lines.append(f"\n  [{name}]")

        # Combat style
        combat_style = src.get("combat_style", "")
        if combat_style:
            lines.append(f"    Combat style: {combat_style}")

        # Mastery
        mastery = src.get("oc_current_mastery", "")
        if mastery:
            lines.append(f"    Mastery: {mastery}")

        # Current strain (aggregate from usage_tracking entries matching this source)
        source_strain = _find_source_strain(name, short_name, usage_tracking)
        if source_strain:
            strain_level, last_ch = source_strain
            lines.append(
                f"    Current strain: {strain_level.upper()} (last used Ch.{last_ch})"
                + (" ← SHOW EXHAUSTION EFFECTS" if strain_level in ("high", "critical") else "")
            )

        # Techniques (canon_techniques with per-technique costs/limitations)
        techniques = src.get("canon_techniques", src.get("canonical_techniques", []))
        if techniques:
            lines.append("    Techniques (use ONLY these):")
            for tech in techniques[:_MAX_TECHNIQUES_PER_SOURCE]:
                if isinstance(tech, dict):
                    tech_name = tech.get("name", "?")
                    desc = tech.get("description", "")
                    cost = tech.get("cost", "")
                    limitations = tech.get("limitations", [])
                    limit_str = "; ".join(str(l) for l in limitations) if isinstance(limitations, list) else str(limitations)
                    detail_parts = []
                    if desc:
                        detail_parts.append(desc)
                    if cost:
                        detail_parts.append(f"cost: {cost}")
                    if limit_str:
                        detail_parts.append(f"limits: {limit_str}")
                    if detail_parts:
                        lines.append(f"      • {tech_name} — {detail_parts[0]}")
                        for dp in detail_parts[1:]:
                            lines.append(f"        [{dp}]")
                    else:
                        lines.append(f"      • {tech_name}")
                else:
                    lines.append(f"      • {tech}")

        # Weaknesses (opponents SHOULD exploit)
        src_weaknesses = src.get("weaknesses_and_counters", src.get("weaknesses", []))
        if src_weaknesses:
            lines.append("    Weaknesses (opponents SHOULD exploit these):")
            weak_list = src_weaknesses if isinstance(src_weaknesses, list) else [src_weaknesses]
            for w in weak_list:
                lines.append(f"      • {w}")

        # Canon scene examples (writing templates)
        scene_examples = src.get("canon_scene_examples", [])
        if scene_examples:
            lines.append("    Canon Usage Templates (write combat LIKE THIS):")
            for ex in scene_examples[:_MAX_SCENE_EXAMPLES_PER_SOURCE]:
                if isinstance(ex, dict):
                    scene = ex.get("scene", "?")
                    how = ex.get("how_deployed", "")
                    lines.append(f"      • {scene}: {how}")
                else:
                    lines.append(f"      • {ex}")

    # --- Top-level canon scene examples (not per-source) ---
    top_level_examples = power_origins.get("canon_scene_examples", [])
    if top_level_examples:
        lines.append("\n  [Global Canon Scene References]")
        lines.append("    Study these for power writing style:")
        for ex in top_level_examples[:5]:
            if isinstance(ex, dict):
                scene = ex.get("scene", "?")
                how = ex.get("how_deployed", "")
                outcome = ex.get("outcome", "")
                lines.append(f"      • {scene}: {how}")
                if outcome:
                    lines.append(f"        → Outcome: {outcome}")
            else:
                lines.append(f"      • {ex}")

    # --- Power interactions (hybrid synergies) ---
    interactions = power_origins.get("power_interactions", [])
    if interactions:
        lines.append(f"\n▸ POWER INTERACTIONS (hybrid synergies):")
        for inter in interactions[:_MAX_POWER_INTERACTIONS]:
            if isinstance(inter, dict):
                src_a = inter.get("source_a", "?")
                src_b = inter.get("source_b", "?")
                name = inter.get("interaction", "?")
                notes = inter.get("notes", "")
                lines.append(f"  • {src_a} × {src_b} → {name}")
                if notes:
                    lines.append(f"    {notes}")
            else:
                lines.append(f"  • {inter}")

    # --- Cumulative strain status ---
    if usage_tracking:
        strain_data = _compute_cumulative_strain(usage_tracking, chapter_count)

        if strain_data["high_critical"] or strain_data["medium"]:
            lines.append(f"\n▸ STRAIN STATUS (cumulative across {chapter_count} chapters):")

            if strain_data["high_critical"]:
                lines.append("  Powers at HIGH/CRITICAL strain — MUST show physical/mental effects:")
                for key, level, last_ch in strain_data["high_critical"]:
                    lines.append(
                        f"    • {key}: {level.upper()} (Ch.{last_ch}) "
                        f"— protagonist should be visibly taxed"
                    )

            if strain_data["medium"]:
                lines.append("  Powers at MEDIUM strain (show subtle fatigue):")
                for key, level, last_ch in strain_data["medium"][:_MAX_MEDIUM_STRAIN_ENTRIES]:
                    lines.append(f"    • {key}: MEDIUM (Ch.{last_ch})")

            lines.append(
                f"  Overall: {strain_data['summary']}. "
                "Protagonist should NOT fight at full capacity."
            )

    # --- Global weaknesses ---
    if global_weaknesses:
        lines.append("\n  Global weaknesses (apply to ALL power usage):")
        for w in global_weaknesses:
            lines.append(f"    • {w}")

    # --- Power scaling rules from jobber_prevention_rules ---
    cci = bible.get("canon_character_integrity", {})
    jobber_rules = cci.get("jobber_prevention_rules", [])
    if jobber_rules:
        lines.append(f"\n▸ POWER SCALING RULES (from jobber_prevention_rules):")
        for rule in jobber_rules:
            lines.append(f"  • {rule}")

    # --- Common power violations ---
    lines.append("\n▸ COMMON POWER VIOLATIONS — DO NOT COMMIT THESE:")
    lines.append("  ✘ Using techniques not listed in canon_techniques for a source")
    lines.append("  ✘ Ignoring documented costs/limitations of a technique")
    lines.append("  ✘ Letting a Course 1 student match a Strategic-Class asset in raw power")
    lines.append("  ✘ Downplaying planetary-scale power to create artificial tension")
    lines.append("  ✘ Writing generic \"energy blast\" instead of named signature moves")
    lines.append("  ✘ Ignoring strain — a power at HIGH strain cannot be used freely")

    return "\n".join(lines)


def _find_source_strain(
    source_name: str,
    short_name: str,
    usage_tracking: dict,
) -> tuple[str, int] | None:
    """Find the highest strain entry in usage_tracking that matches a power source.

    Tries exact match on source_name, then partial/prefix match on short_name.
    Returns (strain_level, last_chapter) for the highest severity match, or None.
    """
    # Exact match first
    entry = usage_tracking.get(source_name)
    if isinstance(entry, dict):
        return (entry.get("strain_level", "none"), entry.get("last_chapter", 0))

    # Partial/prefix match — aggregate all matching entries, return highest
    best_severity = 0
    best_entry: tuple[str, int] | None = None
    source_lower = source_name.lower()
    short_lower = short_name.lower()

    for key, data in usage_tracking.items():
        if not isinstance(data, dict):
            continue
        key_lower = key.lower()
        if (
            source_lower in key_lower
            or key_lower in source_lower
            or short_lower in key_lower
            or key_lower.startswith(short_lower)
        ):
            level = data.get("strain_level", "none").strip().lower()
            severity = _STRAIN_SEVERITY.get(level, 0)
            if severity > best_severity:
                best_severity = severity
                best_entry = (level, data.get("last_chapter", 0))

    return best_entry


def _build_protected_characters_block(bible: dict) -> str:
    """Build the PROTECTED CHARACTERS / anti-Worfing enforcement block.

    Per-character competence minimums and anti-Worf notes.
    NOTE: jobber_prevention_rules are now surfaced in the POWER SYSTEM ENFORCEMENT
    block to avoid duplication and keep scaling rules co-located with power data.
    """
    cci = bible.get("canon_character_integrity", {})
    protected = cci.get("protected_characters", [])

    if not protected:
        return ""

    lines = ["\n\n══ PROTECTED CHARACTERS — ANTI-WORFING ══"]

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

    lines.append(
        "NEVER make these characters lose to opponents below their level. "
        "If the OC wins, it MUST be justified by specific counter, ambush, "
        "or significant cost."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4g. Character behavior & voice enforcement
# ---------------------------------------------------------------------------

_MAX_VOICE_PROFILES = 10
_MAX_RELATIONSHIP_ENTRIES = 10


def _build_character_behavior_block(bible: dict) -> str:
    """Build the CHARACTER BEHAVIOR & VOICES enforcement block.

    Injects character_voices profiles (personality, speech patterns, verbal tics,
    emotional tells, vocabulary level, topics to avoid/discuss, example dialogue)
    and the protagonist's key relationships directly into the model context.

    This ensures the Storyteller doesn't need to voluntarily call read_bible()
    to access character behavior data — it's always present.
    """
    voices = bible.get("character_voices", {})
    char_sheet = bible.get("character_sheet", {})
    relationships = char_sheet.get("relationships", {})

    if not voices and not relationships:
        return ""

    lines = [
        "\n\n══ CHARACTER BEHAVIOR & VOICES — ENFORCEMENT ══",
        "[!!!] Characters MUST behave according to these profiles. "
        "Out-of-character behavior invalidates the chapter.",
    ]

    # --- Section 1: Voice profiles ---
    if voices:
        lines.append(f"\n▸ CHARACTER VOICE PROFILES ({min(len(voices), _MAX_VOICE_PROFILES)} characters):")

        # Protagonist first, then sort the rest alphabetically
        # Name may include kanji like "Kageaki Ren (蓮 影明)" — match by prefix
        protagonist_full = char_sheet.get("name", "")
        protagonist_key = ""
        for vk in voices:
            if vk in protagonist_full or protagonist_full in vk or protagonist_full.split("(")[0].strip() == vk:
                protagonist_key = vk
                break

        sorted_names = sorted(voices.keys())
        if protagonist_key and protagonist_key in sorted_names:
            sorted_names.remove(protagonist_key)
            sorted_names.insert(0, protagonist_key)

        for char_name in sorted_names[:_MAX_VOICE_PROFILES]:
            profile = voices[char_name]
            if not isinstance(profile, dict):
                continue

            is_protagonist = char_name == protagonist_key
            label = f"  [{char_name}]" + (" ★ PROTAGONIST" if is_protagonist else "")
            lines.append(f"\n{label}")

            # Personality
            personality = profile.get("personality", "")
            if personality:
                # Strip extra quotes from LLM-generated strings
                clean = str(personality).strip('"')
                lines.append(f"    Personality: {clean}")

            # Speech patterns
            speech = profile.get("speech_patterns", "")
            if speech:
                if isinstance(speech, list):
                    speech = ", ".join(str(s) for s in speech)
                lines.append(f"    Speech: {speech}")

            # Vocabulary level
            vocab = profile.get("vocabulary_level", "")
            if vocab:
                lines.append(f"    Vocabulary: {vocab}")

            # Verbal tics
            tics = profile.get("verbal_tics", "")
            if tics:
                lines.append(f"    Verbal tics: {tics}")

            # Emotional tells
            tells = profile.get("emotional_tells", "")
            if tells:
                lines.append(f"    Emotional tells: {tells}")

            # Example dialogue
            example = profile.get("example_dialogue", "")
            if example:
                lines.append(f'    Example: "{example}"')

            # Topics to avoid (critical for staying in character)
            avoid = profile.get("topics_to_avoid", profile.get("topics_they_avoid", []))
            if avoid:
                if isinstance(avoid, list):
                    avoid_str = "; ".join(str(a) for a in avoid)
                else:
                    avoid_str = str(avoid)
                lines.append(f"    NEVER discusses: {avoid_str}")

            # Topics to discuss
            discuss = profile.get("topics_to_discuss", profile.get("topics_they_discuss", []))
            if discuss:
                if isinstance(discuss, list):
                    discuss_str = "; ".join(str(d) for d in discuss)
                else:
                    discuss_str = str(discuss)
                lines.append(f"    Naturally discusses: {discuss_str}")

    # --- Section 2: Active relationships (protagonist's POV) ---
    if relationships:
        lines.append(f"\n▸ ACTIVE RELATIONSHIPS ({min(len(relationships), _MAX_RELATIONSHIP_ENTRIES)} entries):")
        lines.append("  Write interactions consistent with these dynamics:")

        # Sort by trust level (high first) then alphabetically
        trust_order = {"high": 0, "medium": 1, "low": 2}
        sorted_rels = sorted(
            relationships.items(),
            key=lambda kv: (
                trust_order.get(kv[1].get("trust", "low") if isinstance(kv[1], dict) else "low", 3),
                kv[0],
            ),
        )

        for char_name, rel in sorted_rels[:_MAX_RELATIONSHIP_ENTRIES]:
            if not isinstance(rel, dict):
                continue
            rel_type = rel.get("type", "unknown")
            trust = rel.get("trust", "?")
            dynamics = rel.get("dynamics", "")
            relation = rel.get("relation", "")

            tag = f"{rel_type.upper()}"
            lines.append(f"  • {char_name} [{tag}, trust: {trust}] — {relation}")
            if dynamics:
                lines.append(f"    Dynamic: {dynamics}")

    # --- Section 3: Behavioral rules ---
    lines.append("\n▸ BEHAVIORAL RULES:")
    lines.append("  ✘ Characters must NOT suddenly shift personality without narrative justification")
    lines.append("  ✘ Dialogue must match documented speech_patterns and vocabulary_level")
    lines.append("  ✘ Characters must NOT discuss their topics_to_avoid unless under extreme duress")
    lines.append("  ✘ Emotional tells must appear when the documented triggers are present")
    lines.append("  ✘ Relationship dynamics must match the documented trust level and type")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4g. Auto-enrichment of event playbooks from source text
# ---------------------------------------------------------------------------

_MAX_ENRICHMENTS_PER_TURN = 1
_MIN_BEATS_FOR_RICH_PLAYBOOK = 5


def _match_volumes(
    source_ref: str,
    event_name: str,
    available_volumes: list[str],
) -> list[str]:
    """Match an event to relevant source text volumes using the DB catalog.

    Scores each available volume by:
    1. Volume number match against source reference (e.g., "LN Vol 2" → Volume 02)
    2. Arc keyword overlap between event name and volume name

    Returns matched volume names sorted by relevance score (top 3).
    """
    if not available_volumes:
        return []

    # Parse target volume numbers from source reference
    target_nums: set[int] = set()
    if source_ref:
        range_match = re.search(r'[Vv]ol(?:ume)?\.?\s*(\d+)\s*[-–]\s*(\d+)', source_ref)
        if range_match:
            target_nums = set(range(int(range_match.group(1)), int(range_match.group(2)) + 1))
        else:
            single_match = re.search(r'[Vv]ol(?:ume)?\.?\s*(\d+)', source_ref)
            if single_match:
                target_nums = {int(single_match.group(1))}

    # Arc keywords from event name (drop stop words)
    stop_words = {"the", "of", "at", "in", "a", "an", "and", "is", "was"}
    event_words = set(event_name.lower().split()) - stop_words

    scored: list[tuple[str, float]] = []
    for vol_name in available_volumes:
        score = 0.0

        # Number match
        vol_num_match = re.match(r'Volume (\d+)', vol_name)
        if vol_num_match and int(vol_num_match.group(1)) in target_nums:
            score += 10.0

        # Arc keyword overlap
        vol_words = set(vol_name.lower().split()) - stop_words - {
            "volume", "i", "ii", "iii", "(i)", "(ii)", "(iii)",
        }
        overlap = event_words & vol_words
        if overlap:
            score += len(overlap) * 3.0

        if score > 0:
            scored.append((vol_name, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in scored[:3]]


def _extract_relevant_sections(
    full_text: str,
    search_terms: list[str],
    context_chars: int = 3000,
    max_total: int = 15_000,
) -> str:
    """Extract sections from full volume text around keyword matches.

    Searches for each term, takes ``context_chars`` of surrounding text,
    merges overlapping ranges, and caps total output at ``max_total``.
    """
    text_lower = full_text.lower()
    ranges: list[tuple[int, int]] = []

    for term in search_terms:
        if not term:
            continue
        term_lower = term.lower()
        start_pos = 0
        matches = 0
        while matches < 3:
            idx = text_lower.find(term_lower, start_pos)
            if idx == -1:
                break
            r_start = max(0, idx - context_chars)
            r_end = min(len(full_text), idx + len(term) + context_chars)
            ranges.append((r_start, r_end))
            start_pos = idx + len(term)
            matches += 1

    if not ranges:
        return ""

    # Merge overlapping ranges
    ranges.sort()
    merged = [ranges[0]]
    for start, end in ranges[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    sections: list[str] = []
    total = 0
    for start, end in merged:
        if total >= max_total:
            break
        section = full_text[start:end]
        if start > 0:
            section = "..." + section
        if end < len(full_text):
            section = section + "..."
        sections.append(section)
        total += len(section)

    return "\n\n---\n\n".join(sections)


async def _fetch_source_context(
    universe: str,
    event: dict,
    available_volumes: list[tuple[str, int]],
    max_chars: int = 30_000,
) -> str:
    """Fetch relevant source text context for an event from the DB.

    Two-pronged, data-driven approach:
    1. Keyword search across **all** volumes (discovers content regardless of
       which volume it lives in)
    2. Direct volume fetch + section extraction for volumes matched by the
       DB catalog (number + arc-name scoring)

    Returns combined context string, or empty string if nothing found.
    """
    from src.tools.source_text import search_source_text, get_source_text

    event_name = event.get("event", "")
    characters = event.get("characters_involved", [])
    source_ref = event.get("source", "")

    sections: list[str] = []

    # 1. Search across all volumes by event name
    result = await search_source_text(universe, event_name)
    if not result.startswith("No matches") and not result.startswith("No source text"):
        sections.append(f"=== Search: '{event_name}' ===\n{result}")

    # 2. Search by key characters (surname for broader recall)
    for char in characters[:2]:
        surname = char.split()[-1] if " " in char else char
        result = await search_source_text(universe, surname)
        if not result.startswith("No matches"):
            sections.append(f"=== Search: '{surname}' ===\n{result}")

    # 3. Fetch from matched volumes using the DB catalog
    vol_names = [v[0] for v in available_volumes]
    matched = _match_volumes(source_ref, event_name, vol_names)
    search_terms = [event_name] + characters[:3]
    for vol_name in matched[:2]:
        vol_text = await get_source_text(universe, vol_name)
        # Skip error messages
        if vol_text.startswith("No source text") or "not found" in vol_text[:80]:
            continue
        relevant = _extract_relevant_sections(vol_text, search_terms)
        if relevant:
            sections.append(f"=== {vol_name} (relevant sections) ===\n{relevant}")

    combined = "\n\n".join(sections)
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n...[truncated]"
    return combined


async def _llm_extract_playbook(
    event_name: str,
    source_context: str,
    event: dict,
) -> dict | None:
    """Extract a rich event_playbook from source text via a direct Gemini call.

    Returns a dict with narrative_beats, character_behaviors, emotional_arc,
    key_decisions — or ``None`` if extraction fails.
    """
    from src.utils.resilient_client import ResilientClient
    from src.utils.auth import get_api_key

    characters = event.get("characters_involved", [])
    significance = event.get("significance", event.get("description", ""))
    consequences = event.get("consequences", [])

    prompt = (
        f"You are extracting a detailed event playbook from source novel text.\n\n"
        f"EVENT: {event_name}\n"
        f"CHARACTERS INVOLVED: {', '.join(characters) if characters else 'Unknown'}\n"
        f"SIGNIFICANCE: {significance}\n"
        f"CONSEQUENCES: {', '.join(str(c) for c in consequences) if isinstance(consequences, list) else str(consequences)}\n\n"
        f"SOURCE TEXT EXCERPTS:\n{source_context}\n\n"
        "Extract a detailed event playbook as a JSON object with:\n"
        '- "narrative_beats": Array of 5-10 STRINGS (plain text, not objects). Each string is a '
        "specific scene-level beat from the source text. Include exact details, dialogue references, "
        "and turning points. Order chronologically.\n"
        '- "character_behaviors": Object mapping character names to their specific '
        "behavior/role during this event.\n"
        '- "emotional_arc": String describing the emotional progression '
        '(e.g., "Tension → Shock → Desperate defense → Pyrrhic victory").\n'
        '- "key_decisions": Array of critical decision points that shaped the outcome.\n\n'
        "Focus on SPECIFIC details from the source text, not generic summaries.\n"
        "Output ONLY valid JSON. No markdown, no explanation."
    )

    client = ResilientClient(api_key=get_api_key())
    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = response.text.strip()

        # Strip markdown code fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
        if text.startswith("json"):
            text = text[4:].strip()

        playbook = json.loads(text)
        if not isinstance(playbook, dict) or not playbook.get("narrative_beats"):
            return None

        # Normalize beats to plain strings (LLM sometimes returns dicts)
        playbook["narrative_beats"] = [
            b.get("description", str(b)) if isinstance(b, dict) else str(b)
            for b in playbook["narrative_beats"]
        ]
        return playbook

    except Exception as e:
        logger.warning("Playbook extraction failed for '%s': %s", event_name, e)
        return None


async def _persist_bible_content(story_id: str, content: dict) -> None:
    """Write updated Bible content back to the database."""
    from sqlalchemy.orm.attributes import flag_modified

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WorldBible).where(WorldBible.story_id == story_id)
        )
        bible = result.scalar_one_or_none()
        if bible:
            bible.content = content
            flag_modified(bible, "content")
            await db.commit()


async def _maybe_enrich_event_playbooks(
    story_id: str, bible_content: dict
) -> bool:
    """Auto-enrich shallow event_playbooks from source text as major events approach.

    Called from ``before_storyteller_model_callback``.  Finds upcoming
    high-pressure events with missing / shallow playbooks, fetches relevant
    source text from the DB, and extracts rich narrative beats via a direct
    LLM call.

    Rate-limited to ``_MAX_ENRICHMENTS_PER_TURN`` per turn.  Each event is
    flagged with ``_source_enriched`` so it is never re-processed.
    """
    meta = bible_content.get("meta", {})
    if not meta.get("use_source_text", True):
        return False

    canon_tl = bible_content.get("canon_timeline", {})
    all_events = canon_tl.get("events", [])
    if not all_events:
        return False

    current_date_str = meta.get("current_story_date", "")
    current_dt_parsed = _parse_story_date(current_date_str)
    protagonist_name = bible_content.get("character_sheet", {}).get("name", "")
    story_start_dt = _parse_story_date(meta.get("story_start_date", ""))

    # Identify events that need enrichment
    candidates = []
    for evt in all_events:
        if _is_past_event(evt.get("status", "")):
            continue
        if _is_pre_story_event(evt, story_start_dt):
            continue

        playbook = evt.get("event_playbook")
        if isinstance(playbook, dict) and playbook.get("_source_enriched"):
            continue  # Already enriched or attempted

        beats = playbook.get("narrative_beats", []) if isinstance(playbook, dict) else []
        if len(beats) >= _MIN_BEATS_FOR_RICH_PLAYBOOK:
            continue  # Rich enough already

        pressure = _compute_pressure_score(
            evt, current_dt_parsed, protagonist_name, all_events,
        )
        if pressure["pressure_score"] < 5.0 and not pressure["is_overdue"]:
            continue

        candidates.append((evt, pressure))

    if not candidates:
        return False

    candidates.sort(key=lambda x: x[1]["pressure_score"], reverse=True)

    # Query DB for available source text volumes (data-driven catalog)
    event_universe = candidates[0][0].get("universe", "")
    universe_key = event_universe.lower().strip() if event_universe else ""
    if not universe_key:
        return False

    try:
        from src.models import SourceText as _ST

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(_ST.volume, _ST.word_count)
                .where(_ST.universe == universe_key)
                .order_by(_ST.volume)
            )
            available_volumes = result.all()
    except Exception:
        return False

    if not available_volumes:
        return False

    enriched_count = 0
    for target_evt, target_pressure in candidates[:_MAX_ENRICHMENTS_PER_TURN]:
        event_name = target_evt.get("event", "Unknown")

        logger.info(
            "Auto-enriching playbook for '%s' (pressure: %.1f)",
            event_name, target_pressure["pressure_score"],
        )

        # Fetch relevant source text (search + volume fetch)
        context = await _fetch_source_context(
            universe_key, target_evt, available_volumes,
        )
        if not context:
            target_evt.setdefault("event_playbook", {})["_source_enriched"] = "no_source_found"
            continue

        # Extract playbook via LLM
        enriched = await _llm_extract_playbook(event_name, context, target_evt)
        if not enriched:
            target_evt.setdefault("event_playbook", {})["_source_enriched"] = "extraction_failed"
            continue

        # Merge: preserve existing fields, override with richer data
        existing = target_evt.get("event_playbook") or {}
        if isinstance(existing, dict):
            enriched = {**existing, **enriched}
        enriched["_source_enriched"] = True
        target_evt["event_playbook"] = enriched
        enriched_count += 1

        logger.info(
            "Enriched '%s': %d beats, %d character behaviors",
            event_name,
            len(enriched.get("narrative_beats", [])),
            len(enriched.get("character_behaviors", {})),
        )

    # Always persist — even failure markers (_source_enriched = "no_source_found" /
    # "extraction_failed") must be saved so we don't re-attempt every turn.
    await _persist_bible_content(story_id, bible_content)

    return enriched_count > 0


# ---------------------------------------------------------------------------
# 4h. Event playbook enforcement (narrative beats for upcoming major events)
# ---------------------------------------------------------------------------

def _build_event_playbook_block(bible: dict, chapter_count: int) -> str:
    """Build the EVENT PLAYBOOK enforcement block for upcoming major events.

    Extracts event_playbook data from canon_timeline events that are:
    - Not yet past (status != occurred/modified/prevented)
    - MANDATORY or HIGH priority (pressure >= 5.0)
    - Have an event_playbook field populated

    Injects narrative beats, character behaviors, emotional arc, and key
    decisions so the Storyteller writes canonically-accurate event scenes.
    Capped at _MAX_PLAYBOOK_EVENTS (3) to stay within token budget (~1500 tokens).
    """
    canon_tl = bible.get("canon_timeline", {})
    all_events = canon_tl.get("events", [])
    if not all_events:
        return ""

    meta = bible.get("meta", {})
    current_date_str = meta.get("current_story_date", "")
    current_dt_parsed = _parse_story_date(current_date_str)
    protagonist_name = bible.get("character_sheet", {}).get("name", "")
    story_start_dt = _parse_story_date(meta.get("story_start_date", ""))

    # Filter to upcoming events with playbooks
    candidates: list[tuple[dict, dict]] = []
    for evt in all_events:
        status = evt.get("status", "")
        if _is_past_event(status):
            continue
        if _is_pre_story_event(evt, story_start_dt):
            continue
        playbook = evt.get("event_playbook")
        if not playbook or not isinstance(playbook, dict):
            continue

        pressure = _compute_pressure_score(
            evt, current_dt_parsed, protagonist_name, all_events,
        )
        # Only include MANDATORY (>= 7.0) or HIGH (>= 5.0) pressure events
        if pressure["pressure_score"] >= 5.0 or pressure["is_overdue"]:
            candidates.append((evt, pressure))

    if not candidates:
        return ""

    # Sort by pressure descending, cap at max
    candidates.sort(key=lambda x: x[1]["pressure_score"], reverse=True)
    candidates = candidates[:_MAX_PLAYBOOK_EVENTS]

    lines = [
        "\n\n══ EVENT PLAYBOOK — NARRATIVE REFERENCE ══",
        "These are detailed breakdowns of how upcoming canon events originally "
        "played out. Use as your reference for writing canonically-accurate scenes.",
    ]

    for evt, pressure in candidates:
        event_name = evt.get("event", "Unknown Event")
        date_str = evt.get("date", "TBD")
        p_score = pressure["pressure_score"]
        overdue_tag = " ⚠ OVERDUE" if pressure["is_overdue"] else ""
        playbook = evt["event_playbook"]

        lines.append(
            f"\n▸ {event_name} [{date_str}] (pressure: {p_score}{overdue_tag})"
        )

        # Narrative beats (normalize dicts to strings for clean injection)
        beats = playbook.get("narrative_beats", [])
        if beats:
            lines.append("  Narrative beats:")
            for i, beat in enumerate(beats, 1):
                if isinstance(beat, dict):
                    beat = beat.get("description", str(beat))
                lines.append(f"    {i}. {beat}")

        # Character behaviors (event-specific)
        behaviors = playbook.get("character_behaviors", {})
        if behaviors and isinstance(behaviors, dict):
            lines.append("  Character behaviors (event-specific):")
            for char, behavior in behaviors.items():
                lines.append(f"    • {char}: {behavior}")

        # Emotional arc
        arc = playbook.get("emotional_arc", "")
        if arc:
            lines.append(f"  Emotional arc: {arc}")

        # Key decisions
        decisions = playbook.get("key_decisions", [])
        if decisions:
            lines.append("  Key decisions:")
            for decision in decisions:
                lines.append(f"    → {decision}")

        # Source reference
        source = playbook.get("source", "")
        if source:
            lines.append(f"  Source: {source}")

    lines.append(
        "\nUse this as your reference. You may diverge from canon beats, but "
        "divergences must be justified by prior story events or player choices."
    )

    return "\n".join(lines)
