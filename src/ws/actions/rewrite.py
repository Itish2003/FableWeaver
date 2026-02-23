"""Handle the ``rewrite`` WebSocket action — delete last chapter and regenerate."""

from __future__ import annotations

import copy
import json

from sqlalchemy import select, desc
from sqlalchemy.orm.attributes import flag_modified

from src.database import AsyncSessionLocal
from src.models import History, WorldBible
from src.pipelines import build_game_pipeline, get_story_universes, reset_adk_session
from src.utils.legacy_logger import logger
from src.ws.context import WsSessionContext
from src.ws.actions import ActionResult


async def handle_rewrite(ctx: WsSessionContext, inner_data: dict) -> ActionResult:
    instruction = inner_data.get("instruction", "")

    # 1. Save the chapter context AND restore Bible state BEFORE deleting
    deleted_chapter_summary = ""
    deleted_chapter_text = ""
    deleted_chapter_sequence = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(History).where(History.story_id == ctx.story_id).order_by(desc(History.sequence)).limit(1)
        )
        last_history = result.scalar_one_or_none()
        if last_history:
            deleted_chapter_summary = last_history.summary or ""
            deleted_chapter_text = last_history.text or ""
            deleted_chapter_sequence = last_history.sequence or 1

            # Restore Bible to pre-chapter state
            if last_history.bible_snapshot:
                bible_result = await db.execute(
                    select(WorldBible).where(WorldBible.story_id == ctx.story_id).with_for_update()
                )
                bible = bible_result.scalar_one_or_none()
                if bible:
                    bible.content = copy.deepcopy(last_history.bible_snapshot)
                    flag_modified(bible, 'content')
                    logger.log("info", f"Rewrite: Restored Bible to pre-Chapter {deleted_chapter_sequence} state")

            await db.delete(last_history)
            await db.commit()
            logger.log("info", f"Deleted last history item {last_history.id} (Chapter {deleted_chapter_sequence}) for rewrite.")

    # 2. Clean up ADK session events
    await reset_adk_session(ctx.story_id)

    # 3. Fetch universes
    universes, deviation = await get_story_universes(ctx.story_id)

    # 4. Get PREVIOUS chapters for story arc context
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(History).where(
                History.story_id == ctx.story_id,
                History.sequence < deleted_chapter_sequence
            ).order_by(desc(History.sequence)).limit(3)
        )
        prev_chapters = result.scalars().all()

        prev_summaries = ""
        if prev_chapters:
            for ch in reversed(prev_chapters):
                if ch.summary:
                    prev_summaries += f"- **Ch.{ch.sequence}**: {ch.summary[:300]}{'...' if len(ch.summary) > 300 else ''}\n"

        bible_result = await db.execute(select(WorldBible).where(WorldBible.story_id == ctx.story_id))
        bible = bible_result.scalar_one_or_none()

        if bible and bible.content:
            ctx.bible_snapshot_content = copy.deepcopy(bible.content)

        rewrite_story_context = ""
        if bible and bible.content:
            meta = bible.content.get("meta", {})
            char_sheet = bible.content.get("character_sheet", {})
            rewrite_story_context = f"""
**STORY STATE (from World Bible):**
- Current Date: {meta.get('current_story_date', 'Unknown')}
- Protagonist: {char_sheet.get('name', 'Unknown')} ({char_sheet.get('cape_name', 'No cape name')})
- Status: {char_sheet.get('status', {}).get('condition', 'Normal') if isinstance(char_sheet.get('status'), dict) else 'Normal'}"""

    # 5. Switch to game pipeline
    ctx.active_agent = build_game_pipeline(ctx.story_id, universes=universes, deviation=deviation)

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

    # 6. Construct rewrite instruction
    ctx.input_text = f"""CRITICAL INSTRUCTION: REWRITE Chapter {deleted_chapter_sequence}.

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
                         STORY ARC CONTEXT (for continuity)
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

**PREVIOUS CHAPTER SUMMARIES:**
{prev_summaries if prev_summaries else "This is Chapter 1 - no previous chapters."}
{rewrite_story_context}
{bible_state_section}
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
                    ORIGINAL CHAPTER TO REWRITE (Chapter {deleted_chapter_sequence})
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

**ORIGINAL SUMMARY:**
{deleted_chapter_summary}

**ORIGINAL CONTENT (for reference - rewrite this, don't copy):**
{deleted_chapter_text[:3000]}{"..." if len(deleted_chapter_text) > 3000 else ""}

\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
                              REWRITE INSTRUCTIONS
\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

USER'S CHANGES: {instruction if instruction else "Improve the narrative quality and pacing."}

REQUIREMENTS:
- Rewrite the SAME chapter (Chapter {deleted_chapter_sequence}) with the user's requested changes
- Keep the same general plot beats and timeline position
- Maintain the same characters and setting from the original
- Apply the user's changes/corrections throughout
- Reference the World Bible state provided above for character details, canon facts, and setting information
- Use any research data in the World Bible (check world_state.knowledge_base)
- Output the full rewritten chapter with summary and choices

DO NOT write a different chapter. Rewrite THIS chapter with the requested modifications."""
    logger.log("pipeline", f"Enabled REWRITE (GAME) pipeline for story {ctx.story_id} - rewriting Chapter {deleted_chapter_sequence}")
    return ActionResult(needs_runner=True)
