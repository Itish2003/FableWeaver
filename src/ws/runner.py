"""Pipeline runner — executes the ADK agent pipeline and streams results."""

from __future__ import annotations

import asyncio
import json
import re
import uuid

from fastapi import WebSocketDisconnect
from google.adk.runners import Runner
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.genai import types
from sqlalchemy import select, desc

from src.app import manager
from src.config import get_settings
from src.database import AsyncSessionLocal
from src.models import History
from src.utils.bible_helpers import auto_update_bible_from_chapter, verify_bible_integrity
from src.utils.legacy_logger import logger
from src.utils.logging_config import get_logger
from src.ws.context import WsSessionContext

_logger = get_logger("fable.ws.runner")


async def run_pipeline(ctx: WsSessionContext) -> None:
    """Execute the active agent pipeline and stream results to the client.

    Called by the WebSocket handler when an action returns
    ``ActionResult(needs_runner=True)``.
    """
    settings = get_settings()

    # FRESH RUNNER for this action to ensure agent pipeline is picked up
    runner = Runner(
        agent=ctx.active_agent,
        app_name="agents",
        session_service=ctx.session_service,
        memory_service=ctx.memory_service,
        artifact_service=ctx.artifact_service,
        plugins=[ReflectAndRetryToolPlugin(max_retries=settings.tool_retry_max_attempts)],
    )

    # State seeded into the session via run_async(state_delta=...) so
    # callbacks can read story_id and pipeline type.
    _callback_state_delta = {
        "story_id": ctx.story_id,
        "_pipeline_type": "init" if ctx.action == "init" else "game",
    }

    # Run the Pipeline
    await manager.send_json({"type": "status", "status": "processing"}, ctx.websocket)

    buffer = ""
    ws_disconnected = False  # Track if client disconnected during streaming

    # Construct Content object
    user_msg = types.Content(parts=[types.Part(text=ctx.input_text)], role="user")

    logger.log("runner_start", f"Running agent: {runner.agent.name}", {"action": ctx.action, "story_id": ctx.story_id})
    _logger.debug("Starting runner for story=%s agent=%s", ctx.story_id, runner.agent.name)

    # Heartbeat task keeps the WebSocket alive during long generation
    pipeline_timed_out = False

    async def heartbeat():
        """Send periodic keepalive messages while the pipeline runs."""
        while True:
            await asyncio.sleep(settings.heartbeat_interval_seconds)
            if ws_disconnected:
                return
            try:
                await manager.send_json({
                    "type": "status",
                    "status": "processing",
                }, ctx.websocket)
            except WebSocketDisconnect:
                return

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        async with asyncio.timeout(settings.pipeline_timeout_seconds):
            async with runner:
                last_event_author = None
                async for event in runner.run_async(
                    user_id=ctx.user_id,
                    session_id=ctx.agent_session_id,
                    new_message=user_msg,
                    state_delta=_callback_state_delta,
                ):
                    # Only stream output from the Storyteller agent to the user
                    # Research agents (lore_hunter, lore_keeper, archivist) run silently
                    event_author = str(getattr(event, 'author', '') or '').lower()
                    is_storyteller = "storyteller" in event_author or "story_teller" in event_author or "narrator" in event_author

                    # Agent transition -> send WebSocket progress
                    if event_author and event_author != str(last_event_author or '').lower() and not ws_disconnected:
                        if last_event_author is not None:
                            try:
                                await manager.send_json({
                                    "type": "status",
                                    "status": "processing",
                                    "detail": f"{event_author} starting...",
                                }, ctx.websocket)
                            except WebSocketDisconnect:
                                ws_disconnected = True
                        last_event_author = event_author

                    # Log pipeline event flow
                    has_content = bool(getattr(event, 'content', None) or getattr(event, 'text', None))
                    _logger.debug(
                        "ADK event: author=%s has_content=%s turn_complete=%s",
                        event_author, has_content, getattr(event, 'turnComplete', False),
                    )

                    text_chunk = _extract_text_chunk(event)

                    if text_chunk:
                        # Only stream Storyteller output to user; accumulate all for logging
                        if is_storyteller:
                            buffer += text_chunk
                            logger.log("output_chunk", text_chunk)
                            try:
                                await manager.send_json({
                                    "type": "content_delta",
                                    "text": text_chunk,
                                    "sender": "storyteller"
                                }, ctx.websocket)
                            except WebSocketDisconnect:
                                # Client disconnected during streaming - continue to save chapter
                                logger.log("warning", "WebSocket disconnected during streaming, will still save chapter")
                                ws_disconnected = True
                        elif event_author == "archivist" or "archivist" in event_author.lower():
                            # ARCHIVIST STRUCTURED OUTPUT PROCESSING
                            logger.log("archivist_output", f"Received Archivist output: {text_chunk[:500]}...")
                            await _process_archivist_output(ctx.story_id, text_chunk, ctx.websocket)
                        elif event_author == "lore_keeper" or "lore_keeper" in event_author.lower():
                            # LORE KEEPER STRUCTURED OUTPUT PROCESSING
                            logger.log("lore_keeper_output", f"Received Lore Keeper output: {text_chunk[:500]}...")
                            await _process_lore_keeper_output(ctx.story_id, text_chunk, ctx.websocket)
                        else:
                            # Log research agent output for debugging but don't send to user
                            logger.log("research_output", f"[{event_author}] {text_chunk[:200]}...")

    except TimeoutError:
        pipeline_timed_out = True
        timeout_mins = settings.pipeline_timeout_seconds / 60
        logger.log("timeout", f"Pipeline timed out after {timeout_mins:.0f}m for story {ctx.story_id}", {"action": ctx.action})
        if not ws_disconnected:
            try:
                await manager.send_json({
                    "type": "error",
                    "message": f"Generation timed out after {timeout_mins:.0f} minutes. Any partial output has been saved. Please try again."
                }, ctx.websocket)
            except WebSocketDisconnect:
                ws_disconnected = True
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass

    # --- Post-generation processing ---
    logger.log("turn_end", f"Turn complete for story {ctx.story_id}")

    # Check for empty/failed output (skip if we already sent a timeout error)
    if not pipeline_timed_out and (not buffer or len(buffer.strip()) < 100):
        logger.log("warning", f"Storyteller produced minimal output ({len(buffer)} chars).", {"story_id": ctx.story_id, "action": ctx.action})
        if not buffer and not ws_disconnected:
            try:
                await manager.send_json({
                    "type": "content_delta",
                    "text": "\n\n\u26a0\ufe0f **Generation Issue**: The story agent did not produce narrative output. This may be due to context length or a timeout. Please try again or use /research first to populate the World Bible.\n",
                    "sender": "system"
                }, ctx.websocket)
            except WebSocketDisconnect:
                ws_disconnected = True

    # Extract structured JSON metadata from chapter output
    from src.utils.json_extractor import extract_chapter_json, validate_chapter_length

    parsed = extract_chapter_json(buffer)
    choices_json = parsed.get("choices") if parsed else None
    summary_text = parsed.get("summary") if parsed else None
    questions_json = parsed.get("questions") if parsed else None

    # Validate chapter word count (non-blocking warning)
    validation = validate_chapter_length(buffer, settings.chapter_min_words, settings.chapter_max_words)
    logger.log("chapter_length", validation.message, {
        "word_count": validation.word_count,
        "meets_minimum": validation.meets_minimum,
        "story_id": ctx.story_id,
    })

    if not validation.meets_minimum and not ws_disconnected:
        try:
            await manager.send_json({
                "type": "content_delta",
                "text": f"\n\n⚠️ **Chapter Length Note**: This chapter is {validation.word_count} words "
                        f"({settings.chapter_min_words}-{settings.chapter_max_words} target). "
                        f"You can regenerate for a fuller narrative using the Regenerate button.\n",
                "sender": "system"
            }, ctx.websocket)
        except WebSocketDisconnect:
            ws_disconnected = True

    # --- Truncation detection ---
    if buffer and len(buffer.strip()) > 2000 and parsed is None:
        logger.log("truncation_warning",
                    f"Possible output truncation: {len(buffer)} chars but no JSON metadata found. "
                    f"Tail: {buffer[-200:]}")
        if not ws_disconnected:
            try:
                await manager.send_json({
                    "type": "content_delta",
                    "text": "\n\n\u26a0\ufe0f **Note**: This chapter may have been cut short by a token limit. "
                            "Choices and summary could not be extracted. You can continue "
                            "the story by typing what happens next.\n",
                    "sender": "system"
                }, ctx.websocket)
            except WebSocketDisconnect:
                ws_disconnected = True

    # Save History Item (Story History)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(History).where(History.story_id == ctx.story_id).order_by(desc(History.sequence)).limit(1)
        )
        last_history = result.scalar_one_or_none()
        next_seq = (last_history.sequence + 1) if last_history else 1

        new_history = History(
            id=str(uuid.uuid4()),
            story_id=ctx.story_id,
            sequence=next_seq,
            text=buffer,
            summary=summary_text,
            choices=choices_json,
            bible_snapshot=ctx.bible_snapshot_content  # Bible state BEFORE this chapter (for undo)
        )
        db.add(new_history)
        await db.commit()

    # AUTO-UPDATE BIBLE: Apply chapter metadata to World Bible
    await auto_update_bible_from_chapter(ctx.story_id, buffer, next_seq)

    # VERIFY & AUTO-FIX: Check Bible integrity and fix any schema issues
    integrity_issues = await verify_bible_integrity(ctx.story_id)
    if integrity_issues:
        logger.log("bible_verification", f"Fixed {len(integrity_issues)} schema issues")

    logger.log("turn_end", f"Turn complete for story {ctx.story_id}")
    if not ws_disconnected:
        try:
            # Include questions in turn_complete for frontend to display
            turn_complete_msg = {"type": "turn_complete"}
            if questions_json:
                turn_complete_msg["questions"] = questions_json
            await manager.send_json(turn_complete_msg, ctx.websocket)
        except WebSocketDisconnect:
            ws_disconnected = True

    if ws_disconnected:
        manager.disconnect(ctx.websocket)
        _logger.info("WebSocket disconnected (chapter saved)", extra={"story_id": ctx.story_id})


