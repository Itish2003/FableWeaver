"""Forbidden Knowledge (FK) post-generation detector.

Scans chapter text against ``knowledge_boundaries`` from the World Bible
and deterministically injects FK questions before they reach the frontend.
No LLM call needed — pure rule-based detection.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from src.database import AsyncSessionLocal
from src.models import WorldBible
from src.utils.logging_config import get_logger

_logger = get_logger("fable.fk_detector")

# Words to ignore when extracting keywords from suspect strings
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "must", "need", "dare",
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "under", "over", "about", "against", "among", "within",
    "and", "but", "or", "nor", "not", "no", "so", "yet", "both",
    "that", "this", "these", "those", "it", "its", "he", "his", "her",
    "she", "him", "they", "them", "their", "who", "whom", "which",
    "what", "when", "where", "how", "why", "if", "then", "than",
    "more", "most", "very", "also", "just", "even", "only", "some",
    "any", "each", "every", "all", "own", "other", "such", "same",
    "than", "too", "much", "many", "few", "like", "using", "rather",
})

# Minimum keyword length to extract from suspect strings
_MIN_KEYWORD_LEN = 4

# Max FK questions to inject per chapter
_MAX_FK_QUESTIONS = 2

# Standard three-tier answer options for FK questions
_FK_OPTIONS = [
    "No — remains unaware",
    "Suspects — something felt off",
    "Yes — a clue slips through",
]


async def detect_fk_situations(
    story_id: str,
    chapter_text: str,
    chapter_num: int,
) -> list[dict]:
    """Scan chapter text against World Bible knowledge_boundaries.

    Returns 0-2 frontend-compatible question dicts sorted by relevance.
    """
    bible = await _load_bible(story_id)
    if not bible:
        return []

    kb = bible.get("knowledge_boundaries", {})
    if not kb:
        return []

    protagonist_name = bible.get("character_sheet", {}).get("name", "The protagonist")
    chapter_lower = chapter_text.lower()

    # Build character name lookup from multiple Bible sources
    known_names = _build_character_names(bible)

    # Collect all detections
    detections: list[dict] = []

    # --- Type A: Secret Proximity ---
    detections.extend(
        _detect_secret_proximity(kb, protagonist_name, chapter_lower, known_names)
    )

    # --- Type B: Suspect Crystallization ---
    detections.extend(
        _detect_suspect_crystallization(kb, protagonist_name, chapter_lower)
    )

    # --- Type C: Periodic Audit (every 5 chapters, only if A/B found nothing) ---
    if not detections and chapter_num % 5 == 0:
        detections.extend(
            _detect_periodic_audit(kb, protagonist_name, chapter_lower, known_names)
        )

    if not detections:
        return []

    # Sort by relevance descending, take top N
    detections.sort(key=lambda d: d["_relevance"], reverse=True)
    results = detections[:_MAX_FK_QUESTIONS]

    questions = []
    for det in results:
        q = {
            "question": det["question"],
            "context": "Forbidden Knowledge — your answer shapes whether this secret unravels",
            "type": "choice",
            "options": _FK_OPTIONS,
            "category": "forbidden_knowledge",
        }
        questions.append(q)
        _logger.info(
            "fk_injection | type=%s relevance=%.2f | story=%s ch=%d | %s",
            det["_detection_type"], det["_relevance"], story_id, chapter_num,
            det["question"][:80],
        )

    return questions


# ---------------------------------------------------------------------------
# Detection helpers (pure functions, no I/O)
# ---------------------------------------------------------------------------

def _detect_secret_proximity(
    kb: dict,
    protagonist_name: str,
    chapter_lower: str,
    known_names: set[str],
) -> list[dict]:
    """Type A — a character with secrets appears alongside the protagonist."""
    character_secrets: dict[str, list[str]] = kb.get("character_secrets", {})
    if not character_secrets:
        return []

    protagonist_present = _name_in_text(protagonist_name, chapter_lower)
    if not protagonist_present:
        return []

    detections = []
    for holder, secrets in character_secrets.items():
        if not secrets or holder.lower() == protagonist_name.lower():
            continue
        if not _name_in_text(holder, chapter_lower):
            continue

        # Base relevance for proximity
        relevance = 0.7

        # Boost if secret keywords appear in chapter text
        for secret in secrets:
            keywords = _extract_keywords(secret)
            matching = sum(1 for kw in keywords if kw in chapter_lower)
            if matching >= 1:
                relevance = min(1.0, relevance + 0.1 * matching)

        first_secret_hint = secrets[0] if secrets else "something hidden"
        detections.append({
            "question": (
                f"{holder} is nearby and holds secrets. "
                f"Does {protagonist_name} pick up on anything?"
            ),
            "_relevance": relevance,
            "_detection_type": "secret_proximity",
            "_holder": holder,
            "_hint": first_secret_hint,
        })

    return detections


def _detect_suspect_crystallization(
    kb: dict,
    protagonist_name: str,
    chapter_lower: str,
) -> list[dict]:
    """Type B — protagonist's suspicions find textual evidence in the chapter."""
    char_limits = kb.get("character_knowledge_limits", {})
    protag_limits = char_limits.get(protagonist_name, {})
    suspects: list[str] = protag_limits.get("suspects", [])
    if not suspects:
        return []

    detections = []
    for item in suspects:
        keywords = _extract_keywords(item)
        if len(keywords) < 2:
            continue

        matching = [kw for kw in keywords if kw in chapter_lower]
        if len(matching) >= 2:
            # Relevance scales with keyword match ratio
            ratio = len(matching) / len(keywords)
            relevance = 0.5 + 0.5 * ratio  # range: 0.5-1.0

            # Trim the suspect text for the question
            short_concept = item if len(item) <= 80 else item[:77] + "..."
            detections.append({
                "question": (
                    f"{protagonist_name} suspects: \"{short_concept}\" "
                    f"Does the suspicion solidify?"
                ),
                "_relevance": relevance,
                "_detection_type": "suspect_crystallization",
                "_suspect_item": item,
                "_matching_keywords": matching,
            })

    return detections


