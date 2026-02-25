import json
import logging

from google.adk.runners import InMemoryRunner
from google.adk.plugins import ReflectAndRetryToolPlugin
from google.genai import types
from src.agents.research import create_lore_hunter_swarm, create_lore_keeper, create_midstream_lore_keeper, plan_midstream_queries
from google.adk.agents.sequential_agent import SequentialAgent
from typing import Literal, List, Optional

_meta_logger = logging.getLogger("fable.meta_tools")

async def _fallback_integrate_research(story_id: str, research_texts: list[str], topic: str, logger) -> int:
    """
    Programmatic fallback: extract Bible updates from research text via a direct
    Gemini call, then apply them with BibleTools.update_bible().

    Used when the Lore Keeper agent fails to make tool calls despite mode=ANY.
    Returns the number of updates successfully applied.
    """
    from src.utils.resilient_client import ResilientClient
    from src.utils.auth import get_api_key
    from src.tools.core_tools import BibleTools

    combined_text = "\n\n".join(research_texts)
    if not combined_text.strip():
        logger.log("warning", "[fallback] No research text to integrate.")
        return 0

    # Truncate to avoid token limits on the extraction call
    if len(combined_text) > 30_000:
        combined_text = combined_text[:30_000] + "\n...[truncated]"

    client = ResilientClient(api_key=get_api_key())
    bible = BibleTools(story_id)

    prompt = f"""You are a data extraction assistant. Below is raw research text about "{topic}".

Extract ALL factual data and output a JSON array of Bible updates.
Each update is an object with:
- "key": dot-notation Bible path (e.g., "character_voices.Taylor.speech_patterns", "power_origins.combat_style", "world_state.characters.Eidolon", "canon_timeline.events")
- "value": the data (use arrays for list fields like speech_patterns, verbal_tics, signature_moves; use strings for single values; use objects for character/faction entries)

KEY MAPPINGS:
- Character personality → character_voices.<Name>.personality (string)
- Speech patterns → character_voices.<Name>.speech_patterns (array of strings)
- Verbal tics → character_voices.<Name>.verbal_tics (array of strings)
- Dialogue examples → character_voices.<Name>.dialogue_examples (array of strings)
- Combat style → power_origins.combat_style (string)
- Signature moves → power_origins.signature_moves (array of strings)
- Weaknesses → power_origins.weaknesses (array of strings)
- Characters → world_state.characters.<Name> (object with role, disposition, powers, universe)
- Factions → world_state.factions.<Name> (object with type, description, members)
- Locations → world_state.locations.<Name> (object with description, significance)
- Timeline events → canon_timeline.events (array of event objects)

RESEARCH TEXT:
{combined_text}

Output ONLY a valid JSON array. No markdown, no explanation."""

    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = response.text.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3].strip()
        if text.startswith("json"):
            text = text[4:].strip()

        updates = json.loads(text)
        if not isinstance(updates, list):
            updates = [updates]

        applied = 0
        for update in updates:
            key = update.get("key", "")
            value = update.get("value")
            if key and value is not None:
                try:
                    await bible.update_bible(key, value)
                    logger.log("tool_step", f"[fallback] update_bible({key!r}, ...)")
                    applied += 1
                except Exception as e:
                    logger.log("warning", f"[fallback] Failed to update {key}: {e}")

        logger.log("tool_end", f"[fallback] Applied {applied}/{len(updates)} updates from research text.")
        return applied

    except json.JSONDecodeError as e:
        logger.log("error", f"[fallback] Could not parse extraction JSON: {e}")
    except Exception as e:
        logger.log("error", f"[fallback] Integration failed: {e}")

    # Last resort: store raw text in knowledge_base
    try:
        safe_topic = topic[:40].replace(" ", "_").replace("/", "_")
        await bible.update_bible(
            f"world_state.knowledge_base.research_{safe_topic}",
            combined_text[:5000],
        )
        logger.log("tool_step", f"[fallback] Stored raw research text in knowledge_base.")
        return 1
    except Exception:
        return 0


