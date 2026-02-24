"""
Bible Delta Processor

Processes BibleDelta structured output from the Archivist agent
and applies changes to the World Bible.

This replaces the tool-call-based approach with deterministic updates.
"""
import copy
import json
import logging
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from src.database import AsyncSessionLocal
from src.models import WorldBible
from src.schemas import BibleDelta

logger = logging.getLogger(__name__)


async def apply_bible_delta(story_id: str, delta: BibleDelta) -> Dict[str, Any]:
    """
    Apply a BibleDelta to the World Bible.

    Args:
        story_id: The story UUID
        delta: BibleDelta structured output from Archivist

    Returns:
        dict with results: {success, updates_applied, errors}
    """
    results = {
        "success": False,
        "updates_applied": [],
        "errors": []
    }

    async with AsyncSessionLocal() as db:
        try:
            # Get Bible with lock
            stmt = select(WorldBible).where(
                WorldBible.story_id == story_id
            ).with_for_update()
            result = await db.execute(stmt)
            bible = result.scalar_one_or_none()

            if not bible or not bible.content:
                results["errors"].append("World Bible not found")
                return results

            content = copy.deepcopy(bible.content)

            # Apply each type of update
            _apply_relationship_updates(content, delta, results)
            _apply_character_voice_updates(content, delta, results)
            _apply_knowledge_updates(content, delta, results)
            _apply_stakes_refinements(content, delta, results)
            _apply_divergence_refinements(content, delta, results)
            _apply_new_divergences(content, delta, results)
            _apply_butterfly_effects(content, delta, results)
            _apply_protagonist_status(content, delta, results)
            _apply_location_updates(content, delta, results)
            _apply_faction_updates(content, delta, results)
            _apply_knowledge_violations(content, delta, results)
            _apply_power_scaling_violations(content, delta, results)

            # Save if we made updates
            if results["updates_applied"]:
                bible.content = content
                flag_modified(bible, "content")
                await db.commit()

                # Sync to disk for debugging
                try:
                    with open("src/world_bible.json", 'w') as f:
                        json.dump(content, f, indent=2)
                except Exception:
                    pass

                results["success"] = True
                logger.info(f"Applied {len(results['updates_applied'])} Bible updates: {results['updates_applied']}")
            else:
                results["success"] = True  # No updates needed is still success
                logger.info("No Bible updates to apply from delta")

        except Exception as e:
            results["errors"].append(str(e))
            logger.error(f"Error applying Bible delta: {e}")

    return results


def _apply_relationship_updates(content: dict, delta: BibleDelta, results: dict):
    """Apply relationship updates to character_sheet.relationships."""
    if not delta.relationship_updates:
        return

    if "character_sheet" not in content:
        content["character_sheet"] = {}
    if "relationships" not in content["character_sheet"]:
        content["character_sheet"]["relationships"] = {}

    relationships = content["character_sheet"]["relationships"]

    for update in delta.relationship_updates:
        char_name = update.character_name

        # Get existing or create new
        existing = relationships.get(char_name, {})

        # Merge update into existing (update only non-None fields)
        update_dict = update.model_dump(exclude={"character_name"}, exclude_none=True)
        existing.update(update_dict)

        relationships[char_name] = existing
        results["updates_applied"].append(f"relationship:{char_name}")


def _apply_character_voice_updates(content: dict, delta: BibleDelta, results: dict):
    """Apply character voice updates to character_voices."""
    if not delta.character_voice_updates:
        return

    if "character_voices" not in content:
        content["character_voices"] = {}

    voices = content["character_voices"]

    for update in delta.character_voice_updates:
        char_name = update.character_name

        # Get existing or create new
        existing = voices.get(char_name, {})

        # Merge update into existing
        update_dict = update.model_dump(exclude={"character_name"}, exclude_none=True)
        existing.update(update_dict)

        voices[char_name] = existing
        results["updates_applied"].append(f"voice:{char_name}")


def _apply_knowledge_updates(content: dict, delta: BibleDelta, results: dict):
    """Apply knowledge boundary updates."""
    if not delta.knowledge_updates:
        return

    if "knowledge_boundaries" not in content:
        content["knowledge_boundaries"] = {}
    if "character_knowledge_limits" not in content["knowledge_boundaries"]:
        content["knowledge_boundaries"]["character_knowledge_limits"] = {}

    limits = content["knowledge_boundaries"]["character_knowledge_limits"]

    for update in delta.knowledge_updates:
        char_name = update.character_name

        # Get existing or create new
        existing = limits.get(char_name, {"knows": [], "doesnt_know": [], "suspects": []})

        # Append new learned items (avoid duplicates)
        for item in update.learned:
            if item not in existing.get("knows", []):
                existing.setdefault("knows", []).append(item)

        # Append new suspicions (avoid duplicates)
        for item in update.now_suspects:
            if item not in existing.get("suspects", []):
                existing.setdefault("suspects", []).append(item)

        limits[char_name] = existing
        results["updates_applied"].append(f"knowledge:{char_name}")


