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

    # --- Fetch last chapter's question_answers for FK/timeline continuity ---
    last_qa: dict = {}
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

        # 6. Previous chapter's player FK/timeline answers (carry forward)
        if last_qa:
            instructions.append(
                _build_previous_qa_block(last_qa)
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

# Timeline enforcement caps
_MAX_MANDATORY_EVENTS = 5
_MAX_HIGH_EVENTS = 5
_MAX_MEDIUM_EVENTS = 5

# Statuses that mean an event has already happened or been removed from play
_PAST_STATUSES = frozenset({
    "occurred", "modified", "prevented",
    "completed", "completed —",  # prefix match handled separately
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


def _build_previous_qa_block(last_qa: dict) -> str:
    """Build a block carrying forward the player's FK/timeline answers from last chapter."""
    if not last_qa:
        return ""

    lines = [
        "\n\n══ PLAYER'S PREVIOUS CHAPTER DECISIONS ══",
        "The player made these FK/timeline decisions last chapter. RESPECT them:",
    ]
    for idx, answer in sorted(last_qa.items(), key=lambda x: str(x[0])):
        lines.append(f"  - Q{idx}: {answer}")

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
