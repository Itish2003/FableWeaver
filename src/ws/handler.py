import json
import re
from fastapi import WebSocket, WebSocketDisconnect

from src.app import manager
from src.config import make_session_id, get_session_service
from src.utils.logging_config import get_logger
from src.utils.legacy_logger import logger
from src.ws.context import WsSessionContext
from src.ws.actions import ACTION_DISPATCH, ActionResult
from src.ws.runner import run_pipeline

from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.errors.already_exists_error import AlreadyExistsError

_logger = get_logger("fable.ws.handler")

async def websocket_endpoint(websocket: WebSocket, story_id: str):
    """Clean WebSocket entry point using modular dispatch."""
    await manager.connect(websocket)
    _logger.info("WebSocket connected", extra={"story_id": story_id})

    # 1. Initialize Context
    agent_session_id = make_session_id(story_id)
    user_id = "user"

    ctx = WsSessionContext(
        websocket=websocket,
        story_id=story_id,
        user_id=user_id,
        agent_session_id=agent_session_id,
        session_service=get_session_service(),
        memory_service=InMemoryMemoryService(),
        artifact_service=InMemoryArtifactService()
    )

    # 2. Ensure ADK session exists
    try:
        await ctx.session_service.create_session(
            app_name="agents",
            user_id=user_id,
            session_id=agent_session_id
        )
    except AlreadyExistsError:
        pass

    try:
        from src.schemas.ws_messages import MAX_MESSAGE_BYTES, validate_ws_payload

        while True:
            data = await websocket.receive_text()
            ctx.action = "" # Reset per-turn state

            # Size validation
            if len(data.encode("utf-8", errors="replace")) > MAX_MESSAGE_BYTES:
                await manager.send_json({"type": "error", "code": "MESSAGE_TOO_LARGE",
                                       "message": f"Message exceeds {MAX_MESSAGE_BYTES // 1024}KB limit"}, websocket)
                continue

            try:
                payload = json.loads(data)
                action = payload.get("action")
                inner_data = payload.get("payload", {})
            except (json.JSONDecodeError, ValueError) as exc:
                await manager.send_json({"type": "error", "code": "INVALID_JSON",
                    "message": f"Malformed JSON: {exc}"}, websocket)
                continue

            if not isinstance(payload, dict):
                await manager.send_json({"type": "error", "code": "INVALID_FORMAT",
                    "message": "Expected a JSON object"}, websocket)
                continue

            # Slash-command routing for "choice"
            if action == "choice":
                choice_text = inner_data.get("choice", "").strip()
                if choice_text.startswith("/rewrite"):
                    action = "rewrite"
                    inner_data["instruction"] = choice_text[8:].strip()
                elif choice_text.startswith("/research"):
                    action = "research"
                    research_input = choice_text[9:].strip()
                    if research_input.lower().startswith("deep "):
                        inner_data["depth"] = "deep"
                        inner_data["query"] = research_input[5:].strip()
                    elif research_input.lower().startswith("quick "):
                        inner_data["depth"] = "quick"
                        inner_data["query"] = research_input[6:].strip()
                    else:
                        inner_data["depth"] = "quick"
                        inner_data["query"] = research_input
                elif choice_text.startswith("/enrich"):
                    action = "enrich"
                    focus_input = choice_text[7:].strip()
                    inner_data["focuses"] = [f.strip().lower() for f in focus_input.replace(",", " ").split() if f.strip()] if focus_input else ["all"]
                elif choice_text.startswith("/undo"): action = "undo"
                elif choice_text.startswith("/reset"): action = "reset"
                elif choice_text.startswith("/bible-diff"): action = "bible-diff"
                elif choice_text.startswith("/bible-snapshot"):
                    action = "bible-snapshot"
                    parts = choice_text[15:].strip().split(maxsplit=1)
                    inner_data["subcommand"] = parts[0] if parts else "list"
                    inner_data["snapshot_name"] = parts[1] if len(parts) > 1 else None

            # Validate payload
            ok, val_result = validate_ws_payload(action, inner_data)
            if not ok:
                await manager.send_json({"type": "error", "code": "INVALID_PAYLOAD", "message": val_result}, websocket)
                continue
            inner_data = val_result

            ctx.action = action
            handler = ACTION_DISPATCH.get(action)

            if not handler:
                await manager.send_json({"type": "error", "message": f"Unknown action: {action}"}, websocket)
                continue

            # Dispatch to handler
            result: ActionResult = await handler(ctx, inner_data)

            if result.needs_runner:
                await run_pipeline(ctx)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        _logger.info("WebSocket disconnected", extra={"story_id": story_id})
    except Exception as e:
        _logger.exception("Fatal error in WebSocket loop")
        try:
            await manager.send_json({"type": "error", "message": str(e)}, websocket)
        except: pass