def _extract_text_chunk(event) -> str:
    """Extract displayable text from an ADK event."""
    text_chunk = ""
    if hasattr(event, "text") and event.text:
        text_chunk = event.text
    else:
        content = getattr(event, 'content', None)
        if content:
            if isinstance(content, str):
                text_chunk = content
            elif hasattr(content, 'parts') and content.parts:
                for part in content.parts:
                    if hasattr(part, 'text') and part.text:
                        text_chunk += part.text
                    elif isinstance(part, str):
                        text_chunk += part
                    elif isinstance(part, dict) and 'text' in part:
                        text_chunk += part['text']
            elif hasattr(content, 'text') and content.text:
                text_chunk = content.text
            # Try model_dump for Pydantic models (GenAI types)
            elif hasattr(content, 'model_dump'):
                try:
                    dumped = content.model_dump()
                    if isinstance(dumped, dict) and 'parts' in dumped:
                        for part in dumped['parts']:
                            if isinstance(part, dict) and 'text' in part:
                                text_chunk += part['text']
                except Exception:
                    pass
            # Fallback to string but be more lenient
            if not text_chunk:
                s = str(content)
                if s and s != "None" and "parts=None" not in s and s.strip() != "role='model'":
                    if "text='" in s or 'text="' in s:
                        matches = re.findall(r"text=['\"]([^'\"]*)['\"]", s)
                        if matches:
                            text_chunk = "".join(matches)

    if not text_chunk:
        text_chunk = getattr(event, 'message', "")

    # Skip empty or technical-only responses
    if text_chunk and ("parts=None" in text_chunk or text_chunk.strip() == "role='model'"):
        text_chunk = ""

    if text_chunk:
        # Clean technical strings
        if isinstance(text_chunk, str) and text_chunk.startswith("parts=["):
            matches = re.findall(r'text="""([\s\S]*?)"""', text_chunk)
            if matches:
                text_chunk = "".join(matches)
            else:
                matches = re.findall(r"text='([\s\S]*?)'", text_chunk)
                if matches:
                    text_chunk = "".join(matches)

    return text_chunk


