"""Handle the ``reset`` WebSocket action — clear corrupted session state."""

from __future__ import annotations

from src.app import manager
from src.pipelines import reset_adk_session
from src.ws.context import WsSessionContext
from src.ws.actions import ActionResult


async def handle_reset(ctx: WsSessionContext, inner_data: dict) -> ActionResult:
    await manager.send_json({"type": "status", "status": "processing"}, ctx.websocket)
    try:
        await reset_adk_session(ctx.story_id)
        await manager.send_json({
            "type": "content_delta",
            "text": "[System] Session reset complete. Story history and World Bible preserved.\n",
            "sender": "system"
        }, ctx.websocket)
    except Exception as e:
        await manager.send_json({"type": "error", "message": f"Reset failed: {e}"}, ctx.websocket)

    await manager.send_json({"type": "turn_complete"}, ctx.websocket)
    return ActionResult(needs_runner=False)
