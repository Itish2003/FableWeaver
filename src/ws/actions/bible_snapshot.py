"""Handle the ``bible-snapshot`` WebSocket action — save/load/list/delete named snapshots."""

from __future__ import annotations

import copy

from sqlalchemy import select, desc
from sqlalchemy.orm.attributes import flag_modified

from src.database import AsyncSessionLocal
from src.models import History, WorldBible, BibleSnapshot
from src.app import manager
from src.ws.context import WsSessionContext
from src.ws.actions import ActionResult


async def handle_bible_snapshot(ctx: WsSessionContext, inner_data: dict) -> ActionResult:
    await manager.send_json({"type": "status", "status": "processing"}, ctx.websocket)
    subcommand = inner_data.get("subcommand", "list")
    snapshot_name = inner_data.get("snapshot_name")

    try:
        async with AsyncSessionLocal() as db:
            # Get current chapter number
            result = await db.execute(
                select(History).where(History.story_id == ctx.story_id).order_by(desc(History.sequence)).limit(1)
            )
            last_history = result.scalar_one_or_none()
            current_chapter = last_history.sequence if last_history else 0

            if subcommand == "save":
                if not snapshot_name:
                    await manager.send_json({
                        "type": "content_delta",
                        "text": "[System] Usage: /bible-snapshot save <name>\n",
                        "sender": "system"
                    }, ctx.websocket)
                else:
                    # Get current Bible content
                    bible_result = await db.execute(select(WorldBible).where(WorldBible.story_id == ctx.story_id))
                    bible = bible_result.scalar_one_or_none()
                    if not bible or not bible.content:
                        await manager.send_json({
                            "type": "content_delta",
                            "text": "[System] No World Bible found to snapshot.\n",
                            "sender": "system"
                        }, ctx.websocket)
                    else:
                        # Check if name already exists
                        existing = await db.execute(
                            select(BibleSnapshot).where(
                                BibleSnapshot.story_id == ctx.story_id,
                                BibleSnapshot.name == snapshot_name
                            )
                        )
                        if existing.scalar_one_or_none():
                            await manager.send_json({
                                "type": "content_delta",
                                "text": f"[System] Snapshot '{snapshot_name}' already exists. Use a different name.\n",
                                "sender": "system"
                            }, ctx.websocket)
                        else:
                            # Create snapshot
                            new_snapshot = BibleSnapshot(
                                story_id=ctx.story_id,
                                name=snapshot_name,
                                content=copy.deepcopy(bible.content),
                                chapter_number=current_chapter
                            )
                            db.add(new_snapshot)
                            await db.commit()
                            await manager.send_json({
                                "type": "content_delta",
                                "text": f"[System] \u2705 Snapshot '{snapshot_name}' saved at Chapter {current_chapter}.\n",
                                "sender": "system"
                            }, ctx.websocket)

            elif subcommand == "load":
                if not snapshot_name:
                    await manager.send_json({
                        "type": "content_delta",
                        "text": "[System] Usage: /bible-snapshot load <name>\n",
                        "sender": "system"
                    }, ctx.websocket)
                else:
                    # Find snapshot
                    snap_result = await db.execute(
                        select(BibleSnapshot).where(
                            BibleSnapshot.story_id == ctx.story_id,
                            BibleSnapshot.name == snapshot_name
                        )
                    )
                    snapshot = snap_result.scalar_one_or_none()
                    if not snapshot:
                        await manager.send_json({
                            "type": "content_delta",
                            "text": f"[System] Snapshot '{snapshot_name}' not found. Use /bible-snapshot list to see available snapshots.\n",
                            "sender": "system"
                        }, ctx.websocket)
                    else:
                        # Restore Bible to snapshot
                        bible_result = await db.execute(
                            select(WorldBible).where(WorldBible.story_id == ctx.story_id).with_for_update()
                        )
                        bible = bible_result.scalar_one_or_none()
                        if bible:
                            bible.content = copy.deepcopy(snapshot.content)
                            flag_modified(bible, 'content')
                            await db.commit()
                            await manager.send_json({
                                "type": "content_delta",
                                "text": f"[System] \u2705 World Bible restored to snapshot '{snapshot_name}' (from Chapter {snapshot.chapter_number}).\n",
                                "sender": "system"
                            }, ctx.websocket)
                        else:
                            await manager.send_json({
                                "type": "content_delta",
                                "text": "[System] No World Bible found to restore.\n",
                                "sender": "system"
                            }, ctx.websocket)

            elif subcommand == "list":
                # List all snapshots
                snap_result = await db.execute(
                    select(BibleSnapshot).where(BibleSnapshot.story_id == ctx.story_id).order_by(BibleSnapshot.created_at)
                )
                snapshots = snap_result.scalars().all()
                if not snapshots:
                    await manager.send_json({
                        "type": "content_delta",
                        "text": "[System] No saved snapshots. Use /bible-snapshot save <name> to create one.\n",
                        "sender": "system"
                    }, ctx.websocket)
                else:
                    lines = ["[System] **Saved Bible Snapshots:**\n"]
                    for snap in snapshots:
                        lines.append(f"  \u2022 **{snap.name}** (Chapter {snap.chapter_number}, {snap.created_at.strftime('%Y-%m-%d %H:%M')})\n")
                    lines.append("\nUse /bible-snapshot load <name> to restore.\n")
                    await manager.send_json({
                        "type": "content_delta",
                        "text": "".join(lines),
                        "sender": "system"
                    }, ctx.websocket)

            elif subcommand == "delete":
                if not snapshot_name:
                    await manager.send_json({
                        "type": "content_delta",
                        "text": "[System] Usage: /bible-snapshot delete <name>\n",
                        "sender": "system"
                    }, ctx.websocket)
                else:
                    snap_result = await db.execute(
                        select(BibleSnapshot).where(
                            BibleSnapshot.story_id == ctx.story_id,
                            BibleSnapshot.name == snapshot_name
                        )
                    )
                    snapshot = snap_result.scalar_one_or_none()
                    if not snapshot:
                        await manager.send_json({
                            "type": "content_delta",
                            "text": f"[System] Snapshot '{snapshot_name}' not found.\n",
                            "sender": "system"
                        }, ctx.websocket)
                    else:
                        await db.delete(snapshot)
                        await db.commit()
                        await manager.send_json({
                            "type": "content_delta",
                            "text": f"[System] \u2705 Snapshot '{snapshot_name}' deleted.\n",
                            "sender": "system"
                        }, ctx.websocket)
            else:
                await manager.send_json({
                    "type": "content_delta",
                    "text": f"[System] Unknown subcommand: {subcommand}. Use: save, load, list, or delete.\n",
                    "sender": "system"
                }, ctx.websocket)

    except Exception as e:
        await manager.send_json({"type": "error", "message": f"Bible snapshot failed: {e}"}, ctx.websocket)

    await manager.send_json({"type": "turn_complete"}, ctx.websocket)
    return ActionResult(needs_runner=False)
