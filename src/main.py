from dotenv import load_dotenv
from datetime import datetime
load_dotenv()

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import json
import traceback
import sys
import uuid
import re
import copy
from sqlalchemy import select, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from contextlib import asynccontextmanager

from src.database import get_db, AsyncSessionLocal
from src.models import Story, History, WorldBible, AdkSession, AdkEvent, BibleSnapshot
from src.tools.core_tools import get_default_bible_content
from src.config import make_session_id, get_settings

# --- Logger ---
class FileLogger:
    def __init__(self, filename="server.log"):
        self.filename = filename
    
    def log(self, type, message, metadata=None):
        log_entry = {
            "type": type,
            "message": message,
            "metadata": metadata
        }
        with open(self.filename, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

logger = FileLogger()

import google.genai
from src.utils.resilient_client import ResilientClient

# Store the original Client class before patching
OriginalClient = google.genai.Client

# Global patch
google.genai.Client = ResilientClient

from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.runners import InMemoryRunner, Runner
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from src.services.adk_service import FableSessionService
from google.genai import types

# Import our agents
from src.agents.research import create_lore_hunter_swarm, create_lore_keeper, plan_research_queries
from src.agents.narrative import create_storyteller, create_archivist
from src.tools.meta_tools import MetaTools


def compute_bible_diff(before: dict, after: dict, chapter_num: int) -> str:
    """
    Compute a human-readable diff between Bible snapshots.
    Shows what the Archivist changed during chapter generation.
    """
    lines = [f"[System] **World Bible Changes (Chapter {chapter_num}):**\n\n"]

    def diff_section(path: str, old_val, new_val, indent=0):
        """Recursively diff sections."""
        prefix = "  " * indent
        changes = []

        if old_val == new_val:
            return []

        if old_val is None and new_val is not None:
            changes.append(f"{prefix}**+ Added {path}**")
            if isinstance(new_val, str) and len(new_val) < 100:
                changes.append(f"{prefix}  → {new_val}")
            elif isinstance(new_val, list) and len(new_val) <= 3:
                changes.append(f"{prefix}  → {new_val}")
        elif old_val is not None and new_val is None:
            changes.append(f"{prefix}**- Removed {path}**")
        elif isinstance(old_val, dict) and isinstance(new_val, dict):
            all_keys = set(old_val.keys()) | set(new_val.keys())
            for key in all_keys:
                sub_path = f"{path}.{key}" if path else key
                sub_changes = diff_section(sub_path, old_val.get(key), new_val.get(key), indent)
                changes.extend(sub_changes)
        elif isinstance(old_val, list) and isinstance(new_val, list):
            if old_val != new_val:
                added = [x for x in new_val if x not in old_val]
                removed = [x for x in old_val if x not in new_val]
                if added:
                    changes.append(f"{prefix}**{path}** added: {added[:3]}{'...' if len(added) > 3 else ''}")
                if removed:
                    changes.append(f"{prefix}**{path}** removed: {removed[:3]}{'...' if len(removed) > 3 else ''}")
        else:
            # Simple value change
            old_str = str(old_val)[:50] if old_val else "(empty)"
            new_str = str(new_val)[:50] if new_val else "(empty)"
            if old_str != new_str:
                changes.append(f"{prefix}**{path}**: {old_str} → {new_str}")

        return changes

    # Key sections to diff
    sections_to_check = [
        'meta',
        'character_sheet',
        'stakes_and_consequences',
        'story_timeline',
        'divergences',
        'character_voices',
        'knowledge_boundaries',
        'power_origins'
    ]

    total_changes = []
    for section in sections_to_check:
        old_section = before.get(section)
        new_section = after.get(section)
        if old_section != new_section:
            changes = diff_section(section, old_section, new_section, indent=0)
            if changes:
                total_changes.extend(changes)

    if not total_changes:
        lines.append("No changes detected in World Bible.\n")
    else:
        lines.extend([f"{c}\n" for c in total_changes[:20]])  # Limit to 20 changes
        if len(total_changes) > 20:
            lines.append(f"... and {len(total_changes) - 20} more changes.\n")

    return "".join(lines)


def format_question_answers(answers: dict) -> str:
    """
    Format user's answers to clarifying questions for inclusion in the prompt.
    The answers dict has question indices as keys and answers as values.
    """
    if not answers:
        return ""

    lines = ["""
═══════════════════════════════════════════════════════════════════════════════
                     PLAYER'S CLARIFYING ANSWERS
═══════════════════════════════════════════════════════════════════════════════
**The player answered optional clarifying questions to help shape this chapter:**
"""]

    for idx, answer in sorted(answers.items(), key=lambda x: int(x[0])):
        lines.append(f"- **Q{int(idx)+1}:** {answer}")

    lines.append("""
**Use these answers to guide the tone, pacing, and direction of the chapter.**
""")

    return "\n".join(lines)


async def auto_update_bible_from_chapter(story_id: str, chapter_text: str, chapter_num: int):
    """
    Automatically apply chapter metadata to World Bible.
    This ensures core updates ALWAYS happen, regardless of Archivist LLM behavior.
    """
    import copy
    from sqlalchemy.orm.attributes import flag_modified

    # Extract JSON metadata from chapter text
    json_match = re.search(r'\{[\s\S]*"summary"[\s\S]*\}', chapter_text)
    if not json_match:
        return

    try:
        chapter_data = json.loads(json_match.group(0))
    except:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WorldBible).where(WorldBible.story_id == story_id).with_for_update()
        )
        bible = result.scalar_one_or_none()
        if not bible or not bible.content:
            return

        content = copy.deepcopy(bible.content)
        updates_made = []

        # 1. Update stakes_and_consequences
        stakes_tracking = chapter_data.get('stakes_tracking', {})
        if stakes_tracking:
            if 'stakes_and_consequences' not in content:
                content['stakes_and_consequences'] = {}
            stakes = content['stakes_and_consequences']

            # Add costs_paid (schema: {cost, severity, chapter})
            costs = stakes_tracking.get('costs_paid', [])
            if costs:
                if 'costs_paid' not in stakes:
                    stakes['costs_paid'] = []
                for cost in costs:
                    cost_entry = {
                        'cost': cost if isinstance(cost, str) else cost.get('cost', str(cost)),
                        'severity': 'medium',  # Default; Archivist can refine
                        'chapter': chapter_num
                    }
                    stakes['costs_paid'].append(cost_entry)
                updates_made.append(f"costs_paid: +{len(costs)}")

            # Add near_misses (schema: {what_almost_happened, saved_by, chapter})
            near_misses = stakes_tracking.get('near_misses', [])
            if near_misses:
                if 'near_misses' not in stakes:
                    stakes['near_misses'] = []
                for miss in near_misses:
                    miss_entry = {
                        'what_almost_happened': miss if isinstance(miss, str) else miss.get('what_almost_happened', str(miss)),
                        'saved_by': 'Unknown',  # Default; Archivist should refine
                        'chapter': chapter_num
                    }
                    stakes['near_misses'].append(miss_entry)
                updates_made.append(f"near_misses: +{len(near_misses)}")

            # Add consequences_triggered (schema: {action, predicted_consequence, due_by})
            consequences = stakes_tracking.get('consequences_triggered', [])
            if consequences:
                if 'pending_consequences' not in stakes:
                    stakes['pending_consequences'] = []
                for cons in consequences:
                    cons_text = cons if isinstance(cons, str) else str(cons)
                    stakes['pending_consequences'].append({
                        'action': f'Chapter {chapter_num} events',
                        'predicted_consequence': cons_text,
                        'due_by': f'Chapter {chapter_num + 2}'  # Default: 2 chapters ahead
                    })
                updates_made.append(f"consequences: +{len(consequences)}")

        # 2. Update timeline
        timeline_data = chapter_data.get('timeline', {})
        if timeline_data:
            # Update current story date
            end_date = timeline_data.get('chapter_end_date')
            if end_date:
                if 'meta' not in content:
                    content['meta'] = {}
                content['meta']['current_story_date'] = end_date
                updates_made.append(f"story_date: {end_date}")

            # Add to story_timeline
            if 'story_timeline' not in content:
                content['story_timeline'] = {'events': [], 'chapter_dates': []}

            # Compute chapter date string (used for both chapter_dates and events)
            start_date = timeline_data.get('chapter_start_date')
            date_str = None
            if start_date or end_date:
                # Combine start/end into single date string
                if start_date == end_date or not end_date:
                    date_str = start_date
                elif not start_date:
                    date_str = end_date
                else:
                    date_str = f"{start_date} - {end_date}"

                # Add chapter date entry (schema: {chapter, date})
                content['story_timeline']['chapter_dates'].append({
                    'chapter': chapter_num,
                    'date': date_str
                })

            # Add canon events addressed (include date from chapter timeline)
            canon_events = timeline_data.get('canon_events_addressed', [])
            if canon_events:
                for event in canon_events:
                    content['story_timeline']['events'].append({
                        'chapter': chapter_num,
                        'event': event if isinstance(event, str) else str(event),
                        'type': 'canon_addressed',
                        'date': date_str or content.get('meta', {}).get('current_story_date', 'Unknown')
                    })
                updates_made.append(f"canon_events: +{len(canon_events)}")

                # Update canon_timeline.current_position with latest date + recent events
                if 'canon_timeline' not in content:
                    content['canon_timeline'] = {}
                current_date = content.get('meta', {}).get('current_story_date', date_str or 'Unknown')
                recent_canon = ', '.join(canon_events[-2:]) if len(canon_events) <= 2 else ', '.join(canon_events[-2:])
                content['canon_timeline']['current_position'] = f"{current_date} - {recent_canon}"

            # Add divergences (schema: {id, chapter, what_changed, severity, status, canon_event, cause, ripple_effects, affected_canon_events})
            divergences = timeline_data.get('divergences_created', [])
            if divergences:
                if 'divergences' not in content:
                    content['divergences'] = {'list': [], 'stats': {'total': 0, 'major': 0, 'minor': 0}}
                if 'list' not in content['divergences']:
                    content['divergences']['list'] = []
                existing_count = len(content['divergences']['list'])
                for i, div in enumerate(divergences):
                    div_text = div if isinstance(div, str) else str(div)
                    # Skip placeholder divergences
                    if div_text.lower() in ('none', 'none significant', 'none significant this chapter', 'none this chapter'):
                        continue
                    content['divergences']['list'].append({
                        'id': f'div_{existing_count + i + 1:03d}',
                        'chapter': chapter_num,
                        'what_changed': div_text,
                        'severity': 'minor',  # Default; Archivist can refine
                        'status': 'active',
                        'canon_event': '',  # Archivist should fill
                        'cause': 'OC intervention',
                        'ripple_effects': [],
                        'affected_canon_events': []
                    })
                # Update stats
                div_list = content['divergences']['list']
                major_count = sum(1 for d in div_list if d.get('severity') in ('major', 'critical'))
                content['divergences']['stats'] = {
                    'total': len(div_list),
                    'major': major_count,
                    'minor': len(div_list) - major_count
                }
                updates_made.append(f"divergences: +{len(divergences)}")

        # 3. Track power usage
        power_debt = stakes_tracking.get('power_debt_incurred', {}) if stakes_tracking else {}
        if power_debt:
            if 'power_origins' not in content:
                content['power_origins'] = {}
            if 'usage_tracking' not in content['power_origins']:
                content['power_origins']['usage_tracking'] = {}
            for power, level in power_debt.items():
                content['power_origins']['usage_tracking'][power] = {
                    'last_chapter': chapter_num,
                    'strain_level': level if isinstance(level, str) else str(level)
                }
            updates_made.append(f"power_debt: {list(power_debt.keys())}")

        # Save updates
        if updates_made:
            bible.content = content
            flag_modified(bible, 'content')
            await db.commit()
            logger.log("auto_bible_update", f"Chapter {chapter_num} auto-updates: {', '.join(updates_made)}")

            # Sync to disk for debugging
            try:
                with open("src/world_bible.json", 'w') as f:
                    json.dump(content, f, indent=2)
            except Exception:
                pass


