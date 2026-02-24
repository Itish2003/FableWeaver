"""
World Bible Validator

This module provides validation and auto-fix functionality for World Bible entries.
It converts legacy data formats to the canonical schemas defined in src/schemas/.

Usage:
    from src.utils.bible_validator import validate_and_fix_bible_entry

    # Before saving to database
    validated_value = validate_and_fix_bible_entry(path, value)
"""
from typing import Any, Dict, List, Optional
import logging
import copy

logger = logging.getLogger(__name__)


def validate_and_fix_bible_entry(path: str, value: Any) -> Any:
    """
    Validate and auto-fix Bible entries before saving.

    This function detects legacy formats and converts them to the canonical
    schemas expected by the frontend components.

    Args:
        path: The Bible path being updated (e.g., "stakes_tracking.costs_paid")
        value: The value to validate/fix

    Returns:
        The validated and potentially fixed value
    """
    if value is None:
        return value

    # Handle list fields that need item-by-item fixing
    # Support both "stakes_tracking" and "stakes_and_consequences" paths
    if path in ("stakes_tracking.costs_paid", "stakes_and_consequences.costs_paid") and isinstance(value, list):
        return [_fix_cost(c) for c in value]

    elif path in ("stakes_tracking.near_misses", "stakes_and_consequences.near_misses") and isinstance(value, list):
        return [_fix_near_miss(m) for m in value]

    elif path in ("stakes_tracking.pending_consequences", "stakes_and_consequences.pending_consequences") and isinstance(value, list):
        return [_fix_consequence(c) for c in value]

    elif path == "divergences.list" and isinstance(value, list):
        return [_fix_divergence(d, i) for i, d in enumerate(value)]

    elif path == "story_timeline.chapter_dates" and isinstance(value, list):
        return _dedupe_and_fix_chapter_dates(value)

    elif path == "story_timeline.events" and isinstance(value, list):
        return [_fix_timeline_event(e) for e in value]

    elif path == "divergences.butterfly_effects" and isinstance(value, list):
        return [_fix_butterfly_effect(e) for e in value]

    # Handle full section updates
    # Support both "stakes_tracking" and "stakes_and_consequences" paths
    elif path in ("stakes_tracking", "stakes_and_consequences") and isinstance(value, dict):
        return _fix_stakes_tracking(value)

    elif path == "divergences" and isinstance(value, dict):
        return _fix_divergences_section(value)

    elif path == "story_timeline" and isinstance(value, dict):
        return _fix_timeline_section(value)

    return value


def _fix_cost(cost: Any) -> dict:
    """Convert legacy cost format to current schema.

    Expected: {cost, severity, chapter}
    Legacy: {cost} (missing severity/chapter)
    """
    if not isinstance(cost, dict):
        # Handle string entries
        return {
            "cost": str(cost),
            "severity": "medium",
            "chapter": 0
        }

    result = copy.deepcopy(cost)

    if "severity" not in result:
        result["severity"] = "medium"
    if "chapter" not in result:
        result["chapter"] = 0

    return result


def _fix_near_miss(miss: Any) -> dict:
    """Convert legacy near_miss format to current schema.

    Expected: {what_almost_happened, saved_by, chapter}
    Legacy: {event} (wrong field name)
    """
    if not isinstance(miss, dict):
        return {
            "what_almost_happened": str(miss),
            "saved_by": "Unknown",
            "chapter": 0
        }

    result = copy.deepcopy(miss)

    # Convert legacy 'event' field to 'what_almost_happened'
    if "event" in result and "what_almost_happened" not in result:
        result["what_almost_happened"] = result.pop("event")

    if "what_almost_happened" not in result:
        result["what_almost_happened"] = "Unknown near miss"
    if "saved_by" not in result:
        result["saved_by"] = "Unknown"
    if "chapter" not in result:
        result["chapter"] = 0

    return result


