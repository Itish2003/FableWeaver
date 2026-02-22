"""Handle the ``research`` WebSocket action — manual /research trigger."""

from __future__ import annotations

from src.app import manager
from src.pipelines import get_story_universes
from src.tools.meta_tools import MetaTools
from src.utils.legacy_logger import logger
from src.ws.context import WsSessionContext
from src.ws.actions import ActionResult


async def handle_research(ctx: WsSessionContext, inner_data: dict) -> ActionResult:
    query = inner_data.get("query", "")
    depth = inner_data.get("depth", "quick")
    await manager.send_json({"type": "status", "status": "processing"}, ctx.websocket)

    # Notify user of research mode
    mode_indicator = "\U0001f50d **DEEP RESEARCH**" if depth == "deep" else "\U0001f50e **Quick Research**"
    await manager.send_json({
        "type": "content_delta",
        "text": f"\n{mode_indicator}: {query}\n",
        "sender": "system"
    }, ctx.websocket)

    try:
        # Get story universes for context in deep mode
        universes = None
        if depth == "deep":
            universes, _ = await get_story_universes(ctx.story_id)
            await manager.send_json({
                "type": "content_delta",
                "text": "Planning focused research topics...\n",
                "sender": "system"
            }, ctx.websocket)

        meta = MetaTools(ctx.story_id)
        result = await meta.trigger_research(query, depth=depth, universes=universes)
        await manager.send_json({
            "type": "content_delta",
            "text": f"\n--- [RESEARCH LOG: {query}]\n{result}\n-----------------------------\n\n",
            "sender": "system"
        }, ctx.websocket)
    except Exception as e:
        await manager.send_json({"type": "error", "message": f"Research failed: {e}"}, ctx.websocket)

    await manager.send_json({"type": "turn_complete"}, ctx.websocket)
    return ActionResult(needs_runner=False)
