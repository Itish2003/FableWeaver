"""Handle the ``bible-diff`` WebSocket action — show Archivist changes."""

from __future__ import annotations

from sqlalchemy import select, desc

from src.database import AsyncSessionLocal
from src.models import History, WorldBible
from src.app import manager
from src.utils.bible_helpers import compute_bible_diff
from src.ws.context import WsSessionContext
from src.ws.actions import ActionResult


async def handle_bible_diff(ctx: WsSessionContext, inner_data: dict) -> ActionResult:
    await manager.send_json({"type": "status", "status": "processing"}, ctx.websocket)
    try:
        async with AsyncSessionLocal() as db:
            # Get last chapter with its snapshot
            result = await db.execute(
                select(History).where(History.story_id == ctx.story_id).order_by(desc(History.sequence)).limit(1)
            )
            last_history = result.scalar_one_or_none()

            # Get current Bible
            bible_result = await db.execute(select(WorldBible).where(WorldBible.story_id == ctx.story_id))
            bible = bible_result.scalar_one_or_none()

            if not last_history or not last_history.bible_snapshot:
                await manager.send_json({
                    "type": "content_delta",
                    "text": "[System] No Bible snapshot available for comparison. Snapshots are created when new chapters are generated.\n",
                    "sender": "system"
                }, ctx.websocket)
            elif not bible or not bible.content:
                await manager.send_json({
                    "type": "content_delta",
                    "text": "[System] No World Bible found for this story.\n",
                    "sender": "system"
                }, ctx.websocket)
            else:
                # Compute diff between snapshot (before) and current (after)
                before = last_history.bible_snapshot
                after = bible.content
                diff_text = compute_bible_diff(before, after, last_history.sequence)

                await manager.send_json({
                    "type": "content_delta",
                    "text": diff_text,
                    "sender": "system"
                }, ctx.websocket)

    except Exception as e:
        await manager.send_json({"type": "error", "message": f"Bible diff failed: {e}"}, ctx.websocket)

    await manager.send_json({"type": "turn_complete"}, ctx.websocket)
    return ActionResult(needs_runner=False)