def _apply_stakes_refinements(content: dict, delta: BibleDelta, results: dict):
    """Apply stakes refinements (costs_paid, near_misses, pending_consequences)."""
    # Find the stakes section (could be stakes_and_consequences or stakes_tracking)
    stakes_key = "stakes_and_consequences"
    if stakes_key not in content:
        stakes_key = "stakes_tracking"
    if stakes_key not in content:
        content["stakes_and_consequences"] = {}
        stakes_key = "stakes_and_consequences"

    stakes = content[stakes_key]

    # Costs paid refinements
    if delta.costs_paid_refinements:
        if "costs_paid" not in stakes:
            stakes["costs_paid"] = []

        for cost in delta.costs_paid_refinements:
            cost_dict = cost.model_dump()
            # Check if this is a refinement of existing or new
            existing_idx = _find_matching_entry(
                stakes["costs_paid"],
                cost_dict,
                match_fields=["chapter"],
                fuzzy_fields=["cost"]
            )
            if existing_idx is not None:
                stakes["costs_paid"][existing_idx].update(cost_dict)
            else:
                stakes["costs_paid"].append(cost_dict)
            results["updates_applied"].append(f"cost_paid:ch{cost.chapter}")

    # Near misses refinements
    if delta.near_misses_refinements:
        if "near_misses" not in stakes:
            stakes["near_misses"] = []

        for miss in delta.near_misses_refinements:
            miss_dict = miss.model_dump()
            existing_idx = _find_matching_entry(
                stakes["near_misses"],
                miss_dict,
                match_fields=["chapter"],
                fuzzy_fields=["what_almost_happened"]
            )
            if existing_idx is not None:
                stakes["near_misses"][existing_idx].update(miss_dict)
            else:
                stakes["near_misses"].append(miss_dict)
            results["updates_applied"].append(f"near_miss:ch{miss.chapter}")

    # Pending consequences refinements
    if delta.pending_consequences_refinements:
        if "pending_consequences" not in stakes:
            stakes["pending_consequences"] = []

        for cons in delta.pending_consequences_refinements:
            cons_dict = cons.model_dump()
            existing_idx = _find_matching_entry(
                stakes["pending_consequences"],
                cons_dict,
                match_fields=[],
                fuzzy_fields=["action", "predicted_consequence"]
            )
            if existing_idx is not None:
                stakes["pending_consequences"][existing_idx].update(cons_dict)
            else:
                stakes["pending_consequences"].append(cons_dict)
            results["updates_applied"].append(f"pending_consequence:{cons.action[:20]}")


def _apply_divergence_refinements(content: dict, delta: BibleDelta, results: dict):
    """Apply refinements to existing divergences."""
    if not delta.divergence_refinements:
        return

    if "divergences" not in content:
        content["divergences"] = {"list": []}
    if "list" not in content["divergences"]:
        content["divergences"]["list"] = []

    div_list = content["divergences"]["list"]

    for refinement in delta.divergence_refinements:
        # Find divergence by ID
        for div in div_list:
            if div.get("id") == refinement.divergence_id:
                # Apply refinements (only non-None fields)
                if refinement.canon_event:
                    div["canon_event"] = refinement.canon_event
                if refinement.cause:
                    div["cause"] = refinement.cause
                if refinement.severity:
                    div["severity"] = refinement.severity
                if refinement.ripple_effects:
                    existing_effects = div.get("ripple_effects", [])
                    for effect in refinement.ripple_effects:
                        if effect not in existing_effects:
                            existing_effects.append(effect)
                    div["ripple_effects"] = existing_effects
                results["updates_applied"].append(f"divergence_refined:{refinement.divergence_id}")
                break


def _apply_new_divergences(content: dict, delta: BibleDelta, results: dict):
    """Apply new divergences."""
    if not delta.new_divergences:
        return

    if "divergences" not in content:
        content["divergences"] = {"list": [], "stats": {"total": 0, "major": 0, "minor": 0}}
    if "list" not in content["divergences"]:
        content["divergences"]["list"] = []

    div_list = content["divergences"]["list"]
    existing_count = len(div_list)

    for i, new_div in enumerate(delta.new_divergences):
        div_id = f"div_{existing_count + i + 1:03d}"
        div_entry = {
            "id": div_id,
            "chapter": content.get("meta", {}).get("current_chapter", 0),
            "what_changed": new_div.what_changed,
            "canon_event": new_div.canon_event,
            "cause": new_div.cause,
            "severity": new_div.severity,
            "status": "active",
            "ripple_effects": new_div.ripple_effects,
            "affected_canon_events": new_div.affected_canon_events
        }
        div_list.append(div_entry)
        results["updates_applied"].append(f"new_divergence:{div_id}")

    # Update stats
    major_count = sum(1 for d in div_list if d.get("severity") in ("major", "critical"))
    content["divergences"]["stats"] = {
        "total": len(div_list),
        "major": major_count,
        "minor": len(div_list) - major_count
    }


