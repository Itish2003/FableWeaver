"""Handle the ``init`` WebSocket action — start a new story."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from src.database import AsyncSessionLocal
from src.models import WorldBible
from src.pipelines import build_init_pipeline
from src.utils.legacy_logger import logger
from src.utils.logging_config import get_logger
from src.ws.context import WsSessionContext
from src.ws.actions import ActionResult

_logger = get_logger("fable.ws.init")


async def handle_init(ctx: WsSessionContext, inner_data: dict) -> ActionResult:
    universes = inner_data.get("universes", ["General"])
    deviation = inner_data.get("timeline_deviation", "")

    _logger.debug("Universes for story=%s: %s", ctx.story_id, universes)

    # Store universes in World Bible meta for later retrieval
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(WorldBible).where(WorldBible.story_id == ctx.story_id))
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
            flag_modified(bible, "content")
            await db.commit()

    # Extract user_input BEFORE building pipeline so Query Planner can use it
    user_req = inner_data.get("user_input", "")

    # Dynamically switch to init pipeline (now async with Query Planner)
    ctx.active_agent = await build_init_pipeline(ctx.story_id, universes, deviation, user_req)
    genre = inner_data.get("genre", "Fantasy")
    theme = inner_data.get("theme", "Mystery")

    ctx.input_text = f"""PHASE: INITIALIZATION
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

    logger.log("pipeline", f"Enabled INIT pipeline for story {ctx.story_id}")
    return ActionResult(needs_runner=True)
