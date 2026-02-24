"""Handle the ``research`` WebSocket action — main research orchestrator."""

from __future__ import annotations

import asyncio
from sqlalchemy import select

from src.app import manager
from src.database import AsyncSessionLocal
from src.models import WorldBible
from src.pipelines import get_story_universes
from src.tools.meta_tools import MetaTools
from src.tools.core_tools import BibleTools
from src.utils.legacy_logger import logger
from src.ws.context import WsSessionContext
from src.ws.actions import ActionResult


async def _detect_gaps(content: dict, universes: list[str]) -> list[str]:
    """Internal gap detection (mirrors enrich logic)."""
    gaps = []

    # Check power system
    powers = content.get("character_sheet", {}).get("powers", {})
    sources = content.get("power_origins", {}).get("sources", [])
    detailed_sources = [s for s in sources if isinstance(s, dict) and all(k in s for k in ["canonical_techniques", "combat_style", "signature_moves"])]
    if len(detailed_sources) < len(sources) or len(sources) == 0:
        gaps.append(f"Power origins with detailed techniques - canonical sources, combat style, signature moves for each power system")

    # Check characters
    characters = content.get("world_state", {}).get("characters", {})
    detailed_chars = [c for c in characters.values() if isinstance(c, dict) and all(k in c for k in ["role", "disposition"])]
    if len(detailed_chars) < 5:
        gaps.append(f"Major characters in {', '.join(universes)} - at least 5 with role, universe, powers, relationships, disposition")

    # Check factions
    factions = content.get("world_state", {}).get("factions", {})
    detailed_factions = [f for f in factions.values() if isinstance(f, dict) and all(k in f for k in ["type", "description"])]
    if len(detailed_factions) < 3:
        gaps.append(f"Factions and organizations in {', '.join(universes)} - at least 3 with type, description, hierarchy")

    # Check timeline
    events = content.get("canon_timeline", {}).get("events", [])
    if len(events) < 10:
        gaps.append(f"Canon timeline events for {', '.join(universes)} - major dated events (need at least 10)")

    # Check locations
    locations = content.get("world_state", {}).get("locations", {})
    if len(locations) < 5:
        gaps.append(f"Locations in {', '.join(universes)} - neighborhoods, landmarks, territories, key buildings (need at least 5)")

    # Check character voices
    voices = content.get("character_voices", {})
    if len(voices) < 5:
        gaps.append(f"Character voice profiles for major characters - speech_patterns, verbal_tics, emotional_tells (need at least 5)")

    return gaps


async def handle_research(ctx: WsSessionContext, inner_data: dict) -> ActionResult:
    """Orchestrate research: detect gaps → run research → integrate results."""

    query = inner_data.get("query", "")
    depth = inner_data.get("depth", "quick")

    await manager.send_json({"type": "status", "status": "processing"}, ctx.websocket)

    # Notify user
    mode_indicator = "\U0001f50d **DEEP RESEARCH**" if depth == "deep" else "\U0001f50e **Quick Research**"
    await manager.send_json({
        "type": "content_delta",
        "text": f"\n{mode_indicator}: {query}\n",
        "sender": "system"
    }, ctx.websocket)

    try:
        # Load current Bible
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(WorldBible).where(WorldBible.story_id == ctx.story_id)
            )
            bible_obj = result.scalar_one_or_none()

            if not bible_obj:
                await manager.send_json(
                    {"type": "error", "message": "No World Bible found. Initialize a story first."},
                    ctx.websocket
                )
                await manager.send_json({"type": "turn_complete"}, ctx.websocket)
                return ActionResult(needs_runner=False)

        universes, _ = await get_story_universes(ctx.story_id)
        content = bible_obj.content

        # Step 1: Detect gaps
        await manager.send_json({
            "type": "content_delta",
            "text": f"Analyzing World Bible gaps...\n",
            "sender": "system"
        }, ctx.websocket)

        gaps = await _detect_gaps(content, universes)

        if not gaps:
            await manager.send_json({
                "type": "content_delta",
                "text": f"✓ World Bible is comprehensive. Running confirmatory research on: {query}\n",
                "sender": "system"
            }, ctx.websocket)
            gaps = [query]  # Just research the user query
        else:
            await manager.send_json({
                "type": "content_delta",
                "text": f"Found {len(gaps)} gaps to fill:\n" + "\n".join(f"  • {g[:70]}..." if len(g) > 70 else f"  • {g}" for g in gaps) + "\n\n",
                "sender": "system"
            }, ctx.websocket)

        # Step 2: Run research on gaps
        await manager.send_json({
            "type": "content_delta",
            "text": f"Running research on {len(gaps)} gaps in parallel...\n",
            "sender": "system"
        }, ctx.websocket)

        meta = MetaTools(ctx.story_id)

        async def research_gap(gap_query):
            """Run single research task."""
            try:
                # Report task start
                task_indicator = gap_query[:50] + ("..." if len(gap_query) > 50 else "")
                await manager.send_json({
                    "type": "content_delta",
                    "text": f"  → Researching: {task_indicator}\n",
                    "sender": "system"
                }, ctx.websocket)

                result = await asyncio.wait_for(
                    meta.trigger_research(gap_query, depth=depth, universes=universes),
                    timeout=60.0
                )
                return {"query": gap_query, "success": True, "result": result}
            except asyncio.TimeoutError:
                return {"query": gap_query, "success": False, "error": "Timeout (60s)"}
            except Exception as e:
                return {"query": gap_query, "success": False, "error": str(e)}

        # Run research with timeout for the whole gather
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[research_gap(gap) for gap in gaps]),
                timeout=300.0
            )
        except asyncio.TimeoutError:
            await manager.send_json({
                "type": "content_delta",
                "text": f"⚠️ Research timeout (5 minutes exceeded). Partial results shown below.\n",
                "sender": "system"
            }, ctx.websocket)
            results = []

        # Step 3: Report results
        success_count = sum(1 for r in results if r["success"])
        for r in results:
            if r["success"]:
                await manager.send_json({
                    "type": "content_delta",
                    "text": f"  ✓ {r['result'][:100]}\n",
                    "sender": "system"
                }, ctx.websocket)
            else:
                await manager.send_json({
                    "type": "content_delta",
                    "text": f"  ✗ Failed ({r['query'][:40]}...): {r['error'][:60]}\n",
                    "sender": "system"
                }, ctx.websocket)

        await manager.send_json({
            "type": "content_delta",
            "text": f"\n✓ Research complete! {success_count}/{len(gaps)} gaps researched.\n\n",
            "sender": "system"
        }, ctx.websocket)

        # Step 4: Suggestion for integration
        await manager.send_json({
            "type": "content_delta",
            "text": "📝 Next: Manually integrate research findings into the Bible using database tools,\n   or provide specific structured data to update.",
            "sender": "system"
        }, ctx.websocket)

    except Exception as e:
        logger.exception("Research handler error")
        await manager.send_json({"type": "error", "message": f"Research failed: {e}"}, ctx.websocket)

    await manager.send_json({"type": "turn_complete"}, ctx.websocket)
    return ActionResult(needs_runner=False)