def _fix_consequence(cons: Any) -> dict:
    """Convert legacy consequence format to current schema.

    Expected: {action, predicted_consequence, due_by}
    Legacy: {chapter, consequence} (wrong field names)
    """
    if not isinstance(cons, dict):
        return {
            "action": "Previous events",
            "predicted_consequence": str(cons),
            "due_by": "Ongoing"
        }

    result = copy.deepcopy(cons)

    # Convert legacy 'consequence' field to 'predicted_consequence'
    if "consequence" in result and "predicted_consequence" not in result:
        result["predicted_consequence"] = result.pop("consequence")

    # Generate 'action' from chapter or consequence text if not present
    if "action" not in result or result["action"] == "Chapter ? actions":
        chapter = result.get("chapter")
        if chapter and isinstance(chapter, int):
            result["action"] = f"Chapter {chapter} events"
        else:
            # Try to extract action from consequence text
            consequence = result.get("predicted_consequence", "")
            if "due to" in consequence.lower():
                # Extract cause after "due to"
                parts = consequence.lower().split("due to", 1)
                if len(parts) > 1:
                    cause = parts[1].strip().rstrip(".")
                    result["action"] = cause[:50].capitalize() + ("..." if len(cause) > 50 else "")
                else:
                    result["action"] = "Previous story events"
            elif "from" in consequence.lower() and "chapter" in consequence.lower():
                result["action"] = "Previous chapter events"
            else:
                result["action"] = "Story progression"

    # Generate 'due_by' from chapter if not present
    if "due_by" not in result:
        chapter = result.get("chapter")
        if chapter and isinstance(chapter, int):
            result["due_by"] = f"Chapter {chapter + 2}"
        else:
            result["due_by"] = "Ongoing"

    # Remove legacy 'chapter' field (not in current schema)
    result.pop("chapter", None)

    if "predicted_consequence" not in result:
        result["predicted_consequence"] = "Unknown consequence"

    return result


def _fix_divergence(div: Any, index: int) -> dict:
    """Convert legacy divergence format to current schema.

    Expected: {id, chapter, what_changed, severity, status, canon_event,
               cause, ripple_effects, affected_canon_events}
    Legacy: {divergence} instead of {what_changed}
    """
    if not isinstance(div, dict):
        return {
            "id": f"div_{index + 1:03d}",
            "chapter": 0,
            "what_changed": str(div),
            "severity": "minor",
            "status": "active",
            "canon_event": "",
            "cause": "OC intervention",
            "ripple_effects": [],
            "affected_canon_events": []
        }

    result = copy.deepcopy(div)

    # Convert legacy 'divergence' field to 'what_changed'
    if "divergence" in result and "what_changed" not in result:
        result["what_changed"] = result.pop("divergence")

    # Ensure required fields
    if "id" not in result or not result["id"] or result["id"] == "no-id":
        result["id"] = f"div_{index + 1:03d}"
    if "chapter" not in result:
        result["chapter"] = 0
    if "what_changed" not in result:
        result["what_changed"] = "Unknown divergence"
    if "severity" not in result:
        result["severity"] = "minor"
    if "status" not in result:
        result["status"] = "active"
    if "canon_event" not in result:
        result["canon_event"] = ""
    if "cause" not in result:
        result["cause"] = "OC intervention"
    if "ripple_effects" not in result:
        result["ripple_effects"] = []
    if "affected_canon_events" not in result:
        result["affected_canon_events"] = []

    return result


def _fix_chapter_date(date: Any) -> dict:
    """Convert legacy chapter_date format to current schema.

    Expected: {chapter, date}
    Legacy: {chapter, start, end}
    """
    if not isinstance(date, dict):
        return {
            "chapter": 0,
            "date": str(date)
        }

    result = copy.deepcopy(date)

    # Convert legacy start/end to single date
    if "date" not in result:
        start = result.get("start", "")
        end = result.get("end", "")

        if not start and not end:
            result["date"] = "Unknown"
        elif start == end or not end:
            result["date"] = start
        elif not start:
            result["date"] = end
        else:
            result["date"] = f"{start} - {end}"

        # Remove legacy fields
        result.pop("start", None)
        result.pop("end", None)

    if "chapter" not in result:
        result["chapter"] = 0

    return result


