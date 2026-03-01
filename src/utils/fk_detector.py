"""Forbidden Knowledge (FK) post-generation detector.

Scans chapter text against ``knowledge_boundaries`` from the World Bible
using rule-based detection, then generates contextual questions via a
lightweight LLM call so they feel organic to the narrative.
"""

from __future__ import annotations

import json
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

_MIN_KEYWORD_LEN = 4
_MAX_FK_QUESTIONS = 2

# Timeout for the LLM question-generation call (seconds)
_LLM_TIMEOUT_SECONDS = 15


async def detect_fk_situations(
    story_id: str,
    chapter_text: str,
    chapter_num: int,
) -> list[dict]:
    """Scan chapter text against World Bible knowledge_boundaries.

    Phase 1 (rule-based): detect which FK situations are relevant.
    Phase 2 (LLM): generate contextual questions for the top detections.

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

    known_names = _build_character_names(bible)

    # --- Phase 1: Rule-based detection ---
    detections: list[dict] = []

    detections.extend(
        _detect_secret_proximity(kb, protagonist_name, chapter_lower, known_names)
    )
    detections.extend(
        _detect_suspect_crystallization(kb, protagonist_name, chapter_lower)
    )
    if not detections and chapter_num % 5 == 0:
        detections.extend(
            _detect_periodic_audit(kb, protagonist_name, chapter_lower, known_names)
        )

    if not detections:
        return []

    detections.sort(key=lambda d: d["_relevance"], reverse=True)
    top_detections = detections[:_MAX_FK_QUESTIONS]

    # --- Phase 2: LLM-generated contextual questions ---
    # Extract a short scene excerpt around the relevant characters
    questions = await _generate_fk_questions(
        top_detections, protagonist_name, chapter_text, chapter_num,
    )

    for det, q in zip(top_detections, questions):
        _logger.info(
            "fk_injection | type=%s relevance=%.2f | ch=%d | %s",
            det["_detection_type"], det["_relevance"], chapter_num,
            q["question"][:80],
        )

    return questions


# ---------------------------------------------------------------------------
# LLM question generation
# ---------------------------------------------------------------------------

async def _generate_fk_questions(
    detections: list[dict],
    protagonist_name: str,
    chapter_text: str,
    chapter_num: int,
) -> list[dict]:
    """Use a lightweight Gemini call to generate contextual FK questions.

    Falls back to rule-based templates if the LLM call fails.
    """
    import asyncio
    from src.utils.resilient_client import ResilientClient
    from src.utils.auth import get_api_key

    # Build compact detection summaries for the prompt
    detection_briefs = []
    for det in detections:
        brief = {
            "type": det["_detection_type"],
            "relevance": det["_relevance"],
        }
        if det["_detection_type"] == "secret_proximity":
            brief["character"] = det["_holder"]
            brief["secret"] = det["_hint"]
        elif det["_detection_type"] == "suspect_crystallization":
            brief["suspicion"] = det["_suspect_item"]
            brief["matching_keywords"] = det.get("_matching_keywords", [])
        elif det["_detection_type"] == "periodic_audit":
            brief["forbidden_item"] = det["_forbidden_item"]
        detection_briefs.append(brief)

    # Extract a ~1500 char excerpt from the end of the chapter (most recent scene)
    scene_excerpt = chapter_text[-1500:] if len(chapter_text) > 1500 else chapter_text
    # Find a clean sentence boundary to start
    first_period = scene_excerpt.find(". ")
    if first_period > 0 and first_period < 200:
        scene_excerpt = scene_excerpt[first_period + 2:]

    prompt = f"""You are generating narrative questions for an interactive fiction game.

The protagonist is {protagonist_name}. This is Chapter {chapter_num}.

SCENE EXCERPT (end of this chapter):
{scene_excerpt}

FK DETECTIONS (situations where the protagonist is near forbidden knowledge):
{json.dumps(detection_briefs, indent=2)}

For each detection, generate ONE question that:
1. References the SPECIFIC scene from this chapter (use character names, locations, actions that just happened)
2. Feels like a natural narrative choice, NOT a game menu
3. Has 3 options that represent a SPECTRUM from oblivious → suspicious → breakthrough
4. Options should be SPECIFIC to the scene (e.g., "Ren notices the inconsistency in Tatsuya's CAD readings" not "Yes — a clue slips through")
5. The question context should hint at what's at stake without revealing the secret

Output ONLY a JSON array of objects, one per detection:
[
  {{
    "question": "Scene-specific question about what the protagonist notices",
    "context": "Brief dramatic stakes hint (1 sentence)",
    "options": ["Oblivious option", "Suspicious option", "Breakthrough option"]
  }}
]