class MetaTools:
    def __init__(self, story_id: str):
        self.story_id = story_id

    async def trigger_research(
        self,
        topic: str,
        depth: Literal["quick", "deep"] = "quick",
        universes: Optional[List[str]] = None
    ):
        """
        Pauses the story to research a topic and update the world bible.

        Args:
            topic: The research query/topic
            depth: "quick" for single-agent research, "deep" for multi-agent parallel research
            universes: List of story universes for context (used in deep mode)
        """
        _meta_logger.debug("MetaTools.trigger_research called for topic: %s (depth=%s)", topic, depth)
        from src.utils.legacy_logger import logger

        # Query sanitization: Detect and clean log message contamination
        contamination_patterns = [
            "Starting research runner for ",
            "[researcher_",
            "[lore_keeper]",
            "TOOL CALL:",
            "TOOL RESULT:",
        ]
        original_topic = topic
        for pattern in contamination_patterns:
            if pattern in topic:
                logger.log("warning", f"Query contamination detected: '{pattern}' found in query. Cleaning...")
                topic = topic.replace(pattern, "").strip()

        if topic != original_topic:
            logger.log("info", f"Cleaned query: '{topic}'")

        logger.log("tool_start", f"Triggering research on: {topic}", {"story_id": self.story_id})

        # Build Research Pipeline based on depth
        if depth == "deep":
            # Deep mode: Use query planner to break into multiple focused topics
            logger.log("tool_step", f"[DEEP] Planning research topics for: {topic}")

            research_topics = await plan_midstream_queries(
                query=topic,
                universes=universes or []
            )

            logger.log("tool_step", f"[DEEP] Generated {len(research_topics)} research topics")
            for i, t in enumerate(research_topics, 1):
                logger.log("tool_step", f"  {i}. {t.get('focus', t.get('query', 'Unknown'))}")

            # Create swarm with multiple focused topics
            hunter = create_lore_hunter_swarm(specific_topics=research_topics)
        else:
            # Quick mode: Single researcher agent
            hunter = create_lore_hunter_swarm(specific_topics=[topic])

        # Use lightweight midstream lore keeper (simpler instruction, more reliable updates)
        keeper = create_midstream_lore_keeper(self.story_id)

        # Sequential: Hunter(s) -> Keeper
        pipeline = SequentialAgent(
            name=f"research_tool_pipeline_{depth}",
            sub_agents=[hunter, keeper]
        )
        
        # We use a temporary runner for this sub-task (with retry plugin so
        # the model can self-correct on invalid tool arguments like bare integers)
        runner = InMemoryRunner(
            agent=pipeline,
            app_name="agents",
            plugins=[ReflectAndRetryToolPlugin(max_retries=3)],
        )
        
        message = types.Content(parts=[types.Part(text=f"Research Request: {topic}")])
        
        try:
            # Create a session for the research task. 
            session_id = f"research_{self.story_id}_{hash(topic)}"
            try:
                await runner.session_service.create_session(
                    app_name="agents",
                    user_id="system",
                    session_id=session_id
                )
            except:
                pass

            logger.log("tool_step", f"Starting research runner for {topic}")
            tool_calls_made = []
            research_texts = []  # FIX #38: Collect research text for fallback
            async with runner:
                async for chunk in runner.run_async(
                    user_id="system",
                    session_id=session_id,
                    new_message=message
                ):
                    # Log agent activity for debugging
                    if hasattr(chunk, 'content') and chunk.content:
                        # Log text responses from agents
                        if hasattr(chunk.content, 'parts'):
                            for part in chunk.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    # Truncate long text for log readability
                                    text_preview = part.text[:200] + "..." if len(part.text) > 200 else part.text
                                    logger.log("tool_step", f"[{chunk.author or 'agent'}] {text_preview}")
                                    # Collect text from research agents for fallback
                                    author = chunk.author or ""
                                    if "researcher" in author or "lore_keeper" in author:
                                        research_texts.append(part.text)
                                if hasattr(part, 'function_call') and part.function_call:
                                    fc = part.function_call
                                    tool_calls_made.append(fc.name)
                                    logger.log("tool_step", f"[{chunk.author or 'agent'}] TOOL CALL: {fc.name}({str(fc.args)[:100]}...)")
                                if hasattr(part, 'function_response') and part.function_response:
                                    fr = part.function_response
                                    response_preview = str(fr.response)[:150] + "..." if len(str(fr.response)) > 150 else str(fr.response)
                                    logger.log("tool_step", f"[{chunk.author or 'agent'}] TOOL RESULT: {fr.name} -> {response_preview}")

                    # Also check for errors
                    if hasattr(chunk, 'error_message') and chunk.error_message:
                        logger.log("error", f"[{chunk.author or 'agent'}] ERROR: {chunk.error_message}")

            # Summary of what happened
            update_bible_calls = [c for c in tool_calls_made if c == "update_bible"]
            if update_bible_calls:
                logger.log("tool_end", f"Research on '{topic}' completed. {len(update_bible_calls)} update_bible calls made.")
            else:
                # FIX #38: Programmatic fallback — extract and apply updates directly
                logger.log("warning", f"Research on '{topic}': NO update_bible calls made. Attempting programmatic fallback...")
                fallback_count = await _fallback_integrate_research(
                    self.story_id, research_texts, topic, logger
                )
                if fallback_count:
                    logger.log("tool_end", f"Research on '{topic}': Fallback applied {fallback_count} updates.")
                else:
                    logger.log("warning", f"Research on '{topic}': Fallback also failed. Bible may not be updated.")

            return f"Research on '{topic}' completed. The World Bible has been updated with new findings."
        except Exception as e:
            logger.log("error", f"Research failed for {topic}: {str(e)}")
            return f"Research failed: {str(e)}"