async def verify_bible_integrity(story_id: str) -> list[str]:
    """
    Verify Bible data integrity after chapter generation.
    Returns list of issues found. If issues found, auto-fixes them.
    """
    from src.utils.bible_validator import validate_bible_integrity, validate_and_fix_bible_entry
    import copy

    issues = []

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WorldBible).where(WorldBible.story_id == story_id).with_for_update()
        )
        bible = result.scalar_one_or_none()
        if not bible or not bible.content:
            return ["World Bible not found"]

        content = copy.deepcopy(bible.content)

        # Run integrity check
        issues = validate_bible_integrity(content)

        if issues:
            # Auto-fix by running validator on problematic sections
            sections_to_fix = set()
            for issue in issues:
                if "pending_consequences" in issue:
                    sections_to_fix.add("stakes_and_consequences.pending_consequences")
                elif "near_misses" in issue:
                    sections_to_fix.add("stakes_and_consequences.near_misses")
                elif "costs_paid" in issue:
                    sections_to_fix.add("stakes_and_consequences.costs_paid")
                elif "divergences" in issue:
                    sections_to_fix.add("divergences.list")
                elif "chapter_dates" in issue:
                    sections_to_fix.add("story_timeline.chapter_dates")

            # Apply fixes
            for section in sections_to_fix:
                parts = section.split('.')
                if len(parts) == 2:
                    parent, child = parts
                    if parent in content and child in content[parent]:
                        content[parent][child] = validate_and_fix_bible_entry(
                            section, content[parent][child]
                        )

            bible.content = content
            flag_modified(bible, 'content')
            await db.commit()
            logger.log("bible_integrity_fix", f"Auto-fixed {len(issues)} Bible integrity issues")

    return issues


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables exist
    from src.database import engine
    from src.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Shutdown logic

