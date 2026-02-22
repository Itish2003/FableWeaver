"""
Robust JSON extraction for Storyteller chapter output.

Replaces the fragile regex approach (`re.search(r'\\{[\\s\\S]*"summary"[\\s\\S]*\\}', text)`)
with delimiter-aware parsing and balanced-brace scanning.
"""
import json
import logging
from typing import Optional

from pydantic import ValidationError

from src.schemas import ChapterMetadata

logger = logging.getLogger(__name__)


def extract_chapter_json(text: str) -> Optional[dict]:
    """
    Extract and validate the chapter metadata JSON from Storyteller output.

    Strategy (in order of reliability):
        1. Find the last ``\\`\\`\\`json ... \\`\\`\\``` code-block delimiter.
        2. Fall back to balanced-brace scanning from the end of the text.

    Returns a plain ``dict`` (for backward-compat with existing ``.get()`` callers)
    or ``None`` when extraction or validation fails.
    """
    raw = _extract_from_code_block(text) or _extract_by_brace_scan(text)

    if raw is None:
        logger.warning(
            "json_extract_failed | strategy=none_matched | text_len=%d | tail=%.200s",
            len(text), text[-200:],
        )
        return None

    # --- Parse ---
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "json_extract_failed | strategy=parse_error | error=%s | raw_head=%.500s",
            exc, raw[:500],
        )
        return None

    if not isinstance(parsed, dict):
        logger.warning(
            "json_extract_failed | strategy=not_a_dict | type=%s",
            type(parsed).__name__,
        )
        return None

    # --- Validate (soft) ---
    # Accept if at least 'summary' or 'choices' is present.
    if "summary" not in parsed and "choices" not in parsed:
        logger.warning(
            "json_extract_failed | strategy=missing_keys | keys=%s",
            list(parsed.keys()),
        )
        return None

    # Run Pydantic validation for structural warnings (non-blocking).
    try:
        ChapterMetadata(**parsed)
    except ValidationError as exc:
        logger.info(
            "json_extract_warning | pydantic_issues=%d | detail=%s",
            exc.error_count(), exc.errors(),
        )
        # Still return the dict — partial metadata is better than none.

    return parsed


# ---------------------------------------------------------------------------
# Extraction strategies
# ---------------------------------------------------------------------------

def _extract_from_code_block(text: str) -> Optional[str]:
    """
    Extract JSON from the **last** ``\\`\\`\\`json ... \\`\\`\\``` fenced code block.

    The Storyteller prompt explicitly asks the LLM to wrap metadata in a
    fenced block, so this is the highest-confidence strategy.
    """
    marker = "```json"
    idx = text.rfind(marker)
    if idx == -1:
        return None

    start = idx + len(marker)
    end = text.find("```", start)
    if end == -1:
        # Unclosed code block — take everything after the marker.
        candidate = text[start:].strip()
    else:
        candidate = text[start:end].strip()

    return candidate or None


def _extract_by_brace_scan(text: str) -> Optional[str]:
    """
    Find the last balanced ``{…}`` block in *text* that parses as valid JSON.

    Scans backwards from the end so we skip any stray ``{`` in the narrative.
    """
    search_from = len(text)

    while True:
        # Find the last '{' before our current cursor.
        open_idx = text.rfind("{", 0, search_from)
        if open_idx == -1:
            return None

        # Walk forward to find the matching '}'.
        close_idx = _find_matching_brace(text, open_idx)
        if close_idx is not None:
            candidate = text[open_idx : close_idx + 1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass

        # Try the previous '{'.
        search_from = open_idx


def _find_matching_brace(text: str, start: int) -> Optional[int]:
    """
    Return the index of the ``}`` that balances the ``{`` at *start*,
    respecting JSON string literals so embedded braces don't confuse the count.
    """
    depth = 0
    in_string = False
    escape = False
    length = len(text)

    for i in range(start, length):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\":
            if in_string:
                escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i

    return None
