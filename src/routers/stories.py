"""Story CRUD, World Bible, export, and session-reset REST endpoints."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from typing import List

from src.database import get_db
from src.models import Story, History, WorldBible
from src.tools.core_tools import get_default_bible_content
from src.config import make_session_id, get_session_service
from src.utils.legacy_logger import logger

router = APIRouter()


class CreateStoryRequest(BaseModel):
    title: str = "Untitled Story"


class StoryResponse(BaseModel):
    id: str
    title: str
    updated_at: str


@router.post("/stories", response_model=StoryResponse)
async def create_story(request: CreateStoryRequest, db: AsyncSession = Depends(get_db)):
    story_id = str(uuid.uuid4())
    new_story = Story(id=story_id, title=request.title)
    db.add(new_story)

    # Initialize World Bible with default content
    default_content = await get_default_bible_content()
    bible = WorldBible(id=str(uuid.uuid4()), story_id=story_id, content=default_content)
    db.add(bible)

    await db.commit()
    await db.refresh(new_story)

    return {
        "id": new_story.id,
        "title": new_story.title,
        "updated_at": new_story.updated_at.isoformat()
    }


@router.get("/stories", response_model=List[StoryResponse])
async def list_stories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Story).order_by(desc(Story.updated_at)))
    stories = result.scalars().all()
    return [
        {
            "id": s.id,
            "title": s.title,
            "updated_at": s.updated_at.isoformat()
        }
        for s in stories
    ]


@router.get("/stories/{story_id}")
async def get_story_details(story_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Fetch history
    history_result = await db.execute(
        select(History).where(History.story_id == story_id).order_by(History.sequence)
    )
    history_items = history_result.scalars().all()

    history_data = []
    for h in history_items:
        history_data.append({
            "id": h.id,
            "text": h.text,
            "choices": h.choices,
            "summary": h.summary,
            "sequence": h.sequence
        })

    return {
        "id": story.id,
        "title": story.title,
        "history": history_data
    }


@router.delete("/stories/{story_id}")
async def delete_story(story_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    await db.delete(story)
    await db.commit()

    # Delete ADK session (cascade deletes events)
    adk_session_id = make_session_id(story_id)
    try:
        session_service = get_session_service()
        await session_service.delete_session(
            app_name="agents", user_id="user", session_id=adk_session_id
        )
        logger.log("info", f"Cleaned up ADK session and events for story {story_id}")
    except Exception as e:
        logger.log("error", f"Failed to delete ADK session for {story_id}: {e}")

    return {"status": "deleted"}


@router.delete("/stories/{story_id}/chapters/{chapter_id}")
async def delete_chapter(story_id: str, chapter_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a specific chapter from a story."""
    # Verify story exists
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Find and delete the chapter
    result = await db.execute(
        select(History).where(History.id == chapter_id, History.story_id == story_id)
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    deleted_sequence = chapter.sequence
    await db.delete(chapter)

    # Resequence remaining chapters
    remaining_result = await db.execute(
        select(History).where(
            History.story_id == story_id,
            History.sequence > deleted_sequence
        ).order_by(History.sequence)
    )
    remaining_chapters = remaining_result.scalars().all()
    for ch in remaining_chapters:
        ch.sequence = ch.sequence - 1

    await db.commit()

    logger.log("info", f"Deleted chapter {chapter_id} from story {story_id}")
    return {"status": "deleted", "chapter_id": chapter_id}


@router.get("/stories/{story_id}/bible")
async def get_world_bible(story_id: str, section: str = None, db: AsyncSession = Depends(get_db)):
    """
    Get the World Bible for a story.
    Optional 'section' query param to get specific section (e.g., 'power_origins', 'stakes_and_consequences')
    """
    result = await db.execute(select(WorldBible).where(WorldBible.story_id == story_id))
    bible = result.scalar_one_or_none()

    if not bible:
        raise HTTPException(status_code=404, detail="World Bible not found")

    if section:
        # Return specific section using dot notation
        data = bible.content
        for key in section.split('.'):
            if isinstance(data, dict) and key in data:
                data = data[key]
            else:
                raise HTTPException(status_code=404, detail=f"Section '{section}' not found")
        return {"section": section, "data": data}

    return {"story_id": story_id, "bible": bible.content}


@router.get("/stories/{story_id}/timeline-comparison")
async def get_timeline_comparison(story_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get a structured comparison of canon timeline vs story timeline.
    Returns events categorized by match status for UI rendering.
    """
    result = await db.execute(select(WorldBible).where(WorldBible.story_id == story_id))
    bible = result.scalar_one_or_none()

    if not bible:
        raise HTTPException(status_code=404, detail="World Bible not found")

    data = bible.content
    canon_events = data.get("canon_timeline", {}).get("events", [])
    story_events = data.get("story_timeline", {}).get("events", [])
    divergences = data.get("divergences", {}).get("list", [])
    current_date = data.get("meta", {}).get("current_story_date", "Unknown")

    # Categorize events
    comparison = {
        "current_date": current_date,
        "matched": [],
        "modified": [],
        "prevented": [],
        "upcoming": [],
        "unaddressed": [],
        "story_only": [],
        "stats": {
            "total_canon": 0,
            "matched": 0,
            "modified": 0,
            "prevented": 0,
            "upcoming": 0,
            "unaddressed": 0,
            "story_only": 0,
            "divergence_pct": 0.0
        }
    }

    # Track which story events match canon
    matched_story_events = set()

    for canon_event in canon_events:
        if canon_event.get("status") == "background":
            continue

        comparison["stats"]["total_canon"] += 1

        status = canon_event.get("status", "upcoming")
        event_entry = {
            "date": canon_event.get("date", "?"),
            "event": canon_event.get("event", "Unknown"),
            "importance": canon_event.get("importance", "minor"),
            "characters": canon_event.get("characters", []),
            "story_match": None,
            "match_score": None
        }

        if status == "prevented":
            comparison["prevented"].append(event_entry)
            comparison["stats"]["prevented"] += 1
        elif status == "modified":
            for i, se in enumerate(story_events):
                if any(c in se.get("participants", []) for c in canon_event.get("characters", [])):
                    event_entry["story_match"] = se.get("event", "?")
                    event_entry["story_date"] = se.get("date", "?")
                    matched_story_events.add(i)
                    break
            comparison["modified"].append(event_entry)
            comparison["stats"]["modified"] += 1
        elif status == "occurred":
            for i, se in enumerate(story_events):
                if any(c in se.get("participants", []) for c in canon_event.get("characters", [])):
                    event_entry["story_match"] = se.get("event", "?")
                    event_entry["story_date"] = se.get("date", "?")
                    matched_story_events.add(i)
                    break
            comparison["matched"].append(event_entry)
            comparison["stats"]["matched"] += 1
        elif status == "upcoming":
            comparison["upcoming"].append(event_entry)
            comparison["stats"]["upcoming"] += 1
        else:
            comparison["unaddressed"].append(event_entry)
            comparison["stats"]["unaddressed"] += 1

    # Find story-only events (not matching any canon event)
    for i, story_event in enumerate(story_events):
        if i not in matched_story_events:
            comparison["story_only"].append({
                "date": story_event.get("date", "?"),
                "event": story_event.get("event", "Unknown"),
                "participants": story_event.get("participants", []),
                "chapter": story_event.get("chapter", "?")
            })
            comparison["stats"]["story_only"] += 1

    # Calculate divergence percentage from actual divergences list
    severity_weights = {"critical": 4, "major": 3, "moderate": 2, "minor": 1}
    total_weight = 0
    for div in divergences:
        severity = div.get("severity", "minor")
        total_weight += severity_weights.get(severity, 1)

    if total_weight > 0:
        comparison["stats"]["divergence_pct"] = min(round(total_weight / 20 * 100, 1), 100.0)

    comparison["stats"]["divergence_count"] = len(divergences)
    comparison["stats"]["major_divergences"] = sum(1 for d in divergences if d.get("severity") in ("major", "critical"))
    comparison["divergences"] = divergences[-5:] if divergences else []

    return comparison


@router.patch("/stories/{story_id}/bible")
async def update_world_bible(story_id: str, updates: dict, db: AsyncSession = Depends(get_db)):
    """
    Update specific sections of the World Bible using dot notation.
    Example body: {"path": "character_sheet.cape_name", "value": "Infinity"}
    Or bulk updates: {"updates": [{"path": "...", "value": "..."}, ...]}
    """
    result = await db.execute(select(WorldBible).where(WorldBible.story_id == story_id))
    bible = result.scalar_one_or_none()

    if not bible:
        raise HTTPException(status_code=404, detail="World Bible not found")

    content = bible.content

    # Handle single update or bulk updates
    update_list = updates.get("updates", [updates]) if "updates" in updates else [updates]

    for update in update_list:
        path = update.get("path", "")
        value = update.get("value")

        if not path:
            continue

        # Navigate to the parent and set the value
        keys = path.split('.')
        target = content
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]

        target[keys[-1]] = value

    # Explicitly mark the JSON column as modified (SQLAlchemy doesn't detect nested dict mutations)
    flag_modified(bible, "content")
    await db.commit()

    return {"status": "updated", "story_id": story_id, "updated_paths": [u.get("path") for u in update_list]}


@router.post("/stories/{story_id}/reset-session")
async def reset_story_session(story_id: str, db: AsyncSession = Depends(get_db)):
    """
    Reset/clear the ADK session state for a story.
    Useful when session has corrupted events (parts=None errors).
    Does NOT delete story history or World Bible - only clears agent conversation state.
    """
    agent_session_id = make_session_id(story_id)
    session_service = get_session_service()

    # Delete the session (cascade deletes events), then recreate empty
    await session_service.delete_session(
        app_name="agents", user_id="user", session_id=agent_session_id
    )
    await session_service.create_session(
        app_name="agents", user_id="user", session_id=agent_session_id
    )

    logger.log("info", f"Reset session {agent_session_id}")
    return {"status": "reset", "story_id": story_id}


@router.get("/stories/{story_id}/export")
async def export_story(story_id: str, format: str = "markdown", db: AsyncSession = Depends(get_db)):
    """
    Export the full story as markdown or JSON.
    Includes all chapters and optionally the World Bible.
    """
    # Get story
    story_result = await db.execute(select(Story).where(Story.id == story_id))
    story = story_result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Get chapters
    history_result = await db.execute(
        select(History).where(History.story_id == story_id).order_by(History.sequence)
    )
    chapters = history_result.scalars().all()

    # Get World Bible
    bible_result = await db.execute(select(WorldBible).where(WorldBible.story_id == story_id))
    bible = bible_result.scalar_one_or_none()

    if format == "json":
        return {
            "story": {
                "id": story.id,
                "title": story.title,
                "created_at": story.created_at.isoformat() if story.created_at else None,
            },
            "chapters": [
                {
                    "sequence": ch.sequence,
                    "text": ch.text,
                    "summary": ch.summary,
                    "word_count": len(ch.text.split()) if ch.text else 0
                }
                for ch in chapters
            ],
            "world_bible": bible.content if bible else None
        }

    # Markdown format
    markdown = f"# {story.title}\n\n"
    markdown += f"*Exported from FableWeaver*\n\n---\n\n"

    total_words = 0
    for ch in chapters:
        word_count = len(ch.text.split()) if ch.text else 0
        total_words += word_count
        # Clean JSON from chapter text
        clean_text = ch.text or ""
        json_match = re.search(r'```json[\s\S]*?```', clean_text)
        if json_match:
            clean_text = clean_text[:json_match.start()].strip()

        markdown += f"{clean_text}\n\n---\n\n"

    markdown += f"\n## Story Statistics\n\n"
    markdown += f"- **Total Chapters:** {len(chapters)}\n"
    markdown += f"- **Total Words:** {total_words:,}\n"

    if bible and bible.content:
        content = bible.content

        # Protagonist Section
        char_sheet = content.get("character_sheet", {})
        markdown += f"\n## Protagonist\n\n"
        markdown += f"- **Name:** {char_sheet.get('name', 'Unknown')}\n"
        markdown += f"- **Cape Name:** {char_sheet.get('cape_name', 'Unknown')}\n"
        markdown += f"- **Archetype:** {char_sheet.get('archetype', 'Unknown')}\n"

        # Timeline Section
        timeline = content.get("story_timeline", {})
        if timeline:
            markdown += f"\n## Story Timeline\n\n"
            canon_events = timeline.get("canon_events", [])
            story_events = timeline.get("story_events", [])
            if canon_events:
                markdown += f"### Canon Events Referenced\n"
                for event in canon_events[:10]:
                    if isinstance(event, dict):
                        markdown += f"- {event.get('event', event.get('name', str(event)))}\n"
                    else:
                        markdown += f"- {event}\n"
                markdown += "\n"
            if story_events:
                markdown += f"### Story Events\n"
                for event in story_events[:10]:
                    if isinstance(event, dict):
                        markdown += f"- {event.get('event', event.get('description', str(event)))}\n"
                    else:
                        markdown += f"- {event}\n"
                markdown += "\n"

        # Divergences Section
        divergences = content.get("divergences", [])
        if divergences:
            markdown += f"\n## Timeline Divergences\n\n"
            for div in divergences[:10]:
                if isinstance(div, dict):
                    markdown += f"- {div.get('divergence', div.get('description', str(div)))}\n"
                else:
                    markdown += f"- {div}\n"
            if len(divergences) > 10:
                markdown += f"- ... and {len(divergences) - 10} more divergences\n"

        # Stakes Section
        stakes = content.get("stakes_and_consequences", {})
        if stakes:
            markdown += f"\n## Stakes & Consequences\n\n"
            costs = stakes.get("costs_paid", [])
            near_misses = stakes.get("near_misses", [])
            if costs:
                markdown += f"### Costs Paid\n"
                for cost in costs[:5]:
                    if isinstance(cost, dict):
                        markdown += f"- {cost.get('cost', cost.get('description', str(cost)))}\n"
                    else:
                        markdown += f"- {cost}\n"
                markdown += "\n"
            if near_misses:
                markdown += f"### Near Misses\n"
                for miss in near_misses[:5]:
                    if isinstance(miss, dict):
                        markdown += f"- {miss.get('what_almost_happened', miss.get('description', str(miss)))}\n"
                    else:
                        markdown += f"- {miss}\n"

        # Power Origins Section
        powers = content.get("power_origins", {})
        if powers and powers.get("sources"):
            markdown += f"\n## Power Origins\n\n"
            for name, power in list(powers.get("sources", {}).items())[:5]:
                origin = power.get("universe_origin", "Unknown")
                mastery = power.get("mastery_level", "Unknown")
                markdown += f"- **{name}** ({origin}) - Mastery: {mastery}\n"

    return {"format": "markdown", "content": markdown, "word_count": total_words, "chapter_count": len(chapters)}