def _dedupe_and_fix_chapter_dates(dates: List[Any]) -> List[dict]:
    """Fix and deduplicate chapter dates.

    Keeps the most detailed entry for each chapter number.
    """
    fixed = [_fix_chapter_date(d) for d in dates]

    # Deduplicate by chapter number, keeping most detailed
    by_chapter: Dict[int, dict] = {}
    for date in fixed:
        chapter = date.get("chapter", 0)
        if chapter not in by_chapter:
            by_chapter[chapter] = date
        else:
            # Keep the one with the longer/more detailed date string
            existing_date = by_chapter[chapter].get("date", "")
            new_date = date.get("date", "")
            if len(new_date) > len(existing_date):
                by_chapter[chapter] = date

    # Sort by chapter number
    return sorted(by_chapter.values(), key=lambda x: x.get("chapter", 0))


def _fix_timeline_event(event: Any) -> dict:
    """Fix timeline event format.

    Expected: {event, date, chapter, type}
    """
    if not isinstance(event, dict):
        return {
            "event": str(event),
            "date": "Unknown",
            "chapter": None,
            "type": "story"
        }

    result = copy.deepcopy(event)

    if "event" not in result:
        result["event"] = "Unknown event"
    if "date" not in result or result.get("date") == "?":
        result["date"] = "Unknown"
    if "type" not in result:
        result["type"] = "story"

    return result


def _fix_butterfly_effect(effect: Any) -> dict:
    """Fix butterfly effect format.

    Expected: {prediction, probability, materialized, source_divergence}
    """
    if not isinstance(effect, dict):
        return {
            "prediction": str(effect),
            "probability": None,
            "materialized": False,
            "source_divergence": None
        }

    result = copy.deepcopy(effect)

    if "prediction" not in result:
        result["prediction"] = "Unknown effect"
    if "materialized" not in result:
        result["materialized"] = False

    return result


def _fix_stakes_tracking(stakes: dict) -> dict:
    """Fix entire stakes_tracking section."""
    result = copy.deepcopy(stakes)

    if "costs_paid" in result:
        result["costs_paid"] = [_fix_cost(c) for c in result["costs_paid"]]
    if "near_misses" in result:
        result["near_misses"] = [_fix_near_miss(m) for m in result["near_misses"]]
    if "pending_consequences" in result:
        result["pending_consequences"] = [
            _fix_consequence(c) for c in result["pending_consequences"]
        ]

    return result


def _fix_divergences_section(divs: dict) -> dict:
    """Fix entire divergences section."""
    result = copy.deepcopy(divs)

    if "list" in result:
        result["list"] = [
            _fix_divergence(d, i) for i, d in enumerate(result["list"])
        ]

    if "butterfly_effects" in result:
        result["butterfly_effects"] = [
            _fix_butterfly_effect(e) for e in result["butterfly_effects"]
        ]

    # Update stats
    if "list" in result:
        div_list = result["list"]
        major_count = sum(
            1 for d in div_list
            if d.get("severity") in ("major", "critical")
        )
        result["stats"] = {
            "total": len(div_list),
            "major": major_count,
            "minor": len(div_list) - major_count
        }

    return result


def _fix_timeline_section(timeline: dict) -> dict:
    """Fix entire story_timeline section."""
    result = copy.deepcopy(timeline)

    if "chapter_dates" in result:
        result["chapter_dates"] = _dedupe_and_fix_chapter_dates(
            result["chapter_dates"]
        )

    # Build chapter-to-date mapping for backfilling missing event dates
    chapter_date_map = {}
    for cd in result.get("chapter_dates", []):
        chapter = cd.get("chapter")
        date = cd.get("date")
        if chapter and date:
            chapter_date_map[chapter] = date

    if "events" in result:
        fixed_events = []
        for event in result["events"]:
            fixed = _fix_timeline_event(event)
            # Backfill missing dates from chapter_dates
            if fixed.get("date") in (None, "Unknown", "?", ""):
                chapter = fixed.get("chapter")
                if chapter and chapter in chapter_date_map:
                    fixed["date"] = chapter_date_map[chapter]
            fixed_events.append(fixed)
        result["events"] = fixed_events

    return result