def _apply_butterfly_effects(content: dict, delta: BibleDelta, results: dict):
    """Apply new butterfly effects."""
    if not delta.new_butterfly_effects:
        return

    if "divergences" not in content:
        content["divergences"] = {"list": [], "stats": {}, "butterfly_effects": []}
    if "butterfly_effects" not in content["divergences"]:
        content["divergences"]["butterfly_effects"] = []

    effects = content["divergences"]["butterfly_effects"]

    for effect in delta.new_butterfly_effects:
        effect_dict = effect.model_dump()
        # Avoid duplicates by checking prediction text
        existing = any(
            e.get("prediction", "").lower() == effect_dict.get("prediction", "").lower()
            for e in effects
        )
        if not existing:
            effects.append(effect_dict)
            results["updates_applied"].append(f"butterfly_effect:{effect.prediction[:30]}")


def _apply_protagonist_status(content: dict, delta: BibleDelta, results: dict):
    """Apply protagonist status updates."""
    if not delta.protagonist_status_json:
        return

    try:
        status_updates = json.loads(delta.protagonist_status_json)
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Invalid protagonist_status_json: {delta.protagonist_status_json}")
        return

    if "character_sheet" not in content:
        content["character_sheet"] = {}
    if "status" not in content["character_sheet"]:
        content["character_sheet"]["status"] = {}

    # Merge status updates
    content["character_sheet"]["status"].update(status_updates)
    results["updates_applied"].append("protagonist_status")


def _apply_location_updates(content: dict, delta: BibleDelta, results: dict):
    """Apply location updates."""
    if not delta.location_updates_json:
        return

    try:
        location_updates = json.loads(delta.location_updates_json)
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Invalid location_updates_json: {delta.location_updates_json}")
        return

    if "world_state" not in content:
        content["world_state"] = {}
    if "locations" not in content["world_state"]:
        content["world_state"]["locations"] = {}

    # Merge location updates
    for loc_name, loc_data in location_updates.items():
        existing = content["world_state"]["locations"].get(loc_name, {})
        existing.update(loc_data)
        content["world_state"]["locations"][loc_name] = existing
        results["updates_applied"].append(f"location:{loc_name}")


def _apply_faction_updates(content: dict, delta: BibleDelta, results: dict):
    """Apply faction updates."""
    if not delta.faction_updates_json:
        return

    try:
        faction_updates = json.loads(delta.faction_updates_json)
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Invalid faction_updates_json: {delta.faction_updates_json}")
        return

    if "world_state" not in content:
        content["world_state"] = {}
    if "factions" not in content["world_state"]:
        content["world_state"]["factions"] = {}

    # Merge faction updates
    for faction_name, faction_data in faction_updates.items():
        existing = content["world_state"]["factions"].get(faction_name, {})
        existing.update(faction_data)
        content["world_state"]["factions"][faction_name] = existing
        results["updates_applied"].append(f"faction:{faction_name}")


def _apply_knowledge_violations(content: dict, delta, results: dict):
    """Log knowledge boundary violations to quality_audit."""
    if not delta.knowledge_violations:
        return
    if "quality_audit" not in content:
        content["quality_audit"] = {}
    if "knowledge_violations" not in content["quality_audit"]:
        content["quality_audit"]["knowledge_violations"] = []
    for violation in delta.knowledge_violations:
        content["quality_audit"]["knowledge_violations"].append(violation.model_dump())
        results["updates_applied"].append(
            f"knowledge_violation:{violation.character_name}"
        )


def _apply_power_scaling_violations(content: dict, delta, results: dict):
    """Log power scaling violations to quality_audit."""
    if not delta.power_scaling_violations:
        return
    if "quality_audit" not in content:
        content["quality_audit"] = {}
    if "power_scaling_violations" not in content["quality_audit"]:
        content["quality_audit"]["power_scaling_violations"] = []
    for violation in delta.power_scaling_violations:
        content["quality_audit"]["power_scaling_violations"].append(violation.model_dump())
        results["updates_applied"].append(
            f"power_scaling_violation:{violation.character_name}"
        )


def _find_matching_entry(entries: list, new_entry: dict, match_fields: list, fuzzy_fields: list = None) -> int | None:
    """Find index of existing entry that matches on specified fields.

    Args:
        entries: List of existing entries
        new_entry: New entry to match against
        match_fields: Fields that must match exactly (e.g., chapter number)
        fuzzy_fields: Fields that can match partially (substring match)
    """
    fuzzy_fields = fuzzy_fields or []

    for i, entry in enumerate(entries):
        # Check exact match fields
        exact_matches = all(
            entry.get(field) == new_entry.get(field)
            for field in match_fields
            if new_entry.get(field) is not None
        )

        # Check fuzzy match fields (substring or similar text)
        fuzzy_matches = True
        for field in fuzzy_fields:
            new_val = str(new_entry.get(field, "")).lower()
            existing_val = str(entry.get(field, "")).lower()
            if new_val and existing_val:
                # Match if either is substring of the other, or they share significant words
                if not (new_val in existing_val or existing_val in new_val):
                    # Check word overlap (at least 50% words match)
                    new_words = set(new_val.split())
                    existing_words = set(existing_val.split())
                    overlap = len(new_words & existing_words)
                    if overlap < min(len(new_words), len(existing_words)) * 0.5:
                        fuzzy_matches = False
                        break

        if exact_matches and fuzzy_matches:
            return i
    return None