app = FastAPI(title="FableWeaver Engine", version="2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Connection Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_json(self, message: dict, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# --- Pipeline Builders ---

async def build_init_pipeline(story_id: str, universes: List[str], deviation: str = "", user_input: str = "") -> SequentialAgent:
    """
    Builds the initialization pipeline for a new story.

    This function is async because it first runs the Query Planner to dynamically
    generate research topics based on the user's input, including detecting
    crossover powers from other universes.
    """
    agents = []

    # 0. Query Planner - Analyze input to generate targeted research topics
    # This detects crossover powers (e.g., "Amon's powers from LOTM") and ensures
    # dedicated researchers are spawned for each power source.
    print(f"[Pipeline] Running Query Planner for story {story_id}...")
    research_topics = await plan_research_queries(universes, deviation, user_input)

    # 1. Research Swarm - Now uses dynamically generated topics from Query Planner
    agents.append(create_lore_hunter_swarm(specific_topics=research_topics))
    # 2. Lore Keeper (Permanently updates the Bible)
    agents.append(create_lore_keeper(story_id=story_id))
    # 3. Storyteller (Takes context, writes chapter + choices)
    agents.append(create_storyteller(story_id=story_id, universes=universes, deviation=deviation))

    return SequentialAgent(name="init_pipeline", sub_agents=agents)

async def get_story_universes(story_id: str) -> tuple[List[str], str]:
    """Retrieve universes and deviation from the World Bible meta section."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(WorldBible).where(WorldBible.story_id == story_id))
        bible = result.scalar_one_or_none()
        if bible and bible.content:
            meta = bible.content.get("meta", {})
            universes = meta.get("universes", ["General"])
            deviation = meta.get("timeline_deviation", "")
            return universes, deviation
    return ["General"], ""


def build_game_pipeline(story_id: str, universes: List[str] = None, deviation: str = "") -> SequentialAgent:
    agents = []

    # 1. Archivist (Updates Bible based on previous turn)
    agents.append(create_archivist(story_id=story_id))

    # 2. Storyteller (Checks research, Writes chapter + choices)
    # Pass universes for context if available
    agents.append(create_storyteller(story_id=story_id, universes=universes, deviation=deviation))

    return SequentialAgent(name="game_pipeline", sub_agents=agents)


# --- REST Endpoints for Story Management ---

class CreateStoryRequest(BaseModel):
    title: str = "Untitled Story"
    # Future: allow passing universe/genre overrides here

class StoryResponse(BaseModel):
    id: str
    title: str
    updated_at: str

@app.post("/stories", response_model=StoryResponse)
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

@app.get("/stories", response_model=List[StoryResponse])
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

@app.get("/stories/{story_id}")
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
            "id": h.id, # This is a unique string ID
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

@app.delete("/stories/{story_id}")
async def delete_story(story_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    await db.delete(story)
    await db.commit()

    # Delete ADK Sessions and Events (application-level cascade)
    adk_session_id = make_session_id(story_id)
    try:
        # Delete events first (they reference sessions)
        await db.execute(delete(AdkEvent).where(AdkEvent.adk_session_id == adk_session_id))
        # Then delete the session
        await db.execute(delete(AdkSession).where(AdkSession.adk_session_id == adk_session_id))
        await db.commit()
        logger.log("info", f"Cleaned up ADK session and events for story {story_id}")
    except Exception as e:
        logger.log("error", f"Failed to delete ADK session for {story_id}: {e}")

    return {"status": "deleted"}


@app.delete("/stories/{story_id}/chapters/{chapter_id}")
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


@app.get("/stories/{story_id}/bible")
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


@app.get("/stories/{story_id}/timeline-comparison")
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
        "matched": [],      # Canon events that occurred as expected
        "modified": [],     # Canon events that happened differently
        "prevented": [],    # Canon events that were stopped
        "upcoming": [],     # Canon events not yet reached
        "unaddressed": [],  # Canon events that should have happened but didn't
        "story_only": [],   # Events that only exist in story (not in canon)
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
            # Find matching story event
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
    # Weight: critical=4, major=3, moderate=2, minor=1
    severity_weights = {"critical": 4, "major": 3, "moderate": 2, "minor": 1}
    total_weight = 0
    for div in divergences:
        severity = div.get("severity", "minor")
        total_weight += severity_weights.get(severity, 1)

    # Calculate as percentage (cap at 100%)
    # Base: 20 weight points = 100% divergence (e.g., 5 major divergences or 20 minor ones)
    if total_weight > 0:
        comparison["stats"]["divergence_pct"] = min(round(total_weight / 20 * 100, 1), 100.0)

    # Also add divergence counts to stats
    comparison["stats"]["divergence_count"] = len(divergences)
    comparison["stats"]["major_divergences"] = sum(1 for d in divergences if d.get("severity") in ("major", "critical"))

    # Add recent divergences
    comparison["divergences"] = divergences[-5:] if divergences else []

    return comparison


@app.patch("/stories/{story_id}/bible")
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


@app.post("/stories/{story_id}/reset-session")
async def reset_story_session(story_id: str, db: AsyncSession = Depends(get_db)):
    """
    Reset/clear the ADK session state for a story.
    Useful when session has corrupted events (parts=None errors).
    Does NOT delete story history or World Bible - only clears agent conversation state.
    """
    agent_session_id = make_session_id(story_id)

    # Delete all events for this session
    result = await db.execute(
        select(AdkEvent).where(AdkEvent.adk_session_id == agent_session_id)
    )
    events = result.scalars().all()
    event_count = len(events)

    for event in events:
        await db.delete(event)

    # Also clear the session record if it exists
    session_result = await db.execute(
        select(AdkSession).where(AdkSession.adk_session_id == agent_session_id)
    )
    session = session_result.scalar_one_or_none()
    if session:
        await db.delete(session)

    await db.commit()

    logger.log("info", f"Reset session {agent_session_id}: deleted {event_count} events")
    return {"status": "reset", "story_id": story_id, "events_deleted": event_count}


@app.get("/stories/{story_id}/export")
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
                for event in canon_events[:10]:  # Limit to 10
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


# --- Branching Endpoints ---

@app.post("/stories/{story_id}/branch")
async def create_branch(story_id: str, branch_name: str = "New Branch", db: AsyncSession = Depends(get_db)):
    """
    Create a new branch from the current state of a story.
    Copies all history and World Bible to a new story.
    """
    import copy

    # Get the source story
    result = await db.execute(select(Story).where(Story.id == story_id))
    source_story = result.scalar_one_or_none()
    if not source_story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Get source history
    history_result = await db.execute(
        select(History).where(History.story_id == story_id).order_by(History.sequence)
    )
    source_chapters = history_result.scalars().all()

    # Get source World Bible
    bible_result = await db.execute(select(WorldBible).where(WorldBible.story_id == story_id))
    source_bible = bible_result.scalar_one_or_none()

    # Create new branch story
    branch_id = str(uuid.uuid4())
    branch_story = Story(
        id=branch_id,
        title=f"{source_story.title} [{branch_name}]",
        parent_story_id=story_id,
        branch_name=branch_name,
        branch_point_chapter=len(source_chapters)
    )
    db.add(branch_story)

    # Copy history items
    for ch in source_chapters:
        new_chapter = History(
            id=str(uuid.uuid4()),
            story_id=branch_id,
            sequence=ch.sequence,
            text=ch.text,
            summary=ch.summary,
            choices=ch.choices,
            bible_snapshot=copy.deepcopy(ch.bible_snapshot) if ch.bible_snapshot else None
        )
        db.add(new_chapter)

    # Copy World Bible
    if source_bible:
        new_bible = WorldBible(
            id=str(uuid.uuid4()),
            story_id=branch_id,
            content=copy.deepcopy(source_bible.content) if source_bible.content else {}
        )
        db.add(new_bible)

    await db.commit()

    return {
        "status": "created",
        "branch_id": branch_id,
        "branch_name": branch_name,
        "parent_story_id": story_id,
        "chapters_copied": len(source_chapters)
    }


@app.get("/stories/{story_id}/branches")
async def list_branches(story_id: str, db: AsyncSession = Depends(get_db)):
    """
    List all branches of a story (including the story's own branch info).
    """
    # Get the story
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Get all branches (stories with this as parent)
    branches_result = await db.execute(
        select(Story).where(Story.parent_story_id == story_id)
    )
    branches = branches_result.scalars().all()

    # Get chapter count for main story
    history_result = await db.execute(
        select(History).where(History.story_id == story_id)
    )
    main_chapters = len(history_result.scalars().all())

    return {
        "story_id": story_id,
        "title": story.title,
        "is_branch": story.parent_story_id is not None,
        "parent_story_id": story.parent_story_id,
        "branch_name": story.branch_name,
        "chapter_count": main_chapters,
        "branches": [
            {
                "id": b.id,
                "name": b.branch_name,
                "title": b.title,
                "branch_point_chapter": b.branch_point_chapter,
                "created_at": b.created_at.isoformat() if b.created_at else None
            }
            for b in branches
        ]
    }


@app.get("/stories/{story_id}/family-tree")
async def get_story_family_tree(story_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get the full family tree of a story - parent, siblings, and children.
    """
    # Get the story
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Find the root story (original, no parent)
    root_id = story_id
    if story.parent_story_id:
        # Walk up to find root
        current = story
        while current.parent_story_id:
            parent_result = await db.execute(select(Story).where(Story.id == current.parent_story_id))
            parent = parent_result.scalar_one_or_none()
            if parent:
                current = parent
                root_id = current.id
            else:
                break

    # Get all stories in the family (all descendants of root)
    async def get_descendants(parent_id):
        result = await db.execute(select(Story).where(Story.parent_story_id == parent_id))
        children = result.scalars().all()
        tree = []
        for child in children:
            tree.append({
                "id": child.id,
                "title": child.title,
                "branch_name": child.branch_name,
                "branch_point_chapter": child.branch_point_chapter,
                "children": await get_descendants(child.id)
            })
        return tree

    # Get root story info
    root_result = await db.execute(select(Story).where(Story.id == root_id))
    root = root_result.scalar_one_or_none()

    return {
        "root": {
            "id": root.id,
            "title": root.title,
            "children": await get_descendants(root.id)
        },
        "current_story_id": story_id
    }


async def delete_last_events_from_session(session_service: FableSessionService, story_id: str, count: int = 1, clear_all: bool = False):
    """Delete events from an ADK session (for undo/rewrite functionality).

    Args:
        clear_all: If True, deletes ALL events in the session (needed for rewrite to avoid orphaned tool calls)
    """
    agent_session_id = make_session_id(story_id)
    async with AsyncSessionLocal() as db:
        if clear_all:
            # Delete ALL events - needed for rewrite to avoid conversation corruption
            result = await db.execute(
                select(AdkEvent).where(AdkEvent.adk_session_id == agent_session_id)
            )
            events_to_delete = result.scalars().all()
        else:
            # Get the last events (for undo)
            result = await db.execute(
                select(AdkEvent).where(
                    AdkEvent.adk_session_id == agent_session_id
                ).order_by(desc(AdkEvent.timestamp)).limit(count * 2)
            )
            events_to_delete = result.scalars().all()

        for event in events_to_delete:
            await db.delete(event)

        await db.commit()
        logger.log("info", f"Deleted {len(events_to_delete)} events from session {agent_session_id}")


# --- WebSocket Endpoint ---

@app.websocket("/ws/{story_id}")
async def websocket_endpoint(websocket: WebSocket, story_id: str):
    await manager.connect(websocket)
    print(f"New WebSocket connection for story: {story_id}")
    
    # 1. Verify Story Exists
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Story).where(Story.id == story_id))
        story = result.scalar_one_or_none()
        if not story:
             await manager.send_json({"type": "error", "message": "Story not found"}, websocket)
             await websocket.close()
             return

    # Session Management (ADK needs a session ID)
    agent_session_id = make_session_id(story_id) 
    user_id = "user"
    
    # Build Agent (Storyteller) - model configured via settings
    storyteller = create_storyteller(story_id, universes=None, deviation="")
    
    # Initial agent
    active_agent = storyteller
    
    # Services are persistent for the connection
    session_service = FableSessionService()
    memory_service = InMemoryMemoryService()
    artifact_service = InMemoryArtifactService()
    
    # Ensure session exists (FableSessionService handles creation/retrieval)
    try:
        await session_service.create_session(
            app_name="agents",
            user_id=user_id,
            session_id=agent_session_id
        )
    except Exception as e:
        pass
    
    try:
        while True:
            # CONTINUE GAME
            # Wait for next user action
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            action = payload.get("action")
            inner_data = payload.get("payload", {})
            
            logger.log("input", f"Action: {action} (Story: {story_id})", payload)
            print(f"Received action: {action} for Story: {story_id}")
            print(f"DEBUG: Inner data: {inner_data}")
            
            pipeline = None
            input_text = ""
            bible_snapshot_content = None  # Bible state before Archivist modifies it (for undo)

            # Check for Chat Commands (e.g., /rewrite, /undo) within "choice" action
            if action == "choice":
                 choice_text = inner_data.get("choice", "").strip()
                 if choice_text.startswith("/rewrite"):
                     action = "rewrite"
                     # Extract instruction: "/rewrite fix this" -> "fix this"
                     inner_data["instruction"] = choice_text[8:].strip()
                 elif choice_text.startswith("/research"):
                     action = "research"
                     # Extract query and depth: "/research deep query" or "/research quick query" or "/research query"
                     research_input = choice_text[9:].strip()

                     # Check for depth modifier
                     if research_input.lower().startswith("deep "):
                         inner_data["depth"] = "deep"
                         inner_data["query"] = research_input[5:].strip()
                     elif research_input.lower().startswith("quick "):
                         inner_data["depth"] = "quick"
                         inner_data["query"] = research_input[6:].strip()
                     else:
                         # Default to quick if no modifier
                         inner_data["depth"] = "quick"
                         inner_data["query"] = research_input
                 elif choice_text.startswith("/enrich"):
                     action = "enrich"
                     # Multiple focus areas: "/enrich locations relations events" or just "/enrich"
                     focus_input = choice_text[7:].strip()
                     if focus_input:
                         # Parse multiple focus areas (space or comma separated)
                         inner_data["focuses"] = [f.strip().lower() for f in focus_input.replace(",", " ").split() if f.strip()]
                     else:
                         inner_data["focuses"] = ["all"]
                 elif choice_text.startswith("/undo"):
                     action = "undo"
                 elif choice_text.startswith("/reset"):
                     action = "reset"  # Reset session state
                 elif choice_text.startswith("/bible-diff"):
                     action = "bible-diff"  # Show Archivist changes since last chapter
                 elif choice_text.startswith("/bible-snapshot"):
                     # Parse subcommand: /bible-snapshot save <name> OR /bible-snapshot load <name> OR /bible-snapshot list
                     parts = choice_text[15:].strip().split(maxsplit=1)
                     action = "bible-snapshot"
                     inner_data["subcommand"] = parts[0] if parts else "list"
                     inner_data["snapshot_name"] = parts[1] if len(parts) > 1 else None
            
            if action == "init":
                # START NEW STORY PHASE
                universes = inner_data.get("universes", ["General"])
                deviation = inner_data.get("timeline_deviation", "")

                print(f"DEBUG: Universes for story {story_id}: {universes}")

                # Store universes in World Bible meta for later retrieval
                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(WorldBible).where(WorldBible.story_id == story_id))
                    bible = result.scalar_one_or_none()
                    if bible:
                        if not bible.content:
                            bible.content = {}
                        if "meta" not in bible.content:
                            bible.content["meta"] = {}
                        bible.content["meta"]["universes"] = universes
                        bible.content["meta"]["timeline_deviation"] = deviation
                        bible.content["meta"]["genre"] = inner_data.get("genre", "Fantasy")
                        bible.content["meta"]["theme"] = inner_data.get("theme", "Mystery")
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(bible, "content")
                        await db.commit()

                # FIX: Extract user_input BEFORE building pipeline so Query Planner can use it
                user_req = inner_data.get("user_input", "")

                # Dynamically switch to init pipeline (now async with Query Planner)
                active_agent = await build_init_pipeline(story_id, universes, deviation, user_req)
                genre = inner_data.get("genre", "Fantasy")
                theme = inner_data.get("theme", "Mystery")

                # IMPORTANT: Do NOT include "Start the story" here - it confuses research agents
                # The Storyteller knows to write after research completes based on its own instruction
                input_text = f"""PHASE: INITIALIZATION
GENRE: {genre}
THEME: {theme}

═══════════════════════════════════════════════════════════════════════════════
                         OC/SI DESCRIPTION (CRITICAL)
═══════════════════════════════════════════════════════════════════════════════
{deviation}

**IMPORTANT FOR LORE HUNTERS:**
If the OC has powers from a CHARACTER (e.g., "Gojo's powers", "Taylor's abilities"),
you MUST research that character's power system, techniques, limitations, and how they used them.
This is ESSENTIAL even if the power source is from a different universe than the story setting.
═══════════════════════════════════════════════════════════════════════════════

RESEARCH FOCUS: {user_req if user_req else "Research the specified universes AND any power sources mentioned in the OC description."}

INSTRUCTIONS FOR RESEARCH AGENTS:
- Lore Hunters: Search for canonical information about the universes AND any crossover power sources. DO NOT write narrative.
- Lore Keeper: Consolidate research into the World Bible, including power_origins data. DO NOT write narrative.
- Storyteller: After research is complete, write the first chapter.

Each agent should perform ONLY their designated role."""

                logger.log("pipeline", f"Enabled INIT pipeline for story {story_id}")
                
            elif action == "choice":
                # CONTINUE GAME PHASE
                choice_text = inner_data.get("choice", "")
                question_answers = inner_data.get("question_answers", {})  # User's answers to clarifying questions
                # Fetch universes from World Bible for context continuity
                universes, deviation = await get_story_universes(story_id)

                # AUTO-RESEARCH DETECTION: Check if choice contains research requests
                # Patterns: "Research on...", "research about...", "Research:...", "do research on...", etc.
                # Now supports MULTIPLE research requests in parallel
                # Terminator pattern: stops at sentence end, character names, or other action phrases
                terminator = r'(?:\.|\!|\?|\s+Lucian|\s+Also|\s+Explore|\s+and\s+keep|\s+Then\s+|,\s+and\s+|$)'
                research_patterns = [
                    # "research on [topic]", "do research on [topic]", "do some research on [topic]"
                    rf'[Dd]o\s+(?:some\s+)?[Rr]esearch\s+on\s+(.+?){terminator}',
                    rf'[Rr]esearch\s+on\s+(.+?){terminator}',
                    # "research about [topic]"
                    rf'[Rr]esearch\s+about\s+(.+?){terminator}',
                    # "research for [topic]" - NEW: common phrasing
                    rf'[Dd]o\s+(?:some\s+)?[Rr]esearch\s+for\s+(.+?){terminator}',
                    rf'[Rr]esearch\s+for\s+(.+?){terminator}',
                    # "research: [topic]"
                    rf'[Rr]esearch:\s*(.+?){terminator}',
                    # "research how [topic]"
                    rf'[Rr]esearch\s+how\s+(.+?){terminator}',
                    # "research the [topic]" - NEW: direct article
                    rf'[Rr]esearch\s+the\s+(.+?){terminator}',
                    # "research [topic]" - NEW: direct object (catches "research character relationships")
                    rf'[Rr]esearch\s+([a-zA-Z][a-zA-Z\s\']+(?:relations?|interactions?|history|background|details?|info(?:rmation)?|abilities|powers?))',
                    # "look up [topic]", "look into [topic]" - NEW: synonyms
                    rf'[Ll]ook\s+(?:up|into)\s+(.+?){terminator}',
                    # "find out about [topic]" - NEW: synonym
                    rf'[Ff]ind\s+out\s+(?:about|more about)\s+(.+?){terminator}',
                ]

                # Collect ALL research queries from the choice text
                research_queries = []
                for pattern in research_patterns:
                    matches = re.findall(pattern, choice_text, re.IGNORECASE | re.DOTALL)
                    for match in matches:
                        query = match.strip()
                        # Clean up the query - remove trailing conjunctions and punctuation
                        query = re.sub(r'\s+(And|and|Also|also)\s*$', '', query)
                        query = query.rstrip('.,;')
                        if query and query not in research_queries:  # Avoid duplicates
                            research_queries.append(query)

                # If research detected, run ALL queries in PARALLEL before the chapter
                if research_queries:
                    logger.log("info", f"Auto-detected {len(research_queries)} research request(s): {research_queries}")
                    await manager.send_json({
                        "type": "content_delta",
                        "text": f"🔍 **Auto-Research Detected:** Found {len(research_queries)} research request(s). Running in parallel...\n",
                        "sender": "system"
                    }, websocket)

                    for q in research_queries:
                        await manager.send_json({
                            "type": "content_delta",
                            "text": f"  • {q}\n",
                            "sender": "system"
                        }, websocket)

                    await manager.send_json({
                        "type": "content_delta",
                        "text": f"\n",
                        "sender": "system"
                    }, websocket)

                    # Run all research queries in parallel
                    async def run_single_research(query: str):
                        try:
                            meta = MetaTools(story_id)
                            result = await meta.trigger_research(query)
                            return (query, True, result)
                        except Exception as e:
                            return (query, False, str(e))

                    # Execute all research in parallel
                    import asyncio
                    results = await asyncio.gather(*[run_single_research(q) for q in research_queries])

                    # Report results
                    success_count = sum(1 for _, success, _ in results if success)
                    for query, success, result in results:
                        if success:
                            logger.log("info", f"Auto-research completed for: '{query}'")
                        else:
                            logger.log("warning", f"Auto-research failed for '{query}': {result}")

                    await manager.send_json({
                        "type": "content_delta",
                        "text": f"✅ **Research Complete:** {success_count}/{len(research_queries)} queries successful. World Bible updated.\n\n---\n\n",
                        "sender": "system"
                    }, websocket)

                # Get current chapter count AND recent summaries for context
                async with AsyncSessionLocal() as db:
                    # Get last 3 chapters for context
                    result = await db.execute(
                        select(History).where(History.story_id == story_id).order_by(desc(History.sequence)).limit(3)
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

                    # Get last chapter's full summary for immediate context
                    last_summary = recent_chapters[0].summary if recent_chapters and recent_chapters[0].summary else "No previous chapter."

                    # Extract last chapter's JSON metadata for Archivist
                    last_chapter_metadata = ""
                    if recent_chapters and recent_chapters[0].text:
                        last_text = recent_chapters[0].text
                        json_match = re.search(r'\{[\s\S]*"summary"[\s\S]*\}', last_text)
                        if json_match:
                            try:
                                chapter_data = json.loads(json_match.group(0))
                                # Extract key metadata for Archivist
                                metadata_parts = []
                                if chapter_data.get('stakes_tracking'):
                                    metadata_parts.append(f"**Stakes Tracking:**\n```json\n{json.dumps(chapter_data['stakes_tracking'], indent=2)}\n```")
                                if chapter_data.get('timeline'):
                                    metadata_parts.append(f"**Timeline:**\n```json\n{json.dumps(chapter_data['timeline'], indent=2)}\n```")
                                if chapter_data.get('character_voices_used'):
                                    metadata_parts.append(f"**Characters Featured:** {', '.join(v.split('(')[0].strip() for v in chapter_data['character_voices_used'][:5])}")
                                if metadata_parts:
                                    last_chapter_metadata = "\n\n".join(metadata_parts)
                            except:
                                pass

                    # Get key World Bible facts for inline context
                    bible_result = await db.execute(select(WorldBible).where(WorldBible.story_id == story_id))
                    bible = bible_result.scalar_one_or_none()

                    # Capture Bible snapshot BEFORE Archivist modifies it (for undo rollback)
                    if bible and bible.content:
                        bible_snapshot_content = copy.deepcopy(bible.content)

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
                active_agent = build_game_pipeline(story_id, universes=universes, deviation=deviation)
                # Build chapter metadata section for Archivist
                metadata_section = ""
                if last_chapter_metadata:
                    metadata_section = f"""
═══════════════════════════════════════════════════════════════════════════════
                    LAST CHAPTER METADATA (FOR ARCHIVIST)
═══════════════════════════════════════════════════════════════════════════════
{last_chapter_metadata}
"""

                # Build World Bible state section for Archivist (since output_schema disables tools)
                bible_state_section = ""
                if bible_snapshot_content:
                    bible_state_section = f"""
═══════════════════════════════════════════════════════════════════════════════
                    CURRENT WORLD BIBLE STATE (FOR ARCHIVIST)
═══════════════════════════════════════════════════════════════════════════════
```json
{json.dumps(bible_snapshot_content, indent=2)}
```
"""

                input_text = f"""═══════════════════════════════════════════════════════════════════════════════
                         NARRATIVE CONTEXT (Use for continuity)
═══════════════════════════════════════════════════════════════════════════════

**RECENT CHAPTER SUMMARIES:**
{recent_summaries if recent_summaries else "This is Chapter 1 - no previous chapters."}

**LAST CHAPTER (Ch.{current_chapter}) SUMMARY:**
{last_summary}
{story_context}
{metadata_section}
{bible_state_section}
═══════════════════════════════════════════════════════════════════════════════
                              PLAYER ACTION
═══════════════════════════════════════════════════════════════════════════════

{choice_text}

{format_question_answers(question_answers) if question_answers else ""}
═══════════════════════════════════════════════════════════════════════════════
                            CHAPTER INSTRUCTIONS
═══════════════════════════════════════════════════════════════════════════════

CHAPTER TRACKING:
- Previous chapter was: Chapter {current_chapter}
- You are now writing: Chapter {next_chapter}
- Start your output with "# Chapter {next_chapter}"

ARCHIVIST: Use the CURRENT WORLD BIBLE STATE and LAST CHAPTER METADATA above to produce a BibleDelta with all necessary updates.

STORYTELLER: Reference the World Bible state provided above for complete context, character voices, and canon events.

Proceed to write the next chapter."""
                logger.log("pipeline", f"Enabled GAME pipeline for story {story_id} with universes: {universes}, writing Chapter {next_chapter}")
                
            elif action == "rewrite":
                # REWRITE PHASE - Delete last chapter and regenerate with instruction
                # NOTE: For research, use /research command BEFORE /rewrite
                instruction = inner_data.get("instruction", "")

                # 1. FIRST: Save the chapter context AND restore Bible state BEFORE deleting
                deleted_chapter_summary = ""
                deleted_chapter_text = ""
                deleted_chapter_sequence = 0

                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(History).where(History.story_id == story_id).order_by(desc(History.sequence)).limit(1)
                    )
                    last_history = result.scalar_one_or_none()
                    if last_history:
                        # Save context before deletion
                        deleted_chapter_summary = last_history.summary or ""
                        deleted_chapter_text = last_history.text or ""
                        deleted_chapter_sequence = last_history.sequence or 1

                        # CRITICAL: Restore Bible to pre-chapter state (like /undo does)
                        # This ensures the rewrite starts from the same Bible state as the original
                        if last_history.bible_snapshot:
                            bible_result = await db.execute(
                                select(WorldBible).where(WorldBible.story_id == story_id).with_for_update()
                            )
                            bible = bible_result.scalar_one_or_none()
                            if bible:
                                from sqlalchemy.orm.attributes import flag_modified
                                bible.content = copy.deepcopy(last_history.bible_snapshot)
                                flag_modified(bible, 'content')
                                logger.log("info", f"Rewrite: Restored Bible to pre-Chapter {deleted_chapter_sequence} state")

                        # Now delete the chapter
                        await db.delete(last_history)
                        await db.commit()
                        logger.log("info", f"Deleted last history item {last_history.id} (Chapter {deleted_chapter_sequence}) for rewrite.")

                # 2. Clean up ADK session events - clear ALL to avoid orphaned tool calls
                await delete_last_events_from_session(session_service, story_id, clear_all=True)

                # 3. Fetch universes from World Bible for context continuity
                universes, deviation = await get_story_universes(story_id)

                # 4. Get PREVIOUS chapters (before the deleted one) for story arc context
                async with AsyncSessionLocal() as db:
                    # Get 3 chapters BEFORE the deleted chapter for context
                    result = await db.execute(
                        select(History).where(
                            History.story_id == story_id,
                            History.sequence < deleted_chapter_sequence
                        ).order_by(desc(History.sequence)).limit(3)
                    )
                    prev_chapters = result.scalars().all()

                    # Build previous chapter summaries (reverse to chronological order)
                    prev_summaries = ""
                    if prev_chapters:
                        for ch in reversed(prev_chapters):
                            if ch.summary:
                                prev_summaries += f"- **Ch.{ch.sequence}**: {ch.summary[:300]}{'...' if len(ch.summary) > 300 else ''}\n"

                    # Get key World Bible facts for inline context
                    bible_result = await db.execute(select(WorldBible).where(WorldBible.story_id == story_id))
                    bible = bible_result.scalar_one_or_none()

                    # Capture Bible snapshot BEFORE Archivist modifies it (for undo rollback)
                    if bible and bible.content:
                        bible_snapshot_content = copy.deepcopy(bible.content)

                    rewrite_story_context = ""
                    if bible and bible.content:
                        meta = bible.content.get("meta", {})
                        char_sheet = bible.content.get("character_sheet", {})
                        rewrite_story_context = f"""
**STORY STATE (from World Bible):**
- Current Date: {meta.get('current_story_date', 'Unknown')}
- Protagonist: {char_sheet.get('name', 'Unknown')} ({char_sheet.get('cape_name', 'No cape name')})
- Status: {char_sheet.get('status', {}).get('condition', 'Normal') if isinstance(char_sheet.get('status'), dict) else 'Normal'}"""

                # 5. Dynamically switch to game pipeline (Archivist + Storyteller)
                active_agent = build_game_pipeline(story_id, universes=universes, deviation=deviation)

                # Build World Bible state section for Archivist (since output_schema disables tools)
                bible_state_section = ""
                if bible_snapshot_content:
                    bible_state_section = f"""
═══════════════════════════════════════════════════════════════════════════════
                    CURRENT WORLD BIBLE STATE (FOR ARCHIVIST)
═══════════════════════════════════════════════════════════════════════════════
```json
{json.dumps(bible_snapshot_content, indent=2)}
```
"""

                # 6. Construct rewrite instruction WITH the deleted chapter's context AND story arc
                input_text = f"""CRITICAL INSTRUCTION: REWRITE Chapter {deleted_chapter_sequence}.

═══════════════════════════════════════════════════════════════════════════════
                         STORY ARC CONTEXT (for continuity)
═══════════════════════════════════════════════════════════════════════════════

**PREVIOUS CHAPTER SUMMARIES:**
{prev_summaries if prev_summaries else "This is Chapter 1 - no previous chapters."}
{rewrite_story_context}
{bible_state_section}
═══════════════════════════════════════════════════════════════════════════════
                    ORIGINAL CHAPTER TO REWRITE (Chapter {deleted_chapter_sequence})
═══════════════════════════════════════════════════════════════════════════════

**ORIGINAL SUMMARY:**
{deleted_chapter_summary}

**ORIGINAL CONTENT (for reference - rewrite this, don't copy):**
{deleted_chapter_text[:3000]}{"..." if len(deleted_chapter_text) > 3000 else ""}

═══════════════════════════════════════════════════════════════════════════════
                              REWRITE INSTRUCTIONS
═══════════════════════════════════════════════════════════════════════════════

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
                logger.log("pipeline", f"Enabled REWRITE (GAME) pipeline for story {story_id} - rewriting Chapter {deleted_chapter_sequence}")
            
            elif action == "research":
                # MANUAL RESEARCH TRIGGER with depth support
                query = inner_data.get("query", "")
                depth = inner_data.get("depth", "quick")
                await manager.send_json({"type": "status", "status": "processing"}, websocket)

                # Notify user of research mode
                mode_indicator = "🔍 **DEEP RESEARCH**" if depth == "deep" else "🔎 **Quick Research**"
                await manager.send_json({
                    "type": "content_delta",
                    "text": f"\n{mode_indicator}: {query}\n",
                    "sender": "system"
                }, websocket)

                try:
                    # Get story universes for context in deep mode
                    universes = None
                    if depth == "deep":
                        universes, _ = await get_story_universes(story_id)
                        await manager.send_json({
                            "type": "content_delta",
                            "text": f"Planning focused research topics...\n",
                            "sender": "system"
                        }, websocket)

                    meta = MetaTools(story_id)
                    result = await meta.trigger_research(query, depth=depth, universes=universes)
                    await manager.send_json({
                        "type": "content_delta",
                        "text": f"\n--- [RESEARCH LOG: {query}]\n{result}\n-----------------------------\n\n",
                        "sender": "system"
                    }, websocket)
                except Exception as e:
                    await manager.send_json({"type": "error", "message": f"Research failed: {e}"}, websocket)

                await manager.send_json({"type": "turn_complete"}, websocket)
                continue

            elif action == "enrich":
                # ENRICH WORLD BIBLE - Analyze gaps and fill with PARALLEL research
                focuses = inner_data.get("focuses", ["all"])
                await manager.send_json({"type": "status", "status": "processing"}, websocket)

                try:
                    # Step 1: Read current World Bible to analyze gaps
                    async with AsyncSessionLocal() as db:
                        result = await db.execute(select(WorldBible).where(WorldBible.story_id == story_id))
                        bible = result.scalar_one_or_none()

                        if not bible or not bible.content:
                            await manager.send_json({
                                "type": "content_delta",
                                "text": "[Enrich] No World Bible found. Run /research first to initialize.\n",
                                "sender": "system"
                            }, websocket)
                            await manager.send_json({"type": "turn_complete"}, websocket)
                            continue

                        content = bible.content
                        universes = content.get("meta", {}).get("universes", ["General"])
                        gaps = []

                        # Analyze gaps based on focuses (multiple allowed)
                        await manager.send_json({
                            "type": "content_delta",
                            "text": f"[Enrich] Analyzing World Bible gaps (focus: {', '.join(focuses)})...\n",
                            "sender": "system"
                        }, websocket)

                        # Helper to check if any focus matches
                        def should_check(categories):
                            return "all" in focuses or any(cat in focuses for cat in categories)

                        # Check locations
                        if should_check(["locations", "locs", "location"]):
                            locations = content.get("world_state", {}).get("locations", {})
                            if len(locations) < 5:
                                gaps.append(f"Locations in {', '.join(universes)} - neighborhoods, landmarks, faction territories, key buildings, with atmosphere, key_features, typical_occupants, story_hooks")
                            territory_map = content.get("world_state", {}).get("territory_map", {})
                            if len(territory_map) < 3:
                                gaps.append(f"Territory control map for {', '.join(universes)} factions")

                        # Check relationships
                        if should_check(["relations", "relationships", "family"]):
                            relationships = content.get("character_sheet", {}).get("relationships", {})
                            factions = content.get("world_state", {}).get("factions", {})
                            # Check if protagonist's team/family faction has complete roster
                            for faction_name, faction_data in factions.items():
                                if isinstance(faction_data, dict):
                                    roster = faction_data.get("complete_member_roster", [])
                                    if len(roster) < 3 and faction_data.get("disposition_to_protagonist") == "Allied":
                                        gaps.append(f"Complete member roster for {faction_name} including family relationships, living situation, and role")

                            if len(relationships) < 3:
                                gaps.append(f"Character relationships for protagonist - family members (with type, relation, trust, family_branch), allies, team members in {', '.join(universes)}")

                        # Check character voices
                        if should_check(["voices", "voice", "dialogue"]):
                            voices = content.get("character_voices", {})
                            if len(voices) < 5:
                                gaps.append(f"Character voice profiles for major characters in {', '.join(universes)} - speech_patterns, verbal_tics, emotional_tells, topics_to_discuss, topics_to_avoid, example_dialogue")

                        # Check identities
                        if should_check(["identities", "identity", "personas"]):
                            identities = content.get("character_sheet", {}).get("identities", {})
                            if len(identities) < 1:
                                char_name = content.get("character_sheet", {}).get("name", "protagonist")
                                gaps.append(f"Identity profiles for {char_name} - civilian, hero, and any secret identities with known_by, suspected_by, activities, reputation, vulnerabilities")

                        # Check timeline events
                        if should_check(["events", "timeline", "canon"]):
                            events = content.get("canon_timeline", {}).get("events", [])
                            if len(events) < 10:
                                gaps.append(f"Canon timeline events for {', '.join(universes)} - major dated events with characters_involved, consequences, importance, status")

                        if not gaps:
                            await manager.send_json({
                                "type": "content_delta",
                                "text": f"[Enrich] World Bible looks complete for '{', '.join(focuses)}'! No major gaps found.\n",
                                "sender": "system"
                            }, websocket)
                            await manager.send_json({"type": "turn_complete"}, websocket)
                            continue

                        await manager.send_json({
                            "type": "content_delta",
                            "text": f"[Enrich] Found {len(gaps)} gaps to fill:\n" + "\n".join(f"  • {g[:80]}..." if len(g) > 80 else f"  • {g}" for g in gaps) + "\n\n",
                            "sender": "system"
                        }, websocket)

                    # Step 2: Run targeted research in PARALLEL
                    meta = MetaTools(story_id)

                    await manager.send_json({
                        "type": "content_delta",
                        "text": f"[Enrich] Running {len(gaps)} research tasks in parallel...\n",
                        "sender": "system"
                    }, websocket)

                    async def research_gap(gap_query):
                        """Helper to run single research and return result"""
                        try:
                            result = await meta.trigger_research(gap_query)
                            return {"query": gap_query, "success": True, "result": result}
                        except Exception as e:
                            return {"query": gap_query, "success": False, "error": str(e)}

                    # Run all research tasks in parallel
                    import asyncio
                    results = await asyncio.gather(*[research_gap(gap) for gap in gaps])

                    # Report results
                    success_count = sum(1 for r in results if r["success"])
                    for r in results:
                        if r["success"]:
                            await manager.send_json({
                                "type": "content_delta",
                                "text": f"  ✓ {r['result']}\n",
                                "sender": "system"
                            }, websocket)
                        else:
                            await manager.send_json({
                                "type": "content_delta",
                                "text": f"  ✗ Failed ({r['query'][:30]}...): {r['error'][:50]}\n",
                                "sender": "system"
                            }, websocket)

                    await manager.send_json({
                        "type": "content_delta",
                        "text": f"\n[Enrich] Complete! {success_count}/{len(gaps)} research tasks succeeded.\n",
                        "sender": "system"
                    }, websocket)

                except Exception as e:
                    await manager.send_json({"type": "error", "message": f"Enrich failed: {e}"}, websocket)

                await manager.send_json({"type": "turn_complete"}, websocket)
                continue

            elif action == "undo":
                # UNDO - Remove last chapter and restore Bible to pre-chapter state
                await manager.send_json({"type": "status", "status": "processing"}, websocket)
                try:
                    async with AsyncSessionLocal() as db:
                        # Find the last chapter to undo
                        result = await db.execute(
                            select(History).where(History.story_id == story_id).order_by(desc(History.sequence)).limit(1)
                        )
                        last_history = result.scalar_one_or_none()
                        if last_history:
                            chapter_id = last_history.id
                            chapter_seq = last_history.sequence
                            bible_restored = False

                            # RESTORE BIBLE from snapshot (state BEFORE this chapter was generated)
                            if last_history.bible_snapshot:
                                bible_result = await db.execute(
                                    select(WorldBible).where(WorldBible.story_id == story_id).with_for_update()
                                )
                                bible = bible_result.scalar_one_or_none()
                                if bible:
                                    from sqlalchemy.orm.attributes import flag_modified
                                    bible.content = copy.deepcopy(last_history.bible_snapshot)
                                    flag_modified(bible, 'content')
                                    bible_restored = True
                                    logger.log("info", f"Undo: Restored Bible to pre-Chapter {chapter_seq} state")

                            # Delete the chapter
                            await db.delete(last_history)
                            await db.commit()
                            logger.log("info", f"Undo: Deleted chapter {chapter_id} from story {story_id}")

                            # Also clean up ADK session events for consistency
                            await delete_last_events_from_session(session_service, story_id, count=1)

                            # Inform user
                            bible_msg = " World Bible restored to previous state." if bible_restored else ""
                            await manager.send_json({
                                "type": "content_delta",
                                "text": f"[System] Chapter {chapter_seq} undone successfully.{bible_msg}\n",
                                "sender": "system"
                            }, websocket)
                        else:
                            await manager.send_json({
                                "type": "content_delta",
                                "text": "[System] No chapters to undo.\n",
                                "sender": "system"
                            }, websocket)
                except Exception as e:
                    await manager.send_json({"type": "error", "message": f"Undo failed: {e}"}, websocket)

                await manager.send_json({"type": "turn_complete"}, websocket)
                continue

            elif action == "reset":
                # RESET - Clear corrupted session state
                await manager.send_json({"type": "status", "status": "processing"}, websocket)
                try:
                    agent_session_id = make_session_id(story_id)
                    async with AsyncSessionLocal() as db:
                        # Delete all events for this session
                        result = await db.execute(
                            select(AdkEvent).where(AdkEvent.adk_session_id == agent_session_id)
                        )
                        events = result.scalars().all()
                        event_count = len(events)

                        for event in events:
                            await db.delete(event)

                        # Also clear the session record
                        session_result = await db.execute(
                            select(AdkSession).where(AdkSession.adk_session_id == agent_session_id)
                        )
                        session = session_result.scalar_one_or_none()
                        if session:
                            await db.delete(session)

                        await db.commit()

                    logger.log("info", f"Reset session {agent_session_id}: deleted {event_count} events")
                    await manager.send_json({
                        "type": "content_delta",
                        "text": f"[System] Session reset complete. Cleared {event_count} events. Story history and World Bible preserved.\n",
                        "sender": "system"
                    }, websocket)
                except Exception as e:
                    await manager.send_json({"type": "error", "message": f"Reset failed: {e}"}, websocket)

                await manager.send_json({"type": "turn_complete"}, websocket)
                continue

            elif action == "bible-diff":
                # BIBLE-DIFF - Show what Archivist changed since last chapter's snapshot
                await manager.send_json({"type": "status", "status": "processing"}, websocket)
                try:
                    async with AsyncSessionLocal() as db:
                        # Get last chapter with its snapshot
                        result = await db.execute(
                            select(History).where(History.story_id == story_id).order_by(desc(History.sequence)).limit(1)
                        )
                        last_history = result.scalar_one_or_none()

                        # Get current Bible
                        bible_result = await db.execute(select(WorldBible).where(WorldBible.story_id == story_id))
                        bible = bible_result.scalar_one_or_none()

                        if not last_history or not last_history.bible_snapshot:
                            await manager.send_json({
                                "type": "content_delta",
                                "text": "[System] No Bible snapshot available for comparison. Snapshots are created when new chapters are generated.\n",
                                "sender": "system"
                            }, websocket)
                        elif not bible or not bible.content:
                            await manager.send_json({
                                "type": "content_delta",
                                "text": "[System] No World Bible found for this story.\n",
                                "sender": "system"
                            }, websocket)
                        else:
                            # Compute diff between snapshot (before) and current (after)
                            before = last_history.bible_snapshot
                            after = bible.content
                            diff_text = compute_bible_diff(before, after, last_history.sequence)

                            await manager.send_json({
                                "type": "content_delta",
                                "text": diff_text,
                                "sender": "system"
                            }, websocket)

                except Exception as e:
                    await manager.send_json({"type": "error", "message": f"Bible diff failed: {e}"}, websocket)

                await manager.send_json({"type": "turn_complete"}, websocket)
                continue

            elif action == "bible-snapshot":
                # BIBLE-SNAPSHOT - Save/load/list named snapshots
                await manager.send_json({"type": "status", "status": "processing"}, websocket)
                subcommand = inner_data.get("subcommand", "list")
                snapshot_name = inner_data.get("snapshot_name")

                try:
                    async with AsyncSessionLocal() as db:
                        # Get current chapter number
                        result = await db.execute(
                            select(History).where(History.story_id == story_id).order_by(desc(History.sequence)).limit(1)
                        )
                        last_history = result.scalar_one_or_none()
                        current_chapter = last_history.sequence if last_history else 0

                        if subcommand == "save":
                            if not snapshot_name:
                                await manager.send_json({
                                    "type": "content_delta",
                                    "text": "[System] Usage: /bible-snapshot save <name>\n",
                                    "sender": "system"
                                }, websocket)
                            else:
                                # Get current Bible content
                                bible_result = await db.execute(select(WorldBible).where(WorldBible.story_id == story_id))
                                bible = bible_result.scalar_one_or_none()
                                if not bible or not bible.content:
                                    await manager.send_json({
                                        "type": "content_delta",
                                        "text": "[System] No World Bible found to snapshot.\n",
                                        "sender": "system"
                                    }, websocket)
                                else:
                                    # Check if name already exists
                                    existing = await db.execute(
                                        select(BibleSnapshot).where(
                                            BibleSnapshot.story_id == story_id,
                                            BibleSnapshot.name == snapshot_name
                                        )
                                    )
                                    if existing.scalar_one_or_none():
                                        await manager.send_json({
                                            "type": "content_delta",
                                            "text": f"[System] Snapshot '{snapshot_name}' already exists. Use a different name.\n",
                                            "sender": "system"
                                        }, websocket)
                                    else:
                                        # Create snapshot
                                        new_snapshot = BibleSnapshot(
                                            story_id=story_id,
                                            name=snapshot_name,
                                            content=copy.deepcopy(bible.content),
                                            chapter_number=current_chapter
                                        )
                                        db.add(new_snapshot)
                                        await db.commit()
                                        await manager.send_json({
                                            "type": "content_delta",
                                            "text": f"[System] ✅ Snapshot '{snapshot_name}' saved at Chapter {current_chapter}.\n",
                                            "sender": "system"
                                        }, websocket)

                        elif subcommand == "load":
                            if not snapshot_name:
                                await manager.send_json({
                                    "type": "content_delta",
                                    "text": "[System] Usage: /bible-snapshot load <name>\n",
                                    "sender": "system"
                                }, websocket)
                            else:
                                # Find snapshot
                                snap_result = await db.execute(
                                    select(BibleSnapshot).where(
                                        BibleSnapshot.story_id == story_id,
                                        BibleSnapshot.name == snapshot_name
                                    )
                                )
                                snapshot = snap_result.scalar_one_or_none()
                                if not snapshot:
                                    await manager.send_json({
                                        "type": "content_delta",
                                        "text": f"[System] Snapshot '{snapshot_name}' not found. Use /bible-snapshot list to see available snapshots.\n",
                                        "sender": "system"
                                    }, websocket)
                                else:
                                    # Restore Bible to snapshot
                                    bible_result = await db.execute(
                                        select(WorldBible).where(WorldBible.story_id == story_id).with_for_update()
                                    )
                                    bible = bible_result.scalar_one_or_none()
                                    if bible:
                                        from sqlalchemy.orm.attributes import flag_modified
                                        bible.content = copy.deepcopy(snapshot.content)
                                        flag_modified(bible, 'content')
                                        await db.commit()
                                        await manager.send_json({
                                            "type": "content_delta",
                                            "text": f"[System] ✅ World Bible restored to snapshot '{snapshot_name}' (from Chapter {snapshot.chapter_number}).\n",
                                            "sender": "system"
                                        }, websocket)
                                    else:
                                        await manager.send_json({
                                            "type": "content_delta",
                                            "text": "[System] No World Bible found to restore.\n",
                                            "sender": "system"
                                        }, websocket)

                        elif subcommand == "list":
                            # List all snapshots
                            snap_result = await db.execute(
                                select(BibleSnapshot).where(BibleSnapshot.story_id == story_id).order_by(BibleSnapshot.created_at)
                            )
                            snapshots = snap_result.scalars().all()
                            if not snapshots:
                                await manager.send_json({
                                    "type": "content_delta",
                                    "text": "[System] No saved snapshots. Use /bible-snapshot save <name> to create one.\n",
                                    "sender": "system"
                                }, websocket)
                            else:
                                lines = ["[System] **Saved Bible Snapshots:**\n"]
                                for snap in snapshots:
                                    lines.append(f"  • **{snap.name}** (Chapter {snap.chapter_number}, {snap.created_at.strftime('%Y-%m-%d %H:%M')})\n")
                                lines.append("\nUse /bible-snapshot load <name> to restore.\n")
                                await manager.send_json({
                                    "type": "content_delta",
                                    "text": "".join(lines),
                                    "sender": "system"
                                }, websocket)

                        elif subcommand == "delete":
                            if not snapshot_name:
                                await manager.send_json({
                                    "type": "content_delta",
                                    "text": "[System] Usage: /bible-snapshot delete <name>\n",
                                    "sender": "system"
                                }, websocket)
                            else:
                                snap_result = await db.execute(
                                    select(BibleSnapshot).where(
                                        BibleSnapshot.story_id == story_id,
                                        BibleSnapshot.name == snapshot_name
                                    )
                                )
                                snapshot = snap_result.scalar_one_or_none()
                                if not snapshot:
                                    await manager.send_json({
                                        "type": "content_delta",
                                        "text": f"[System] Snapshot '{snapshot_name}' not found.\n",
                                        "sender": "system"
                                    }, websocket)
                                else:
                                    await db.delete(snapshot)
                                    await db.commit()
                                    await manager.send_json({
                                        "type": "content_delta",
                                        "text": f"[System] ✅ Snapshot '{snapshot_name}' deleted.\n",
                                        "sender": "system"
                                    }, websocket)
                        else:
                            await manager.send_json({
                                "type": "content_delta",
                                "text": f"[System] Unknown subcommand: {subcommand}. Use: save, load, list, or delete.\n",
                                "sender": "system"
                            }, websocket)

                except Exception as e:
                    await manager.send_json({"type": "error", "message": f"Bible snapshot failed: {e}"}, websocket)

                await manager.send_json({"type": "turn_complete"}, websocket)
                continue

            else:
                await manager.send_json({"type": "error", "message": f"Unknown action: {action}"}, websocket)
                continue

            # FRESH RUNNER for this action to ensure agent pipeline is picked up
            runner = Runner(
                agent=active_agent,
                app_name="agents",
                session_service=session_service,
                memory_service=memory_service,
                artifact_service=artifact_service
            )

            # Run the Pipeline
            await manager.send_json({"type": "status", "status": "processing"}, websocket)
            
            full_text = ""
            buffer = ""
            ws_disconnected = False  # Track if client disconnected during streaming

            # Use Runner with Persistent Session
            # We construct Content object
            user_msg = types.Content(parts=[types.Part(text=input_text)], role="user")
            
            # RE-SYNC: Ensure the runner is using the latest agent if it was changed
            # Actually, we'll recreate the runner here or just set it to be sure.
            # In some ADK versions, the runner is stale if agent is reassigned.
            
            logger.log("runner_start", f"Running agent: {runner.agent.name}", {"action": action, "story_id": story_id})
            print(f"DEBUG: Starting runner for story {story_id} with agent {runner.agent.name}")

            # Heartbeat task keeps the WebSocket alive and informs the user during long generation
            settings = get_settings()
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
                        }, websocket)
                    except WebSocketDisconnect:
                        return

            heartbeat_task = asyncio.create_task(heartbeat())

            try:
                async with asyncio.timeout(settings.pipeline_timeout_seconds):
                    async with runner:
                        async for event in runner.run_async(
                            user_id=user_id,
                            session_id=agent_session_id,
                            new_message=user_msg
                        ):
                            # IMPORTANT: Only stream output from the Storyteller agent to the user
                            # Research agents (lore_hunter, lore_keeper, archivist) run silently
                            event_author = getattr(event, 'author', '')
                            # Check for storyteller - handle both exact match and variations
                            is_storyteller = event_author == "storyteller" or "storyteller" in event_author.lower()

                            # Debug: Log all event authors to track pipeline flow
                            has_content = bool(getattr(event, 'content', None) or getattr(event, 'text', None))
                            print(f"EVENT: author='{event_author}' | has_content={has_content} | turn_complete={getattr(event, 'turnComplete', False)}")

                            # Detailed debug for storyteller events
                            if is_storyteller and has_content:
                                content = getattr(event, 'content', None)
                                print(f"  STORYTELLER CONTENT TYPE: {type(content)}")
                                if content:
                                    print(f"  STORYTELLER CONTENT ATTRS: {[a for a in dir(content) if not a.startswith('_')][:10]}")
                                    if hasattr(content, 'parts'):
                                        print(f"  PARTS: {content.parts}")
                                    if hasattr(content, 'text'):
                                        print(f"  TEXT ATTR: {content.text[:100] if content.text else 'None'}...")

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
                                            # Handle dict-like parts
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
                                        except:
                                            pass
                                    # Fallback to string but be more lenient
                                    if not text_chunk:
                                        s = str(content)
                                        # Only filter out clearly empty/technical responses
                                        if s and s != "None" and "parts=None" not in s and s.strip() != "role='model'":
                                            # Try to extract text from string representation
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
                                     if matches: text_chunk = "".join(matches)
                                     else:
                                         matches = re.findall(r"text='([\s\S]*?)'", text_chunk)
                                         if matches: text_chunk = "".join(matches)

                                # Only stream Storyteller output to user; accumulate all for logging
                                if is_storyteller:
                                    buffer += text_chunk
                                    logger.log("output_chunk", text_chunk)
                                    try:
                                        await manager.send_json({
                                            "type": "content_delta",
                                            "text": text_chunk,
                                            "sender": "storyteller"
                                        }, websocket)
                                    except WebSocketDisconnect:
                                        # Client disconnected during streaming - continue to save chapter
                                        logger.log("warning", f"WebSocket disconnected during streaming, will still save chapter")
                                        ws_disconnected = True
                                elif event_author == "archivist" or "archivist" in event_author.lower():
                                    # ARCHIVIST STRUCTURED OUTPUT PROCESSING
                                    # The Archivist outputs a BibleDelta JSON - parse and apply it
                                    logger.log("archivist_output", f"Received Archivist output: {text_chunk[:500]}...")
                                    try:
                                        from src.schemas import BibleDelta
                                        from src.utils.bible_delta_processor import apply_bible_delta

                                        # Try to parse the output as JSON
                                        delta_json = json.loads(text_chunk)
                                        delta = BibleDelta(**delta_json)

                                        # Apply the delta to the Bible
                                        result = await apply_bible_delta(story_id, delta)
                                        if result["success"]:
                                            logger.log("archivist_applied", f"Applied {len(result['updates_applied'])} Bible updates: {result['updates_applied']}")
                                        else:
                                            logger.log("archivist_error", f"Failed to apply delta: {result['errors']}")
                                    except json.JSONDecodeError as e:
                                        logger.log("archivist_json_error", f"Failed to parse Archivist JSON: {e}")
                                    except Exception as e:
                                        logger.log("archivist_error", f"Error processing Archivist output: {e}")
                                else:
                                    # Log research agent output for debugging but don't send to user
                                    logger.log("research_output", f"[{event_author}] {text_chunk[:200]}...")

            except TimeoutError:
                pipeline_timed_out = True
                timeout_mins = settings.pipeline_timeout_seconds / 60
                logger.log("timeout", f"Pipeline timed out after {timeout_mins:.0f}m for story {story_id}", {"action": action})
                if not ws_disconnected:
                    try:
                        await manager.send_json({
                            "type": "error",
                            "message": f"Generation timed out after {timeout_mins:.0f} minutes. Any partial output has been saved. Please try again."
                        }, websocket)
                    except WebSocketDisconnect:
                        ws_disconnected = True
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

            # End of turn - Save to DB
            logger.log("turn_end", f"Turn complete for story {story_id}")

            # Check for empty/failed output (skip if we already sent a timeout error)
            if not pipeline_timed_out and (not buffer or len(buffer.strip()) < 100):
                logger.log("warning", f"Storyteller produced minimal output ({len(buffer)} chars). This could mean the Storyteller agent didn't produce text or only made tool calls.", {"story_id": story_id, "action": action})
                # Send error message to user if completely empty (only if still connected)
                if not buffer and not ws_disconnected:
                    try:
                        await manager.send_json({
                            "type": "content_delta",
                            "text": "\n\n⚠️ **Generation Issue**: The story agent did not produce narrative output. This may be due to context length or a timeout. Please try again or use /research first to populate the World Bible.\n",
                            "sender": "system"
                        }, websocket)
                    except WebSocketDisconnect:
                        ws_disconnected = True

            # Extract basic info from buffer for DB
            # Note: The buffer contains everything, including the JSON from Game Master.
            # We want to parse it to better store structured data.
            
            clean_text = buffer
            choices_json = None
            summary_text = None
            questions_json = None  # Optional clarifying questions for next chapter

            # Try to extract JSON block
            json_match = re.search(r'\{[\s\S]*\"choices\"[\s\S]*\}', buffer)
            if json_match:
                try:
                    json_str = json_match.group(0)
                    json_str = re.sub(r'```json|```', '', json_str).strip()
                    parsed = json.loads(json_str)
                    choices_json = parsed.get("choices")
                    summary_text = parsed.get("summary")
                    questions_json = parsed.get("questions")  # Extract optional questions
                    # Remove JSON from stored text for cleaner history display? 
                    # Actually keeping it in text is fine for raw record, but we want structured too.
                    # Frontend cleans it up. Let's keep raw text as is or clean it?
                    # Let's keep raw text in 'text' column for fidelity, but structured data in columns.
                except:
                    pass
            
            # Save History Item (Story History)
            async with AsyncSessionLocal() as db:
                # 1. Save Structured History (Chapter)
                result = await db.execute(select(History).where(History.story_id == story_id).order_by(desc(History.sequence)).limit(1))
                last_history = result.scalar_one_or_none()
                next_seq = (last_history.sequence + 1) if last_history else 1
                
                new_history = History(
                    id=str(uuid.uuid4()),
                    story_id=story_id,
                    sequence=next_seq,
                    text=buffer,
                    summary=summary_text,
                    choices=choices_json,
                    bible_snapshot=bible_snapshot_content  # Bible state BEFORE this chapter (for undo)
                )
                db.add(new_history)

                # ADK Events are now handled by FableSessionService, no manual save here.

                await db.commit()

            # AUTO-UPDATE BIBLE: Apply chapter metadata to World Bible
            # This ensures core updates ALWAYS happen, regardless of Archivist behavior
            await auto_update_bible_from_chapter(story_id, buffer, next_seq)

            # VERIFY & AUTO-FIX: Check Bible integrity and fix any schema issues
            integrity_issues = await verify_bible_integrity(story_id)
            if integrity_issues:
                logger.log("bible_verification", f"Fixed {len(integrity_issues)} schema issues")

            logger.log("turn_end", f"Turn complete for story {story_id}")
            if not ws_disconnected:
                try:
                    # Include questions in turn_complete for frontend to display
                    turn_complete_msg = {"type": "turn_complete"}
                    if questions_json:
                        turn_complete_msg["questions"] = questions_json
                    await manager.send_json(turn_complete_msg, websocket)
                except WebSocketDisconnect:
                    ws_disconnected = True

            if ws_disconnected:
                manager.disconnect(websocket)
                print(f"WebSocket disconnected for story: {story_id} (chapter saved successfully)")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print(f"WebSocket disconnected for story: {story_id} (before chapter generation completed)")
    except Exception as e:
        traceback.print_exc()
        await manager.send_json({"type": "error", "message": str(e)}, websocket)