def _detect_periodic_audit(
    kb: dict,
    protagonist_name: str,
    chapter_lower: str,
    known_names: set[str],
) -> list[dict]:
    """Type C — periodic awareness check using meta_knowledge_forbidden."""
    forbidden: list[str] = kb.get("meta_knowledge_forbidden", [])
    if not forbidden:
        return []

    # Find forbidden items involving a character present in the chapter
    chapter_present_names = {name for name in known_names if _name_in_text(name, chapter_lower)}
    best_item = None
    best_score = -1
    for item in forbidden:
        item_lower = item.lower()
        # Score: how many chapter-present characters are mentioned in this item
        score = sum(1 for name in chapter_present_names if _name_in_text(name, item_lower))
        # Also check if any item keywords appear in the chapter
        keywords = _extract_keywords(item)
        chapter_matches = sum(1 for kw in keywords if kw in chapter_lower)
        score += chapter_matches * 0.3

        if score > best_score:
            best_score = score
            best_item = item

    if best_item:
        short_item = best_item if len(best_item) <= 70 else best_item[:67] + "..."
        return [{
            "question": (
                f"Awareness check: \"{short_item}\" — "
                f"Does {protagonist_name} sense anything related?"
            ),
            "_relevance": 0.4,
            "_detection_type": "periodic_audit",
            "_forbidden_item": best_item,
        }]

    return []


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

async def _load_bible(story_id: str) -> dict | None:
    """Load World Bible content for a story."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(WorldBible).where(WorldBible.story_id == story_id)
            )
            bible = result.scalar_one_or_none()
            return bible.content if bible and bible.content else None
    except Exception:
        _logger.exception("Failed to load Bible for FK detection (story=%s)", story_id)
        return None


def _build_character_names(bible: dict) -> set[str]:
    """Collect character names from multiple Bible sections."""
    names: set[str] = set()

    # character_sheet.name
    cs_name = bible.get("character_sheet", {}).get("name")
    if cs_name:
        names.add(cs_name)

    # character_sheet.relationships keys
    for name in bible.get("character_sheet", {}).get("relationships", {}):
        names.add(name)

    # world_state.characters keys
    for name in bible.get("world_state", {}).get("characters", {}):
        names.add(name)

    # character_voices keys
    for name in bible.get("character_voices", {}):
        names.add(name)

    # entity_aliases (values are canonical names)
    for alias, canonical in bible.get("world_state", {}).get("entity_aliases", {}).items():
        names.add(alias)
        names.add(canonical)

    # knowledge_boundaries.character_knowledge_limits keys
    for name in bible.get("knowledge_boundaries", {}).get("character_knowledge_limits", {}):
        names.add(name)

    # character_secrets keys
    for name in bible.get("knowledge_boundaries", {}).get("character_secrets", {}):
        names.add(name)

    return names


def _name_in_text(name: str, text_lower: str) -> bool:
    """Check if a character name appears in text using word-boundary matching.

    For multi-word names (e.g. "Kageaki Ren"), also checks individual parts
    so that chapters using just first or last name still match.
    """
    name_lower = name.lower()
    # Full name check
    pattern = re.escape(name_lower)
    if re.search(rf"\b{pattern}\b", text_lower):
        return True
    # Individual name parts (skip very short parts to avoid false positives)
    parts = name_lower.split()
    if len(parts) > 1:
        for part in parts:
            if len(part) >= 3 and re.search(rf"\b{re.escape(part)}\b", text_lower):
                return True
    return False


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords (>= 4 chars, not stopwords) from a string."""
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return [w for w in words if len(w) >= _MIN_KEYWORD_LEN and w not in _STOPWORDS]