def check_power_origin_context_leakage(power_origin: dict, universe: Optional[str] = None) -> List[str]:
    """
    Check for universe-specific terminology in power_origin that indicates context leakage.

    Detects common source-universe concepts that shouldn't appear in mechanics descriptions:
    - JJK terms: "cursed technique", "cursed energy", "jujutsu", "domain"
    - Worm terms: "shard", "trigger", "parahuman", "power"
    - General fiction system terms: "qi", "mana", "cultivation"

    Args:
        power_origin: The power_origin dict from World Bible
        universe: Optional universe name to guide checking (e.g., "Jujutsu Kaisen")

    Returns:
        List of leakage warnings found in the power_origin entry
    """
    warnings = []

    # Terms associated with specific universes - these should only be in source_universe_context
    universe_specific_terms = {
        "jjk": ["cursed technique", "cursed energy", "jujutsu", "domain expansion", "binding vow"],
        "worm": ["shard", "trigger event", "parahuman", "cape"],
        "naruto": ["chakra", "jutsu", "kekkei genkai", "biju"],
        "cultivation": ["qi", "qi cultivation", "cultivation stage", "realm", "dantian"],
    }

    # Fields to check in power_origin
    fields_to_check = [
        "power_name",
        "combat_style",
        "weaknesses_and_counters"
    ]

    # Check canon_techniques for leakage
    for i, technique in enumerate(power_origin.get("canon_techniques", [])):
        for field in ["name", "description"]:
            text = technique.get(field, "").lower()
            for category, terms in universe_specific_terms.items():
                for term in terms:
                    if term in text:
                        warnings.append(
                            f"canon_techniques[{i}].{field}: Found universe-specific term '{term}' "
                            f"(move to source_universe_context)"
                        )

    # Check other fields
    for field in fields_to_check:
        text = power_origin.get(field, "").lower()
        for category, terms in universe_specific_terms.items():
            for term in terms:
                if term in text:
                    warnings.append(
                        f"{field}: Found universe-specific term '{term}' "
                        f"(move to source_universe_context)"
                    )

    return warnings


def validate_bible_integrity(bible: dict) -> List[str]:
    """
    Check Bible data integrity and return list of issues.

    Args:
        bible: The full World Bible content

    Returns:
        List of issue descriptions (empty if valid)
    """
    issues = []

    # Check pending_consequences schema
    # Note: Bible may use either "stakes_tracking" or "stakes_and_consequences"
    stakes = bible.get("stakes_tracking", bible.get("stakes_and_consequences", {}))
    for i, cons in enumerate(stakes.get("pending_consequences", [])):
        if "predicted_consequence" not in cons:
            issues.append(
                f"pending_consequences[{i}] missing 'predicted_consequence'"
            )
        if "action" not in cons:
            issues.append(f"pending_consequences[{i}] missing 'action'")
        if "due_by" not in cons:
            issues.append(f"pending_consequences[{i}] missing 'due_by'")

    # Check near_misses schema
    for i, miss in enumerate(stakes.get("near_misses", [])):
        if "what_almost_happened" not in miss:
            issues.append(
                f"near_misses[{i}] missing 'what_almost_happened'"
            )

    # Check costs_paid schema
    for i, cost in enumerate(stakes.get("costs_paid", [])):
        if "severity" not in cost:
            issues.append(f"costs_paid[{i}] missing 'severity'")

    # Check divergences schema
    divs = bible.get("divergences", {})
    for i, div in enumerate(divs.get("list", [])):
        if "what_changed" not in div:
            issues.append(f"divergences.list[{i}] missing 'what_changed'")
        if not div.get("id"):
            issues.append(f"divergences.list[{i}] missing 'id'")

    # Check chapter_dates schema
    timeline = bible.get("story_timeline", {})
    for i, date in enumerate(timeline.get("chapter_dates", [])):
        if "date" not in date:
            issues.append(f"chapter_dates[{i}] missing 'date' field")

    return issues
