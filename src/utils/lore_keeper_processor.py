"""
Lore Keeper Output Processor

Processes LoreKeeperOutput structured schema from the Lore Keeper agent
during initialization and applies it to create/update the World Bible.

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
from src.schemas import LoreKeeperOutput

logger = logging.getLogger(__name__)


async def apply_lore_keeper_output(story_id: str, output: LoreKeeperOutput) -> Dict[str, Any]:
    """
    Apply LoreKeeperOutput to initialize or update the World Bible.

    Args:
        story_id: The story UUID
        output: LoreKeeperOutput structured output from Lore Keeper

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
            # Get or create Bible
            stmt = select(WorldBible).where(
                WorldBible.story_id == story_id
            )
            result = await db.execute(stmt)
            bible = result.scalar_one_or_none()

            if not bible:
                results["errors"].append(f"World Bible not found for story {story_id}")
                return results

            content = copy.deepcopy(bible.content) if bible.content else {}

            # Initialize top-level sections if missing
            if "meta" not in content:
                content["meta"] = {}
            if "character_sheet" not in content:
                content["character_sheet"] = {}
            if "power_origins" not in content:
                content["power_origins"] = {"sources": []}
            if "world_state" not in content:
                content["world_state"] = {}
            if "canon_timeline" not in content:
                content["canon_timeline"] = {"events": []}
            if "knowledge_boundaries" not in content:
                content["knowledge_boundaries"] = {}
            if "character_voices" not in content:
                content["character_voices"] = {}
            if "canon_character_integrity" not in content:
                content["canon_character_integrity"] = {"protected_characters": []}
            if "upcoming_canon_events" not in content:
                content["upcoming_canon_events"] = {"events": [], "integration_notes": ""}

            # Apply Character Sheet
            _apply_character_sheet(content, output, results)

            # Apply Power Origins
            _apply_power_origins(content, output, results)

            # Apply Canon Timeline
            _apply_canon_timeline(content, output, results)

            # Apply World State
            _apply_world_state(content, output, results)

            # Apply Metadata
            _apply_metadata(content, output, results)

            # Apply Knowledge Boundaries
            _apply_knowledge_boundaries(content, output, results)

            # Apply new World Bible population fields
            _apply_character_voices(content, output, results)
            _apply_character_relationships(content, output, results)
            _apply_character_knowledge(content, output, results)
            _apply_canon_character_integrity(content, output, results)
            _apply_jobber_prevention_rules(content, output, results)
            _apply_knowledge_secrets_and_limits(content, output, results)
            _apply_upcoming_canon_events(content, output, results)
            _apply_power_interactions(content, output, results)
            _apply_magic_system(content, output, results)
            _apply_entity_aliases(content, output, results)

            # Save updated Bible
            bible.content = content
            flag_modified(bible, "content")
            await db.commit()

            results["success"] = True
            return results

        except Exception as e:
            logger.exception(f"Error applying lore keeper output: {e}")
            results["errors"].append(str(e))
            return results


