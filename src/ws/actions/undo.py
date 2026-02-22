"""Handle the ``undo`` WebSocket action — remove last chapter + restore Bible."""

from __future__ import annotations

import copy

from sqlalchemy import select, desc
from sqlalchemy.orm.attributes import flag_modified

from src.database import AsyncSessionLocal
from src.models import History, WorldBible
from src.app import manager
from src.pipelines import reset_adk_session
from src.utils.legacy_logger import logger
from src.ws.context import WsSessionContext
from src.ws.actions import ActionResult


async def handle_undo(ctx: WsSessionContext, inner_data: dict) -> ActionResult:
    await manager.send_json({"type": "status", "status": "processing"}, ctx.websocket)
    try:
        async with AsyncSessionLocal() as db:
            # Find the last chapter to undo
            result = await db.execute(
                select(History).where(History.story_id == ctx.story_id).order_by(desc(History.sequence)).limit(1)
            )
            last_history = result.scalar_one_or_none()
            if last_history:
                chapter_id = last_history.id
                chapter_seq = last_history.sequence
                bible_restored = False

                # RESTORE BIBLE from snapshot (state BEFORE this chapter was generated)
                if last_history.bible_snapshot:
                    bible_result = await db.execute(
                        select(WorldBible).where(WorldBible.story_id == ctx.story_id).with_for_update()
                    )
                    bible = bible_result.scalar_one_or_none()
                    if bible:
                        bible.content = copy.deepcopy(last_history.bible_snapshot)
                        flag_modified(bible, 'content')
                        bible_restored = True
                        logger.log("info", f"Undo: Restored Bible to pre-Chapter {chapter_seq} state")

                # Delete the chapter
                await db.delete(last_history)
                await db.commit()
                logger.log("info", f"Undo: Deleted chapter {chapter_id} from story {ctx.story_id}")

                # Also clean up ADK session events for consistency
                await reset_adk_session(ctx.story_id)

                # Inform user
                bible_msg = " World Bible restored to previous state." if bible_restored else ""
                await manager.send_json({
                    "type": "content_delta",
                    "text": f"[System] Chapter {chapter_seq} undone successfully.{bible_msg}\n",
                    "sender": "system"
                }, ctx.websocket)
            else:
                await manager.send_json({
                    "type": "content_delta",
                    "text": "[System] No chapters to undo.\n",
                    "sender": "system"
                }, ctx.websocket)
    except Exception as e:
        await manager.send_json({"type": "error", "message": f"Undo failed: {e}"}, ctx.websocket)

    await manager.send_json({"type": "turn_complete"}, ctx.websocket)
    return ActionResult(needs_runner=False)
