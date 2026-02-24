"""Handle the ``choice`` WebSocket action — continue the story."""

from __future__ import annotations

import asyncio
import copy
import json
import re

from sqlalchemy import select, desc

from src.database import AsyncSessionLocal
from src.models import History, WorldBible
from src.pipelines import build_game_pipeline, get_story_universes
from src.tools.meta_tools import MetaTools
from src.app import manager
from src.utils.legacy_logger import logger
from src.utils.bible_helpers import format_question_answers
from src.ws.context import WsSessionContext
from src.ws.actions import ActionResult


async def handle_choice(ctx: WsSessionContext, inner_data: dict) -> ActionResult:
    choice_text = inner_data.get("choice", "")
    question_answers = inner_data.get("question_answers", {})
    # Fetch universes from World Bible for context continuity
    universes, deviation = await get_story_universes(ctx.story_id)

    # AUTO-RESEARCH DETECTION
    terminator = r'(?:\.|\!|\?|\s+Lucian|\s+Also|\s+Explore|\s+and\s+keep|\s+Then\s+|,\s+and\s+|$)'
    research_patterns = [
        rf'[Dd]o\s+(?:some\s+)?[Rr]esearch\s+on\s+(.+?){terminator}',
        rf'[Rr]esearch\s+on\s+(.+?){terminator}',
        rf'[Rr]esearch\s+about\s+(.+?){terminator}',
        rf'[Dd]o\s+(?:some\s+)?[Rr]esearch\s+for\s+(.+?){terminator}',
        rf'[Rr]esearch\s+for\s+(.+?){terminator}',
        rf'[Rr]esearch:\s*(.+?){terminator}',
        rf'[Rr]esearch\s+how\s+(.+?){terminator}',
        rf'[Rr]esearch\s+the\s+(.+?){terminator}',
        rf'[Rr]esearch\s+([a-zA-Z][a-zA-Z\s\']+(?:relations?|interactions?|history|background|details?|info(?:rmation)?|abilities|powers?))',
        rf'[Ll]ook\s+(?:up|into)\s+(.+?){terminator}',
        rf'[Ff]ind\s+out\s+(?:about|more about)\s+(.+?){terminator}',
    ]

    # Collect ALL research queries from the choice text
    research_queries = []
    for pattern in research_patterns:
        matches = re.findall(pattern, choice_text, re.IGNORECASE | re.DOTALL)
        for match in matches:
            query = match.strip()
            query = re.sub(r'\s+(And|and|Also|also)\s*$', '', query)
            query = query.rstrip('.,;')
            if query and query not in research_queries:
                research_queries.append(query)

    # If research detected, run ALL queries in PARALLEL before the chapter
    if research_queries:
        logger.log("info", f"Auto-detected {len(research_queries)} research request(s): {research_queries}")
        await manager.send_json({
            "type": "content_delta",
            "text": f"\U0001f50d **Auto-Research Detected:** Found {len(research_queries)} research request(s). Running in parallel...\n",
            "sender": "system"
        }, ctx.websocket)

        for q in research_queries:
            await manager.send_json({
                "type": "content_delta",
                "text": f"  \u2022 {q}\n",
                "sender": "system"
            }, ctx.websocket)

        await manager.send_json({
            "type": "content_delta",
            "text": f"\n",
            "sender": "system"
        }, ctx.websocket)

        async def run_single_research(query: str):
            try:
                meta = MetaTools(ctx.story_id)
                result = await meta.trigger_research(query)
                return (query, True, result)
            except Exception as e:
                return (query, False, str(e))

        results = await asyncio.gather(*[run_single_research(q) for q in research_queries])

        success_count = sum(1 for _, success, _ in results if success)
        for query, success, result in results:
            if success:
                logger.log("info", f"Auto-research completed for: '{query}'")
            else:
                logger.log("warning", f"Auto-research failed for '{query}': {result}")

        await manager.send_json({
            "type": "content_delta",
            "text": f"\u2705 **Research Complete:** {success_count}/{len(research_queries)} queries successful. World Bible updated.\n\n---\n\n",
            "sender": "system"
        }, ctx.websocket)

    # Get current chapter count AND recent summaries for context
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(History).where(History.story_id == ctx.story_id).order_by(desc(History.sequence)).limit(3)
        )
        recent_chapters = result.scalars().all()

        current_chapter = recent_chapters[0].sequence if recent_chapters else 0
        next_chapter = current_chapter + 1

        # Build recent chapter summaries (reverse to chronological order)
        recent_summaries = ""
        if recent_chapters:
            for ch in reversed(recent_chapters):
                if ch.summary:
                    recent_summaries += f"- **Ch.{ch.sequence}**: {ch.summary[:300]}{'...' if len(ch.summary) > 300 else ''}\n"

        last_summary = recent_chapters[0].summary if recent_chapters and recent_chapters[0].summary else "No previous chapter."

        # Extract last chapter's JSON metadata for Archivist
        last_chapter_metadata = ""
        if recent_chapters and recent_chapters[0].text:
            from src.utils.json_extractor import extract_chapter_json
            chapter_data = extract_chapter_json(recent_chapters[0].text)
            if chapter_data:
                metadata_parts = []
                if chapter_data.get('stakes_tracking'):
                    metadata_parts.append(f"**Stakes Tracking:**\n```json\n{json.dumps(chapter_data['stakes_tracking'], indent=2)}\n```")
                if chapter_data.get('timeline'):
                    metadata_parts.append(f"**Timeline:**\n```json\n{json.dumps(chapter_data['timeline'], indent=2)}\n```")
                if chapter_data.get('character_voices_used'):
                    metadata_parts.append(f"**Characters Featured:** {', '.join(v.split('(')[0].strip() for v in chapter_data['character_voices_used'][:5])}")
                if metadata_parts:
                    last_chapter_metadata = "\n\n".join(metadata_parts)

        bible_result = await db.execute(select(WorldBible).where(WorldBible.story_id == ctx.story_id))
        bible = bible_result.scalar_one_or_none()

        # Capture Bible snapshot BEFORE Archivist modifies it (for undo rollback)
        if bible and bible.content:
            ctx.bible_snapshot_content = copy.deepcopy(bible.content)

        story_context = ""
        if bible and bible.content:
            meta = bible.content.get("meta", {})
            char_sheet = bible.content.get("character_sheet", {})
            story_context = f"""
STORY STATE (from World Bible):
- Current Date: {meta.get('current_story_date', 'Unknown')}
- Protagonist: {char_sheet.get('name', 'Unknown')} ({char_sheet.get('cape_name', 'No cape name')})
- Status: {char_sheet.get('status', {}).get('condition', 'Normal') if isinstance(char_sheet.get('status'), dict) else 'Normal'}"""

    # Dynamically switch to game pipeline (Archivist + Storyteller)
    ctx.active_agent = await build_game_pipeline(ctx.story_id, universes=universes, deviation=deviation)

    metadata_section = ""
    if last_chapter_metadata:
        metadata_section = f"""
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
                    LAST CHAPTER METADATA (FOR ARCHIVIST)
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
{last_chapter_metadata}
"""

    bible_state_section = ""
    if ctx.bible_snapshot_content:
        bible_state_section = f"""
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
                    CURRENT WORLD BIBLE STATE (FOR ARCHIVIST)
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
```json
{json.dumps(ctx.bible_snapshot_content, indent=2)}
```
"""

    ctx.input_text = f"""\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
                         NARRATIVE CONTEXT (Use for continuity)
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

**RECENT CHAPTER SUMMARIES:**
{recent_summaries if recent_summaries else "This is Chapter 1 - no previous chapters."}

**LAST CHAPTER (Ch.{current_chapter}) SUMMARY:**
{last_summary}
{story_context}
{metadata_section}
{bible_state_section}
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
                              PLAYER ACTION
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

{choice_text}

{format_question_answers(question_answers) if question_answers else ""}
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
                            CHAPTER INSTRUCTIONS
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

CHAPTER TRACKING:
- Previous chapter was: Chapter {current_chapter}
- You are now writing: Chapter {next_chapter}
- Start your output with "# Chapter {next_chapter}"

ARCHIVIST: Use the CURRENT WORLD BIBLE STATE and LAST CHAPTER METADATA above to produce a BibleDelta with all necessary updates.

STORYTELLER: Reference the World Bible state provided above for complete context, character voices, and canon events.

Proceed to write the next chapter."""
    logger.log("pipeline", f"Enabled GAME pipeline for story {ctx.story_id} with universes: {universes}, writing Chapter {next_chapter}")
    return ActionResult(needs_runner=True)
