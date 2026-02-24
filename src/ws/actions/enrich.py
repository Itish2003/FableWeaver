"""Handle the ``enrich`` WebSocket action — gap analysis + parallel research."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from src.database import AsyncSessionLocal
from src.models import WorldBible
from src.app import manager
from src.tools.meta_tools import MetaTools
from src.ws.context import WsSessionContext
from src.ws.actions import ActionResult


async def handle_enrich(ctx: WsSessionContext, inner_data: dict) -> ActionResult:
    focuses = inner_data.get("focuses", ["all"])
    await manager.send_json({"type": "status", "status": "processing"}, ctx.websocket)

    try:
        # Step 1: Read current World Bible to analyze gaps
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(WorldBible).where(WorldBible.story_id == ctx.story_id))
            bible = result.scalar_one_or_none()

            if not bible or not bible.content:
                await manager.send_json({
                    "type": "content_delta",
                    "text": "[Enrich] No World Bible found. Run /research first to initialize.\n",
                    "sender": "system"
                }, ctx.websocket)
                await manager.send_json({"type": "turn_complete"}, ctx.websocket)
                return ActionResult(needs_runner=False)

            content = bible.content
            universes = content.get("meta", {}).get("universes", ["General"])
            gaps = []

            # Analyze gaps based on focuses (multiple allowed)
            await manager.send_json({
                "type": "content_delta",
                "text": f"[Enrich] Analyzing World Bible gaps (focus: {', '.join(focuses)})...\n",
                "sender": "system"
            }, ctx.websocket)

            # Helper to check if any focus matches
            def should_check(categories):
                return "all" in focuses or any(cat in focuses for cat in categories)

            # Check power system
            if should_check(["power_system", "powers", "power", "abilities"]):
                powers = content.get("character_sheet", {}).get("powers", {})
                sources = content.get("power_origins", {}).get("sources", [])
                # Check for detailed power system (each source should have canonical_techniques, combat_style, signature_moves)
                detailed_sources = [s for s in sources if isinstance(s, dict) and all(k in s for k in ["canonical_techniques", "combat_style", "signature_moves"])]
                if len(detailed_sources) < len(sources) or len(sources) == 0:
                    gaps.append(f"Power origins with detailed techniques - canonical sources, combat style, signature moves, and scene-level examples for each power system")

            # Check characters
            if should_check(["characters", "chars", "people", "npcs"]):
                characters = content.get("world_state", {}).get("characters", {})
                # Check for characters with key fields (role, universe, disposition)
                detailed_chars = [c for c in characters.values() if isinstance(c, dict) and all(k in c for k in ["role", "disposition"])]
                if len(detailed_chars) < 5:  # Need at least 5 detailed character entries
                    gaps.append(f"Major characters in {', '.join(universes)} - at least 5 with role, universe, powers, relationships, and disposition to protagonist")

            # Check factions
            if should_check(["factions", "faction", "groups", "teams", "families"]):
                factions = content.get("world_state", {}).get("factions", {})
                # Check for factions with key fields (type, description, hierarchy)
                detailed_factions = [f for f in factions.values() if isinstance(f, dict) and all(k in f for k in ["type", "description"])]
                if len(detailed_factions) < 3:  # Need at least 3 detailed factions
                    gaps.append(f"Factions and organizations in {', '.join(universes)} - at least 3 with type, description, hierarchy, disposition to protagonist")

            # Check locations
            if should_check(["locations", "locs", "location"]):
                locations = content.get("world_state", {}).get("locations", {})
                if len(locations) < 5:
                    gaps.append(f"Locations in {', '.join(universes)} - neighborhoods, landmarks, faction territories, key buildings, with atmosphere, key_features, typical_occupants, story_hooks")
                territory_map = content.get("world_state", {}).get("territory_map", {})
                if len(territory_map) < 3:
                    gaps.append(f"Territory control map for {', '.join(universes)} factions")

            # Check relationships
            if should_check(["relations", "relationships", "family"]):
                relationships = content.get("character_sheet", {}).get("relationships", {})
                factions = content.get("world_state", {}).get("factions", {})
                # Check if protagonist's team/family faction has complete roster
                for faction_name, faction_data in factions.items():
                    if isinstance(faction_data, dict):
                        roster = faction_data.get("complete_member_roster", [])
                        if len(roster) < 3 and faction_data.get("disposition_to_protagonist") == "Allied":
                            gaps.append(f"Complete member roster for {faction_name} including family relationships, living situation, and role")

                if len(relationships) < 3:
                    gaps.append(f"Character relationships for protagonist - family members (with type, relation, trust, family_branch), allies, team members in {', '.join(universes)}")

            # Check character voices
            if should_check(["voices", "voice", "dialogue"]):
                voices = content.get("character_voices", {})
                if len(voices) < 5:
                    gaps.append(f"Character voice profiles for major characters in {', '.join(universes)} - speech_patterns, verbal_tics, emotional_tells, topics_to_discuss, topics_to_avoid, example_dialogue")

            # Check identities
            if should_check(["identities", "identity", "personas"]):
                identities = content.get("character_sheet", {}).get("identities", {})
                if len(identities) < 1:
                    char_name = content.get("character_sheet", {}).get("name", "protagonist")
                    gaps.append(f"Identity profiles for {char_name} - civilian, hero, and any secret identities with known_by, suspected_by, activities, reputation, vulnerabilities")

            # Check timeline events
            if should_check(["events", "timeline", "canon"]):
                events = content.get("canon_timeline", {}).get("events", [])
                if len(events) < 10:
                    gaps.append(f"Canon timeline events for {', '.join(universes)} - major dated events with characters_involved, consequences, importance, status")

            if not gaps:
                await manager.send_json({
                    "type": "content_delta",
                    "text": f"[Enrich] World Bible looks complete for '{', '.join(focuses)}'! No major gaps found.\n",
                    "sender": "system"
                }, ctx.websocket)
                await manager.send_json({"type": "turn_complete"}, ctx.websocket)
                return ActionResult(needs_runner=False)

            await manager.send_json({
                "type": "content_delta",
                "text": f"[Enrich] Found {len(gaps)} gaps to fill:\n" + "\n".join(f"  \u2022 {g[:80]}..." if len(g) > 80 else f"  \u2022 {g}" for g in gaps) + "\n\n",
                "sender": "system"
            }, ctx.websocket)

        # Step 2: Run targeted research in PARALLEL
        meta = MetaTools(ctx.story_id)

        await manager.send_json({
            "type": "content_delta",
            "text": f"[Enrich] Running {len(gaps)} research tasks in parallel...\n",
            "sender": "system"
        }, ctx.websocket)

        async def research_gap(gap_query):
            """Helper to run single research and return result."""
            try:
                res = await meta.trigger_research(gap_query)
                return {"query": gap_query, "success": True, "result": res}
            except Exception as e:
                return {"query": gap_query, "success": False, "error": str(e)}

        # Run all research tasks in parallel
        results = await asyncio.gather(*[research_gap(gap) for gap in gaps])

        # Report results
        success_count = sum(1 for r in results if r["success"])
        for r in results:
            if r["success"]:
                await manager.send_json({
                    "type": "content_delta",
                    "text": f"  \u2713 {r['result']}\n",
                    "sender": "system"
                }, ctx.websocket)
            else:
                await manager.send_json({
                    "type": "content_delta",
                    "text": f"  \u2717 Failed ({r['query'][:30]}...): {r['error'][:50]}\n",
                    "sender": "system"
                }, ctx.websocket)

        await manager.send_json({
            "type": "content_delta",
            "text": f"\n[Enrich] Complete! {success_count}/{len(gaps)} research tasks succeeded.\n",
            "sender": "system"
        }, ctx.websocket)

    except Exception as e:
        await manager.send_json({"type": "error", "message": f"Enrich failed: {e}"}, ctx.websocket)

    await manager.send_json({"type": "turn_complete"}, ctx.websocket)
    return ActionResult(needs_runner=False)