async def _process_archivist_output(story_id: str, text_chunk: str, websocket=None) -> None:
    """Parse and apply the Archivist's BibleDelta JSON output.

    If the Archivist set context_leakage_detected=True, a non-blocking alert
    is sent to the frontend via a ``context_leakage_alert`` WS message so the
    user can review and optionally roll back via the undo action.
    """
    try:
        from src.schemas import BibleDelta
        from src.utils.bible_delta_processor import apply_bible_delta

        delta_json = json.loads(text_chunk)
        delta = BibleDelta(**delta_json)

        # --- Context leakage detection (non-blocking) ---
        if delta.context_leakage_detected:
            _logger.warning(
                "context_leakage_detected | story_id=%s | details=%s",
                story_id,
                delta.context_leakage_details,
            )
            logger.log(
                "context_leakage",
                f"Archivist flagged context leakage for story {story_id}: {delta.context_leakage_details}",
            )
            if websocket is not None:
                try:
                    await manager.send_json({
                        "type": "context_leakage_alert",
                        "details": delta.context_leakage_details or "Cross-universe terminology detected in Bible update.",
                        "recoverable": True,
                        "hint": "The Archivist rewrote the affected fields. Use 'undo' if the correction looks wrong.",
                    }, websocket)
                except WebSocketDisconnect:
                    pass

        result = await apply_bible_delta(story_id, delta)
        if result["success"]:
            logger.log("archivist_applied", f"Applied {len(result['updates_applied'])} Bible updates: {result['updates_applied']}")
        else:
            logger.log("archivist_error", f"Failed to apply delta: {result['errors']}")
    except json.JSONDecodeError as e:
        logger.log("archivist_json_error", f"Failed to parse Archivist JSON: {e}")
    except Exception as e:
        logger.log("archivist_error", f"Error processing Archivist output: {e}")


async def _process_lore_keeper_output(story_id: str, text_chunk: str, websocket=None) -> None:
    """Parse and apply the Lore Keeper's LoreKeeperOutput JSON structured output.

    The Lore Keeper outputs structured data that is converted to WorldBible format.
    """
    try:
        from src.schemas import LoreKeeperOutput
        from src.utils.lore_keeper_processor import apply_lore_keeper_output

        output_json = json.loads(text_chunk)
        output = LoreKeeperOutput(**output_json)

        result = await apply_lore_keeper_output(story_id, output)
        if result["success"]:
            logger.log("lore_keeper_applied", f"Applied {len(result['updates_applied'])} Bible updates: {result['updates_applied']}")
        else:
            logger.log("lore_keeper_error", f"Failed to apply Lore Keeper output: {result['errors']}")
    except json.JSONDecodeError as e:
        logger.log("lore_keeper_json_error", f"Failed to parse Lore Keeper JSON: {e}")
    except Exception as e:
        logger.log("lore_keeper_error", f"Error processing Lore Keeper output: {e}")
