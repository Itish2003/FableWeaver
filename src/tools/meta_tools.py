from google.adk.runners import InMemoryRunner
from google.genai import types
from src.agents.research import create_lore_hunter_swarm, create_lore_keeper, create_midstream_lore_keeper, plan_midstream_queries
from google.adk.agents.sequential_agent import SequentialAgent
from typing import Literal, List, Optional

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
        import logging
        _meta_logger = logging.getLogger("fable.meta_tools")
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
        
        # We use a temporary runner for this sub-task
        runner = InMemoryRunner(agent=pipeline, app_name="agents")
        
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
            if tool_calls_made:
                logger.log("tool_end", f"Research on '{topic}' completed. Tools called: {tool_calls_made}")
            else:
                logger.log("warning", f"Research on '{topic}' completed but NO TOOL CALLS were made! Lore Keeper may have failed to update Bible.")
            return f"Research on '{topic}' completed. The World Bible has been updated with new findings."
        except Exception as e:
            logger.log("error", f"Research failed for {topic}: {str(e)}")
            return f"Research failed: {str(e)}"