def _apply_character_sheet(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply character sheet updates."""
    if not output.character_name:
        results["errors"].append("character_name is required")
        return

    content["character_sheet"]["name"] = output.character_name
    results["updates_applied"].append("character_sheet.name")

    if output.character_archetype:
        content["character_sheet"]["archetype"] = output.character_archetype
        results["updates_applied"].append("character_sheet.archetype")

    if output.character_status:
        content["character_sheet"]["status"] = output.character_status
        results["updates_applied"].append("character_sheet.status")

    # Powers as dict (enforced format)
    if output.character_powers:
        content["character_sheet"]["powers"] = output.character_powers
        results["updates_applied"].append("character_sheet.powers")
    else:
        content["character_sheet"]["powers"] = {}


def _apply_power_origins(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply power origins updates."""
    if output.power_origins_sources:
        content["power_origins"]["sources"] = output.power_origins_sources
        results["updates_applied"].append("power_origins.sources")


def _apply_canon_timeline(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply canonical timeline events."""
    if output.canon_timeline_events:
        content["canon_timeline"]["events"] = output.canon_timeline_events
        results["updates_applied"].append("canon_timeline.events")


def _apply_world_state(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply world state updates (characters, locations, factions)."""
    if output.world_state_characters:
        if "characters" not in content["world_state"]:
            content["world_state"]["characters"] = {}
        # Normalize powers to dict format before merging (fixes #46)
        from src.utils.bible_validator import _normalize_characters_powers
        normalized = _normalize_characters_powers(output.world_state_characters)
        content["world_state"]["characters"].update(normalized)
        results["updates_applied"].append("world_state.characters")

    if output.world_state_locations:
        if "locations" not in content["world_state"]:
            content["world_state"]["locations"] = {}
        content["world_state"]["locations"].update(output.world_state_locations)
        results["updates_applied"].append("world_state.locations")

    if output.world_state_factions:
        if "factions" not in content["world_state"]:
            content["world_state"]["factions"] = {}
        content["world_state"]["factions"].update(output.world_state_factions)
        results["updates_applied"].append("world_state.factions")

    if output.world_state_territory_map:
        if "territory_map" not in content["world_state"]:
            content["world_state"]["territory_map"] = {}
        content["world_state"]["territory_map"].update(output.world_state_territory_map)
        results["updates_applied"].append("world_state.territory_map")


def _apply_metadata(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply metadata updates."""
    if output.meta_universes:
        content["meta"]["universes"] = output.meta_universes
        results["updates_applied"].append("meta.universes")

    if output.meta_genre:
        content["meta"]["genre"] = output.meta_genre
        results["updates_applied"].append("meta.genre")

    if output.meta_theme:
        content["meta"]["theme"] = output.meta_theme
        results["updates_applied"].append("meta.theme")

    if output.meta_story_start_date:
        content["meta"]["story_start_date"] = output.meta_story_start_date
        results["updates_applied"].append("meta.story_start_date")


def _apply_knowledge_boundaries(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply knowledge boundary updates."""
    if output.knowledge_meta_knowledge_forbidden:
        content["knowledge_boundaries"]["meta_knowledge_forbidden"] = output.knowledge_meta_knowledge_forbidden
        results["updates_applied"].append("knowledge_boundaries.meta_knowledge_forbidden")

    if output.knowledge_common_knowledge:
        content["knowledge_boundaries"]["common_knowledge"] = output.knowledge_common_knowledge
        results["updates_applied"].append("knowledge_boundaries.common_knowledge")


def _apply_character_voices(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply initial character voice profiles."""
    if output.character_voices:
        if "character_voices" not in content:
            content["character_voices"] = {}
        content["character_voices"].update(output.character_voices)
        results["updates_applied"].append("character_voices")


def _apply_character_relationships(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply protagonist's initial relationship network."""
    if output.character_sheet_relationships:
        if "relationships" not in content["character_sheet"]:
            content["character_sheet"]["relationships"] = {}
        content["character_sheet"]["relationships"].update(output.character_sheet_relationships)
        results["updates_applied"].append("character_sheet.relationships")


def _apply_character_knowledge(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply protagonist's starting knowledge."""
    if output.character_sheet_knowledge:
        content["character_sheet"]["knowledge"] = output.character_sheet_knowledge
        results["updates_applied"].append("character_sheet.knowledge")


def _apply_canon_character_integrity(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply anti-Worfing rules for protected characters."""
    if output.canon_character_integrity_protected:
        if "canon_character_integrity" not in content:
            content["canon_character_integrity"] = {}
        content["canon_character_integrity"]["protected_characters"] = output.canon_character_integrity_protected
        results["updates_applied"].append("canon_character_integrity.protected_characters")


def _apply_jobber_prevention_rules(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply general anti-Worfing rules that apply universe-wide."""
    if output.canon_jobber_prevention_rules:
        if "canon_character_integrity" not in content:
            content["canon_character_integrity"] = {}
        content["canon_character_integrity"]["jobber_prevention_rules"] = output.canon_jobber_prevention_rules
        results["updates_applied"].append("canon_character_integrity.jobber_prevention_rules")


def _apply_knowledge_secrets_and_limits(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply per-character secrets and knowledge limits."""
    if output.knowledge_character_secrets:
        content["knowledge_boundaries"]["character_secrets"] = output.knowledge_character_secrets
        results["updates_applied"].append("knowledge_boundaries.character_secrets")

    if output.knowledge_character_limits:
        content["knowledge_boundaries"]["character_knowledge_limits"] = output.knowledge_character_limits
        results["updates_applied"].append("knowledge_boundaries.character_knowledge_limits")


def _apply_upcoming_canon_events(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply upcoming canon events the story should address."""
    if output.upcoming_canon_events:
        if "upcoming_canon_events" not in content:
            content["upcoming_canon_events"] = {"events": [], "integration_notes": ""}
        content["upcoming_canon_events"]["events"] = output.upcoming_canon_events
        results["updates_applied"].append("upcoming_canon_events")


def _apply_power_interactions(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply power interaction rules for crossover stories."""
    if output.power_interactions:
        content["power_origins"]["power_interactions"] = output.power_interactions
        results["updates_applied"].append("power_origins.power_interactions")


def _apply_magic_system(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply magic/power system rules per universe."""
    if output.world_state_magic_system:
        if "magic_system" not in content["world_state"]:
            content["world_state"]["magic_system"] = {}
        content["world_state"]["magic_system"].update(output.world_state_magic_system)
        results["updates_applied"].append("world_state.magic_system")


def _apply_entity_aliases(content: Dict, output: LoreKeeperOutput, results: Dict) -> None:
    """Apply entity alias mappings."""
    if output.world_state_entity_aliases:
        if "entity_aliases" not in content["world_state"]:
            content["world_state"]["entity_aliases"] = {}
        content["world_state"]["entity_aliases"].update(output.world_state_entity_aliases)
        results["updates_applied"].append("world_state.entity_aliases")
