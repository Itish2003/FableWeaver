"""Pipeline builders and ADK session helpers.

Contains:
- ``build_init_pipeline`` — creates the init pipeline (research swarm → lore keeper → storyteller)
- ``build_game_pipeline`` — creates the game-loop pipeline (archivist → storyteller)
- ``get_story_universes`` — reads universe list from World Bible meta
- ``reset_adk_session`` — deletes and recreates an ADK session
"""

from __future__ import annotations

from typing import List

from google.adk.agents.sequential_agent import SequentialAgent
from sqlalchemy import select

from src.database import AsyncSessionLocal
from src.models import WorldBible
from src.config import make_session_id, get_session_service
from src.utils.logging_config import get_logger
from src.utils.legacy_logger import logger

from src.agents.research import create_lore_hunter_swarm, create_lore_keeper, plan_research_queries
from src.agents.narrative import create_storyteller, create_archivist

_logger = get_logger("fable.pipelines")


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
    _logger.info("Running Query Planner", extra={"story_id": story_id})
    research_topics = await plan_research_queries(universes, deviation, user_input)

    # 1. Research Swarm - Now uses dynamically generated topics from Query Planner
    agents.append(create_lore_hunter_swarm(specific_topics=research_topics))
    # 2. Lore Keeper (Permanently updates the Bible)
    agents.append(await create_lore_keeper(story_id=story_id))
    # 3. Storyteller (Takes context, writes chapter + choices)
    agents.append(await create_storyteller(story_id=story_id, universes=universes, deviation=deviation))

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


async def build_game_pipeline(story_id: str, universes: List[str] = None, deviation: str = "") -> SequentialAgent:
    agents = []

    # 1. Archivist (Updates Bible based on previous turn)
    agents.append(await create_archivist(story_id=story_id))

    # 2. Storyteller (Checks research, Writes chapter + choices)
    # Pass universes for context if available
    agents.append(await create_storyteller(story_id=story_id, universes=universes, deviation=deviation))

    return SequentialAgent(name="game_pipeline", sub_agents=agents)


async def reset_adk_session(story_id: str) -> None:
    """Reset ADK session for undo/rewrite by deleting and recreating it."""
    agent_session_id = make_session_id(story_id)
    session_service = get_session_service()
    await session_service.delete_session(
        app_name="agents", user_id="user", session_id=agent_session_id
    )
    await session_service.create_session(
        app_name="agents", user_id="user", session_id=agent_session_id
    )
    logger.log("info", f"Reset ADK session {agent_session_id}")