Output ONLY valid JSON. No markdown fences, no explanation."""

    try:
        client = ResilientClient(api_key=get_api_key())
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            ),
            timeout=_LLM_TIMEOUT_SECONDS,
        )
        text = response.text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
        if text.startswith("json"):
            text = text[4:].strip()

        raw_questions = json.loads(text)
        if not isinstance(raw_questions, list):
            raise ValueError(f"Expected list, got {type(raw_questions)}")

        # Validate and build frontend-compatible question dicts
        questions = []
        for i, rq in enumerate(raw_questions[:_MAX_FK_QUESTIONS]):
            if not isinstance(rq, dict) or "question" not in rq:
                continue
            options = rq.get("options", [])
            if not isinstance(options, list) or len(options) < 2:
                continue
            questions.append({
                "question": rq["question"],
                "context": rq.get("context", "Your answer shapes how this secret unfolds"),
                "type": "choice",
                "options": options[:4],  # cap at 4 options
                "category": "forbidden_knowledge",
            })

        if questions:
            return questions

        _logger.warning("LLM returned no valid FK questions, falling back to templates")

    except Exception:
        _logger.warning("FK question LLM call failed, falling back to templates", exc_info=True)

    # --- Fallback: rule-based templates (better than nothing) ---
    return _fallback_questions(detections, protagonist_name)


def _fallback_questions(
    detections: list[dict],
    protagonist_name: str,
) -> list[dict]:
    """Generate template-based FK questions as a fallback."""
    questions = []
    for det in detections:
        if det["_detection_type"] == "secret_proximity":
            holder = det["_holder"]
            hint = det["_hint"]
            q = {
                "question": f"During this scene with {holder}, does {protagonist_name} pick up on anything unusual?",
                "context": f"{holder} carries a secret that could change everything if discovered",
                "type": "choice",
                "options": [
                    f"{protagonist_name} is too focused on the situation to notice",
                    f"Something about {holder}'s behavior feels off",
                    f"{protagonist_name} catches a detail that doesn't add up",
                ],
                "category": "forbidden_knowledge",
            }
        elif det["_detection_type"] == "suspect_crystallization":
            suspicion = det["_suspect_item"]
            short = suspicion if len(suspicion) <= 60 else suspicion[:57] + "..."
            q = {
                "question": f"Does {protagonist_name}'s suspicion about \"{short}\" crystallize this chapter?",
                "context": "The evidence is mounting — but connecting the dots means crossing a line",
                "type": "choice",
                "options": [
                    "The pieces don't quite connect yet",
                    f"{protagonist_name} files it away — something to revisit later",
                    "The pattern snaps into focus",
                ],
                "category": "forbidden_knowledge",
            }
        else:  # periodic_audit
            forbidden = det.get("_forbidden_item", "something hidden")
            short = forbidden if len(forbidden) <= 60 else forbidden[:57] + "..."
            q = {
                "question": f"Awareness check: does {protagonist_name} sense anything related to \"{short}\"?",
                "context": "Some truths are better left undiscovered — for now",
                "type": "choice",
                "options": [
                    "Completely oblivious",
                    "A vague unease, nothing concrete",
                    "A stray thought that lands uncomfortably close to the truth",
                ],
                "category": "forbidden_knowledge",
            }
        questions.append(q)
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
    character_secrets: dict = kb.get("character_secrets", {})
    if not character_secrets:
        return []

    protagonist_present = _name_in_text(protagonist_name, chapter_lower)
    if not protagonist_present:
        return []

    detections = []
    for holder, raw_secrets in character_secrets.items():
        if not raw_secrets or holder.lower() == protagonist_name.lower():
            continue
        if not _name_in_text(holder, chapter_lower):
            continue

        # Normalize secrets to a list of strings — Bible may store them as:
        #   list[str]:  ["secret1", "secret2"]
        #   dict:       {"secret": "...", "known_by": [...], ...}
        #   str:        "single secret"
        if isinstance(raw_secrets, dict):
            secret_texts = [raw_secrets["secret"]] if "secret" in raw_secrets else []
        elif isinstance(raw_secrets, list):
            secret_texts = [s for s in raw_secrets if isinstance(s, str)]
        elif isinstance(raw_secrets, str):
            secret_texts = [raw_secrets]
        else:
            continue

        if not secret_texts:
            continue

        relevance = 0.7
        for secret in secret_texts:
            keywords = _extract_keywords(secret)
            matching = sum(1 for kw in keywords if kw in chapter_lower)
            if matching >= 1:
                relevance = min(1.0, relevance + 0.1 * matching)

        detections.append({
            "_relevance": relevance,
            "_detection_type": "secret_proximity",
            "_holder": holder,
            "_hint": secret_texts[0],
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
            ratio = len(matching) / len(keywords)
            relevance = 0.5 + 0.5 * ratio

            detections.append({
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

    chapter_present_names = {name for name in known_names if _name_in_text(name, chapter_lower)}
    best_item = None
    best_score = -1
    for item in forbidden:
        item_lower = item.lower()
        score = sum(1 for name in chapter_present_names if _name_in_text(name, item_lower))
        keywords = _extract_keywords(item)
        chapter_matches = sum(1 for kw in keywords if kw in chapter_lower)
        score += chapter_matches * 0.3

        if score > best_score:
            best_score = score
            best_item = item

    if best_item:
        return [{
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

    cs_name = bible.get("character_sheet", {}).get("name")
    if cs_name:
        names.add(cs_name)

    for name in bible.get("character_sheet", {}).get("relationships", {}):
        names.add(name)

    for name in bible.get("world_state", {}).get("characters", {}):
        names.add(name)

    for name in bible.get("character_voices", {}):
        names.add(name)

    # entity_aliases — values may be a string (canonical name) or list of aliases
    for key, value in bible.get("world_state", {}).get("entity_aliases", {}).items():
        names.add(key)
        if isinstance(value, str):
            names.add(value)
        elif isinstance(value, list):
            for v in value:
                if isinstance(v, str):
                    names.add(v)

    for name in bible.get("knowledge_boundaries", {}).get("character_knowledge_limits", {}):
        names.add(name)

    for name in bible.get("knowledge_boundaries", {}).get("character_secrets", {}):
        names.add(name)

    return names


def _name_in_text(name: str, text_lower: str) -> bool:
    """Check if a character name appears in text using word-boundary matching."""
    name_lower = name.lower()
    pattern = re.escape(name_lower)
    if re.search(rf"\b{pattern}\b", text_lower):
        return True
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
