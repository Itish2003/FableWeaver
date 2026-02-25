import logging
import os
import re
import json
from typing import List, Any, Dict
from google.adk import Agent
from google.genai import types as genai_types
from google.adk.agents.parallel_agent import ParallelAgent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.tools import google_search
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from src.utils.auth import get_api_key
from src.utils.resilient_client import ResilientClient
from src.utils.resilient_gemini import ResilientGemini
from src.tools.core_tools import BibleTools
from src.config import get_settings
from src.callbacks import make_timing_callbacks, tool_error_fallback
from src.utils.universe_config import get_wiki_hint, get_universe_config

logger = logging.getLogger("fable.research")


# --- Query Planner ---

async def plan_research_queries(
    universes: List[str],
    deviation: str,
    user_input: str = ""
) -> List[Dict[str, str]]:
    """
    Pre-pipeline LLM call that analyzes the user's input and generates
    targeted research topics for the Lore Hunter swarm.

    This solves the problem of crossover powers not being researched when
    the user mentions a power source from a different universe than the
    story setting (e.g., "Amon's powers from Lord of the Mysteries" in Wormverse).

    Returns a list of research topic dicts with 'query', 'focus', and 'universe' keys.
    """
    settings = get_settings()
    client = ResilientClient(api_key=get_api_key())

    # Combine all user input for analysis
    universes_str = ', '.join(universes)
    full_context = f"""UNIVERSES: {universes_str}

TIMELINE DEVIATION / OC DESCRIPTION:
{deviation}

USER INPUT / ADDITIONAL CONTEXT:
{user_input}
""".strip()

    prompt = """You are a Research Query Planner for an interactive fiction engine.

Analyze the following story setup and generate a comprehensive list of research topics.

""" + full_context + """

═══════════════════════════════════════════════════════════════════════════════
                              YOUR TASK
═══════════════════════════════════════════════════════════════════════════════

1. Identify ALL universes that need research:
   - The explicitly listed universes
   - ANY universe mentioned in the OC description (e.g., "powers from Lord of the Mysteries")
   - Power sources from other media/franchises

2. For EACH universe, generate research topics covering:
   - Timeline and major events
   - Characters, powers, and factions
   - Power system rules and limitations
   - Complete faction/team member lists
   - Supporting characters and relationships
   - Character secrets and hidden knowledge

3. For CROSSOVER POWERS (CRITICAL):
   If the OC has powers from a specific character (e.g., "Amon's powers", "Gojo's abilities"):
   - Generate DEDICATED research topics for that character's powers
   - Include: techniques, limitations, how they use them, power scaling
   - This is NOT optional - missing this ruins the story's accuracy

4. For POWER USAGE SCENES (CRITICAL):
   Generate specific queries to find HOW powers are used in practice:
   - "Character X power usage fight scenes examples" - How they deploy powers in combat
   - "Character X abilities creative uses" - Unconventional applications
   - "Character X vs Y fight scene" - Specific battle examples with tactics
   The Storyteller needs SCENE-LEVEL detail to write believable power usage, not just lists.

═══════════════════════════════════════════════════════════════════════════════
                              OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════════════════

Return a JSON array of research topics. Each topic should have:
- "query": The search query to use (be specific, include wiki hints if known)
- "focus": Human-readable description of what this research covers
- "universe": Which universe/source this belongs to

Example output:
```json
[
  {{"query": "\\"Wormverse\\" official wiki timeline chronology major events site:worm.fandom.com", "focus": "Timeline and major events of Wormverse", "universe": "Wormverse"}},
  {{"query": "\\"Lord of the Mysteries\\" Amon powers abilities Sequence Error pathway site:lordofthemysteries.fandom.com", "focus": "Amon's complete powerset from Lord of the Mysteries", "universe": "Lord of the Mysteries"}},
  {{"query": "\\"Lord of the Mysteries\\" Amon techniques how he uses powers parasitism theft", "focus": "How Amon uses his powers and techniques", "universe": "Lord of the Mysteries"}},
  {{"query": "\\"Lord of the Mysteries\\" Amon fight scenes battles Klein examples", "focus": "Specific scenes showing Amon using powers in combat", "universe": "Lord of the Mysteries"}},
  {{"query": "\\"Lord of the Mysteries\\" Amon steal abilities timing manipulation scene examples", "focus": "Detailed examples of Amon stealing concepts/abilities", "universe": "Lord of the Mysteries"}}
]
```

IMPORTANT:
- Generate 6-8 topics per universe
- For crossover powers, generate 4-6 dedicated topics about that specific power source
- At least 2 topics per power source should focus on SCENE EXAMPLES and COMBAT USAGE
- Use site: hints for known wikis (worm.fandom.com, lordofthemysteries.fandom.com, etc.)
- Be thorough - missing a universe or power source means the story will have gaps

Return ONLY the JSON array, no other text."""

    logger.info("QueryPlanner: analyzing input to generate research topics")

    try:
        response = await client.aio.models.generate_content(
            model=settings.model_research,
            contents=prompt
        )

        response_text = response.text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        topics = json.loads(response_text)

        logger.info("QueryPlanner: generated %d research topics", len(topics))
        for i, topic in enumerate(topics, 1):
            logger.debug("  %d. [%s] %s", i, topic.get('universe', 'Unknown'), topic.get('focus', 'No focus'))

        return topics

    except json.JSONDecodeError as e:
        logger.warning("QueryPlanner: failed to parse JSON response: %s | raw: %.500s", e, response_text)
        # Fallback to default topics if parsing fails
        return _generate_default_topics(universes)
    except Exception as e:
        logger.exception("QueryPlanner: error during query planning")
        return _generate_default_topics(universes)


def _generate_default_topics(universes: List[str]) -> List[Dict[str, str]]:
    """Fallback topic generation if the LLM call fails."""
    topics = []

    for universe in universes:
        hint = get_wiki_hint(universe)
        wiki_hint = f" {hint}" if hint else ""

        topics.extend([
            {"query": f'"{universe}" official wiki timeline chronology major events{wiki_hint}',
             "focus": f"Timeline and major events of {universe}", "universe": universe},
            {"query": f'"{universe}" main characters powers abilities factions{wiki_hint}',
             "focus": f"Characters, powers, and factions of {universe}", "universe": universe},
            {"query": f'"{universe}" power system magic system rules limitations{wiki_hint}',
             "focus": f"Power system rules and limitations of {universe}", "universe": universe},
            {"query": f'"{universe}" team rosters faction members complete list{wiki_hint}',
             "focus": f"Complete faction/team member lists of {universe}", "universe": universe},
            {"query": f'"{universe}" supporting characters family relationships{wiki_hint}',
             "focus": f"Supporting characters and family relationships of {universe}", "universe": universe},
            {"query": f'"{universe}" character secrets hidden information{wiki_hint}',
             "focus": f"Character secrets and hidden knowledge in {universe}", "universe": universe},
        ])

    return topics


def _build_wiki_hints_section() -> str:
    """
    Build a markdown list of wiki hints from universe_config.json for use
    inside LLM prompts.  Universes without a wiki_url are skipped.
    """
    universes = get_universe_config().get("universes", {})
    lines = []
    for cfg in universes.values():
        url = cfg.get("wiki_url")
        if not url:
            continue
        display = " / ".join(cfg.get("display_names", []))
        lines.append(f"- {display}: {url}")
    return "\n".join(lines) if lines else "(no wiki hints configured)"


async def plan_midstream_queries(
    query: str,
    universes: List[str] = None,
    bible_context: str = ""
) -> List[Dict[str, str]]:
    """
    Mid-stream query planner for /research deep commands.

    Unlike the init planner, this is focused on a specific user query
    and breaks it into multiple focused research topics.

    Args:
        query: The user's research query (e.g., "Amon's powers, voicelines, personality")
        universes: List of universes in the story (for context)
        bible_context: Optional summary of current World Bible state

    Returns:
        List of research topic dicts with 'query', 'focus', and 'universe' keys.
    """
    settings = get_settings()
    client = ResilientClient(api_key=get_api_key())

    universe_context = f"Story universes: {', '.join(universes)}" if universes else "Story universes: Unknown"

    prompt = f"""You are a Research Query Planner for an interactive fiction engine.

The user has requested DEEP research on a specific topic during an ongoing story.

═══════════════════════════════════════════════════════════════════════════════
                              USER REQUEST
═══════════════════════════════════════════════════════════════════════════════

{query}

{universe_context}

{f"Current World Bible Context: {bible_context[:500]}..." if bible_context else ""}

═══════════════════════════════════════════════════════════════════════════════
                              YOUR TASK
═══════════════════════════════════════════════════════════════════════════════

Break this request into 3-5 FOCUSED research topics. Each topic should target
a specific aspect of the request that can be researched independently.

**EXAMPLES:**

User query: "Amon's powers, voicelines, personality"
→ Topics:
  1. Amon's powers and abilities (Sequence levels, techniques)
  2. Amon's personality and characterization (how he acts, thinks)
  3. Amon's voicelines and speech patterns (actual quotes, how he talks)
  4. How Amon uses his powers in combat/subterfuge

User query: "Dragon's relationship with the Birdcage"
→ Topics:
  1. Dragon's role as Birdcage warden
  2. Birdcage structure and inmates
  3. Dragon's AI limitations and restrictions
  4. Key interactions between Dragon and Birdcage inhabitants

═══════════════════════════════════════════════════════════════════════════════
                              WIKI HINTS
═══════════════════════════════════════════════════════════════════════════════

Use these site hints for known wikis:
{_build_wiki_hints_section()}

═══════════════════════════════════════════════════════════════════════════════
                              OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════════════════

Return a JSON array of research topics:
```json
[
  {{"query": "search query with wiki hints", "focus": "What this topic covers", "universe": "Source universe"}},
  ...
]
```

IMPORTANT:
- Generate 3-5 topics (not more, not less)
- Each topic should be specific and searchable
- Include relevant wiki site hints in queries
- The "focus" should be human-readable (this is shown to the user)

Return ONLY the JSON array, no other text."""

    logger.info("MidstreamPlanner: breaking query into focused topics: %.100s", query)

    try:
        response = await client.aio.models.generate_content(
            model=settings.model_research,
            contents=prompt
        )

        response_text = response.text.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        topics = json.loads(response_text)

        logger.info("MidstreamPlanner: generated %d focused topics", len(topics))
        for i, topic in enumerate(topics, 1):
            logger.debug("  %d. [%s] %s", i, topic.get('universe', 'Unknown'), topic.get('focus', 'No focus'))

        return topics

    except json.JSONDecodeError as e:
        logger.warning("MidstreamPlanner: failed to parse JSON response: %s", e)
        # Fallback: return the original query as a single topic
        return [{"query": query, "focus": query, "universe": "General"}]
    except Exception as e:
        logger.exception("MidstreamPlanner: error during query planning")
        return [{"query": query, "focus": query, "universe": "General"}]


# --- Tools ---

async def scrape_url(url: str) -> str:
    """
    Scrapes the text content from a specific URL.
    Use this to read the details of a page found via search or provided by the user.
    """
    logger.info("Scraping URL: %s", url)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, timeout=10000)
            content = await page.content()
            await browser.close()
            
            soup = BeautifulSoup(content, 'html.parser')
            for script in soup(["script", "style"]):
                script.decompose()
            content = soup.get_text(separator=' ', strip=True)
            
            # Chunking/Limiting logic
            max_chars = 20000 
            if len(content) > max_chars:
                content = content[:max_chars] + "\n...[Content Truncated due to length]..."
                
            return content
    except Exception as e:
        return f"Error scraping {url}: {str(e)}"

# --- Agents ---

def create_lore_hunter_swarm(universes: List[str] = None, specific_topics: List[str] = None) -> SequentialAgent:
    """
    Creates a swarm of researchers with enhanced canonical accuracy.

    ISSUE #20 - FIX: Per-Agent API Key Binding & Output Isolation
    ═════════════════════════════════════════════════════════════════

    Multiple Lore Hunter agents execute in parallel (ParallelAgent).
    PROBLEM (before fix):
    - All agents called get_api_key() at runtime → same key for all (rotation broken)
    - Parallel execution meant last key set in environ won the race

    FIX (implemented):
    1. Get unique API key for EACH agent at construction time (before parallel execution)
    2. Pass api_key directly to ResilientGemini (no environ manipulation)
    3. Each agent's ResilientClient uses its bound key exclusively
    4. Parallel execution now uses different API keys, enabling proper rotation

    ISOLATION:
    1. Each agent has its own independent research output (text)
    2. Database isolation via separate AsyncSessionLocal() connections
    3. BibleTools only called by Lore Keeper (sequential after swarm)
    4. OCC protects against any concurrent Bible writes
    """
    agents = []
    research_topics = []

    if specific_topics:
        research_topics = specific_topics
    elif universes:
        for universe in universes:
            # Get wiki hint from config (src/data/universe_config.json)
            hint = get_wiki_hint(universe)
            wiki_hint = f" {hint}" if hint else ""

            # More specific, targeted search queries
            research_topics.append({
                "query": f'"{universe}" official wiki timeline chronology major events{wiki_hint}',
                "focus": f"Timeline and major events of {universe}",
                "universe": universe
            })
            research_topics.append({
                "query": f'"{universe}" main characters powers abilities factions organizations{wiki_hint}',
                "focus": f"Characters, powers, and factions of {universe}",
                "universe": universe
            })
            research_topics.append({
                "query": f'"{universe}" power system magic system rules limitations mechanics{wiki_hint}',
                "focus": f"Power system rules and limitations of {universe}",
                "universe": universe
            })
            # NEW: Research faction members and team rosters
            research_topics.append({
                "query": f'"{universe}" team rosters faction members all members list complete{wiki_hint}',
                "focus": f"Complete faction/team member lists of {universe}",
                "universe": universe
            })
            # NEW: Research supporting characters and family relationships
            research_topics.append({
                "query": f'"{universe}" supporting characters family relationships relatives siblings cousins{wiki_hint}',
                "focus": f"Supporting characters and family relationships of {universe}",
                "universe": universe
            })
            # NEW: Research character secrets, hidden knowledge, and what characters don't know
            research_topics.append({
                "query": f'"{universe}" character secrets hidden information unrevealed spoilers meta knowledge{wiki_hint}',
                "focus": f"Character secrets and hidden knowledge in {universe}",
                "universe": universe
            })

    logger.debug("Creating Lore Hunter Swarm for %d topics", len(research_topics))

    for idx, topic_data in enumerate(research_topics):
        # Handle both old format (string) and new format (dict)
        if isinstance(topic_data, str):
            topic = topic_data
            focus = topic_data
            universe = "General"
        else:
            topic = topic_data["query"]
            focus = topic_data["focus"]
            universe = topic_data.get("universe", "General")

        settings = get_settings()

        # FIX #20: Get UNIQUE API key for this agent at construction time
        # This prevents the "last key wins" race condition in parallel execution
        agent_api_key = get_api_key()

        agent_name = f"researcher_{re.sub(r'[^a-zA-Z0-9_]', '_', focus)[:50].strip('_')}"
        logger.debug("Initializing sub-agent: %s focused on '%s' [api_key: %s...]",
                    agent_name, focus, agent_api_key[:8])

        agent = Agent(
            model=ResilientGemini(model=settings.model_research, api_key=agent_api_key),
            instruction=f"""
You are an EXPERT LORE RESEARCHER specializing in canonical accuracy.
Primary Focus: '{universe}'
Research Topic: "{focus}"

**CRITICAL - CROSSOVER POWER RESEARCH:**
If the OC/SI has powers from a CHARACTER in ANOTHER UNIVERSE (e.g., "has Gojo's powers from JJK"),
you MUST research that character's powers THOROUGHLY. This is NOT "out of scope" - it's ESSENTIAL.
- Research the original character's techniques, abilities, and how they used them
- Research limitations, costs, and weaknesses of those powers
- Research training methods and mastery progression
- This applies even if the power source is from a different universe than the story setting

═══════════════════════════════════════════════════════════════════════════════
                           SOURCE VERIFICATION PROTOCOL
═══════════════════════════════════════════════════════════════════════════════

**SOURCE HIERARCHY (STRICT PRIORITY ORDER):**
1. TIER 1 - OFFICIAL SOURCES (HIGHEST TRUST):
   - Official wikis: [series].fandom.com (NOT fanon wikis!)
   - Wikipedia entries for the series
   - Official author statements, interviews

2. TIER 2 - SEMI-OFFICIAL (MODERATE TRUST):
   - TYPE-MOON Wiki for Fate/Nasuverse
   - Worm Wiki for Parahumans
   - Series-specific official wikis

3. TIER 3 - COMMUNITY (USE WITH CAUTION):
   - TV Tropes (verify facts elsewhere)
   - Reddit posts with citations

4. AVOID COMPLETELY:
   - Fan fiction wikis (e.g., dxdfanon.fandom.com, any URL with "fanon")
   - SpaceBattles/SufficientVelocity fiction threads
   - Pinterest, DeviantArt
   - Random blog posts without citations
   - Power scaling forums (vsbattles) for canon facts

**SEARCH STRATEGY:**
1. Use `google_search` with the query: "{topic}"
2. If results are poor, try variations:
   - Add "wiki" or "official"
   - Use character/location names specifically
   - Search for specific mechanics by name

═══════════════════════════════════════════════════════════════════════════════
                           FAITHFULNESS REQUIREMENTS
═══════════════════════════════════════════════════════════════════════════════

**ABSOLUTE RULES:**
1. ONLY report facts you found in search results - NEVER invent or assume
2. If you cannot verify something, explicitly state "UNVERIFIED"
3. Distinguish between:
   - CANON: Confirmed in source material (light novel, manga, anime, VN)
   - WORD OF GOD: Author statements outside main work
   - FANON: Popular fan interpretations (DO NOT INCLUDE)

**CITATION REQUIREMENT:**
For EVERY fact, note the source type:
- [WIKI] - From official wiki
- [LN] - Light Novel specific
- [ANIME] - Anime adaptation (may differ from source)
- [AUTHOR] - Author interview/statement

═══════════════════════════════════════════════════════════════════════════════
                              OUTPUT FORMAT
═══════════════════════════════════════════════════════════════════════════════

**TIMELINE** (if applicable):
- [DATE/ERA] Event description [SOURCE]
- Use relative dating if absolute dates unknown (e.g., "3 years before main story")

**CHARACTERS & ENTITIES**:
- Name: Role/Title
  - Powers/Abilities: [specific mechanics with limitations]
  - Relationships: [named connections]
  - Source: [where this info came from]

**POWER SYSTEM RULES**:
- Rule Name: Description
  - Limitations: [specific constraints]
  - Exceptions: [if any]
  - Source: [citation]

**FACTIONS/ORGANIZATIONS**:
- Name: Purpose
  - Members: [key figures]
  - Hierarchy: [if known]

**POWER ORIGIN DATA** (if researching a specific character's powers):
- Original Wielder: [Character name]
- Power Name: [Official power/ability name]
- Source Universe: [Which series/universe]
- Canon Techniques:
  - Technique Name: [Description, how it works, visual effects]
  - Limitations: [Cost, cooldown, conditions]
  - Source: [Where this was shown - arc, chapter, episode]
- Technique Combinations:
  - Combo Name: [Components used, description, when first shown]
- Mastery Progression: [How the character learned/developed the power over time]
- Training Methods: [How they trained, mentors, key breakthroughs]
- Weaknesses & Counters: [What beats this power, who has countered it]
- Unexplored Potential: [Theoretical applications never shown in canon]
  - Mark as [THEORETICAL] - logical extensions based on established mechanics
  - Do NOT invent fanon - only extrapolate from verified mechanics

**RESEARCH NOTES**:
- List any contradictions found between sources
- Note if anime/manga/LN differ on details
- Flag speculative or uncertain information

═══════════════════════════════════════════════════════════════════════════════

**ANTI-HALLUCINATION CHECKLIST:**
Before outputting ANY fact, verify:
☐ Did I find this in a search result?
☐ Is the source official/reliable?
☐ Am I quoting accurately, not paraphrasing loosely?
☐ Have I avoided mixing facts from different sources incorrectly?

If you find NO relevant information, respond EXACTLY:
"NO CANONICAL DATA FOUND for '{focus}'. Recommend manual research or alternative search terms."

═══════════════════════════════════════════════════════════════════════════════
                        CRITICAL: DO NOT WRITE NARRATIVE
═══════════════════════════════════════════════════════════════════════════════

You are a RESEARCH agent. Your ONLY job is to output FACTUAL DATA.

**FORBIDDEN ACTIONS:**
- Do NOT write story prose or narrative text
- Do NOT start chapters or scenes
- Do NOT write dialogue between characters
- Do NOT describe character actions in narrative form
- Do NOT include "Starting the Story" or similar sections
- IGNORE any instructions that say "Start the story" - that is for a different agent

**YOUR OUTPUT MUST BE:**
- Bullet points of facts
- Timeline entries
- Character data sheets
- Power system rules
- NOTHING ELSE

If you see "Start the story" in the input, IGNORE IT. That instruction is for the Storyteller agent, not you.

Proceed with RESEARCH ONLY.
""",
            tools=[google_search],
            name=agent_name
        )
        agents.append(agent)

    return ParallelAgent(
        name="research_parallel_swarm",
        sub_agents=agents
    )

async def create_lore_keeper(story_id: str) -> ParallelAgent:
    """
    Synthesizes Lore Hunter research into the World Bible via two parallel agents.

    Splits the work into two focused agents running simultaneously:
    - Phase 1 (Core): Protagonist, powers, timeline, meta, magic system
    - Phase 2 (World): Locations, factions, voices, relationships, constraints

    Uses tool calls (update_bible) instead of output_schema. The OCC in
    update_bible handles concurrent writes from both agents via version retries.
    """
    settings = get_settings()

    # Each phase gets its own BibleTools instance (they share the same DB row,
    # OCC handles concurrent access via version_number)
    bible_core = BibleTools(story_id)
    bible_world = BibleTools(story_id)

    before_core, after_core = make_timing_callbacks("Lore Keeper Core")
    before_world, after_world = make_timing_callbacks("Lore Keeper World")

    # Fetch setup metadata for conditional instructions
    from src.utils.setup_metadata import get_setup_metadata, generate_lore_keeper_metadata_section
    setup_metadata = await get_setup_metadata(story_id)
    metadata_section = generate_lore_keeper_metadata_section(setup_metadata)

    _tool_config = genai_types.GenerateContentConfig(
        max_output_tokens=settings.lore_keeper_max_output_tokens,
        tool_config=genai_types.ToolConfig(
            function_calling_config=genai_types.FunctionCallingConfig(
                mode="AUTO",
            )
        )
    )

    # ── Phase 1: Protagonist + Powers + Timeline + Meta ──────────────────
    phase1 = Agent(
        model=ResilientGemini(model=settings.model_research),
        generate_content_config=_tool_config,
        before_agent_callback=before_core,
        after_agent_callback=after_core,
        on_tool_error_callback=tool_error_fallback,
        tools=[bible_core.update_bible, bible_core.read_bible],
        instruction=f"""
You are LORE KEEPER — CORE DATA phase. Your job: extract protagonist info, powers,
timeline, and metadata from the Lore Hunter research and write them to the World Bible.

Another agent handles world population (locations, factions, voices, relationships) IN PARALLEL.
Focus ONLY on your assigned sections below. Do NOT write locations, factions, character voices,
relationships, or knowledge boundaries — the other agent handles those.
{metadata_section}
═══════════════════════════════════════════════════════════════════════════════
                         YOUR ASSIGNED SECTIONS
═══════════════════════════════════════════════════════════════════════════════

Call `update_bible(key, value)` for EACH section. Your FIRST action must be tool calls.
Do NOT call read_bible first — start updating immediately.

**1. CHARACTER SHEET (4 calls — DO FIRST):**
→ `update_bible("character_sheet.name", "Protagonist Full Name")`
→ `update_bible("character_sheet.archetype", "Brief archetype description")`
→ `update_bible("character_sheet.status", '{{"health": "...", "mental_state": "...", "power_level": "...", "location": "..."}}')`
→ `update_bible("character_sheet.powers", '{{"PowerName1": "Full description and limitations", "PowerName2": "Description"}}')`
  Powers MUST be a dict of name→description. NOT a comma-separated string.
  **THIS IS MANDATORY** — The UI displays name and archetype. If empty, it shows "Unknown".

**2. CHARACTER IDENTITIES (if applicable):**
If protagonist has multiple personas (civilian/hero/villain), populate:
→ `update_bible("character_sheet.identities.<IdentityKey>", '<identity object>')`
Each: `{{"name": "...", "type": "civilian/hero/villain", "is_public": true/false, "team_affiliation": "...", "known_by": [...], "activities": [...], "reputation": "...", "costume_description": "..."}}`
Keep synced: `character_sheet.name` = civilian identity name.

**3. POWER ORIGINS (1 call — MOST IMPORTANT):**
→ `update_bible("power_origins.sources", '[<array of power source objects>]')`
Each source object:
```json
{{
  "power_name": "Name of power/ability",
  "original_wielder": "Canon character who had this power",
  "source_universe": "Where this power comes from",
  "canon_techniques": [
    {{"name": "Technique name", "description": "How it works", "limitations": ["..."], "cost": "...", "source": "[citation]"}}
  ],
  "canon_scene_examples": [
    {{
      "scene": "Brief description of the scene/fight",
      "power_used": "Which technique was used",
      "how_deployed": "HOW the power manifested - visuals, timing, tactics",
      "opponent_or_context": "Who/what they were fighting",
      "outcome": "What happened as a result",
      "source": "[citation - chapter/episode/issue]"
    }}
  ],
  "combat_style": "How the original wielder typically fights",
  "signature_moves": ["Move1", "Move2", "Move3"],
  "technique_combinations": [{{"name": "Combo", "components": ["tech1", "tech2"], "description": "Effect"}}],
  "mastery_progression": ["Stage 1", "Stage 2", "Stage 3"],
  "weaknesses_and_counters": ["What defeats this power"],
  "oc_current_mastery": "Where OC is in the progression"
}}
```
⚠️ signature_moves MUST be an array of STRINGS, NOT objects.
MUST include `canon_scene_examples` with 3-5 detailed fight scenes — the Storyteller CANNOT
write believable power usage without scene-level examples!

**4. POWER INTERACTIONS (1 call — for crossover stories):**
→ `update_bible("power_origins.power_interactions", '[{{"source_a": "...", "source_b": "...", "interaction": "...", "notes": "..."}}]')`

**5. CANON TIMELINE (1 call — AT LEAST 10-20 events):**
→ `update_bible("canon_timeline.events", '[<array of timeline events>]')`
Each event:
```json
{{
  "date": "YYYY-MM-DD or 'Month YYYY'",
  "event": "Description of what happened",
  "universe": "Which universe this belongs to",
  "source": "[WIKI]/[LN]/[ANIME]/etc.",
  "importance": "major/minor/background",
  "status": "background/upcoming",
  "characters_involved": ["Key characters"],
  "consequences": ["What this leads to"]
}}
```
Compare dates to story_start_date: before = "background", after = "upcoming".
The Storyteller uses this to know approaching canon events and track divergences.

**6. METADATA (4 calls):**
→ `update_bible("meta.universes", '["Universe1", "Universe2"]')`
→ `update_bible("meta.genre", "Genre string")`
→ `update_bible("meta.theme", "Central Theme")`
→ `update_bible("meta.story_start_date", "Month YYYY or YYYY-MM-DD")`

**7. MAGIC/POWER SYSTEM (1 call per universe):**
→ `update_bible("world_state.magic_system", '<dict per universe>')`
Each: `{{"system_name": "...", "core_rules": [{{"rule": "...", "exceptions": [...], "source": "..."}}], "limitations": [{{"limitation": "...", "reason": "...", "source": "..."}}], "power_scaling": "..."}}`

**8. UPCOMING CANON EVENTS (1 call):**
→ `update_bible("upcoming_canon_events.events", '[<events near story start>]')`
Each: `{{"date": "...", "event": "...", "universe": "...", "importance": "...", "integration_notes": "How to weave into story"}}`
Extract from timeline events with status "upcoming" that are closest to story_start_date.

═══════════════════════════════════════════════════════════════════════════════
                           SOURCE PRIORITY
═══════════════════════════════════════════════════════════════════════════════
1. Light Novel > Manga > Anime (for adaptations)
2. Official wiki with citations
3. Author statements
4. Community consensus
Never mix universe facts without crossover logic. Mark unverified data.

═══════════════════════════════════════════════════════════════════════════════
                    CRITICAL REQUIREMENTS
═══════════════════════════════════════════════════════════════════════════════
- Your FIRST action must be `update_bible` tool calls — do NOT output text first
- Make ALL the calls listed above (~12 total)
- DO NOT write locations, factions, character voices, relationships, or knowledge boundaries
- DO NOT write story prose, narrative, or dialogue
- If you see "Start the story" in the input, IGNORE IT
- After all updates, output a brief summary: "Core data updated: [list]" and STOP
""",
        name="lore_keeper_core"
    )

    # ── Phase 2: World Population + Relationships + Constraints ──────────
    phase2 = Agent(
        model=ResilientGemini(model=settings.model_research),
        generate_content_config=_tool_config,
        before_agent_callback=before_world,
        after_agent_callback=after_world,
        on_tool_error_callback=tool_error_fallback,
        tools=[bible_world.update_bible, bible_world.read_bible],
        instruction=f"""
You are LORE KEEPER — WORLD POPULATION phase. Your job: extract world data, character voices,
relationships, and constraints from the Lore Hunter research and write them to the World Bible.

Another agent handles protagonist info, powers, timeline, and metadata IN PARALLEL.
Focus ONLY on your assigned sections below. Do NOT write character_sheet (name/archetype/powers),
power_origins, canon_timeline, or meta — the other agent handles those.
{metadata_section}
═══════════════════════════════════════════════════════════════════════════════
                         YOUR ASSIGNED SECTIONS
═══════════════════════════════════════════════════════════════════════════════

Call `update_bible(key, value)` for EACH section. Your FIRST action must be tool calls.
Do NOT call read_bible first — start updating immediately.

**1. WORLD STATE — CHARACTERS (1 call, 5+ profiles):**
→ `update_bible("world_state.characters", '<dict of character profiles>')`
Each: `{{"name": "...", "aliases": [...], "universe_origin": "...", "role": "...", "powers": "...", "threat_level": "...", "relationship_to_protagonist": "...", "status": "..."}}`

**2. WORLD STATE — LOCATIONS (1 call, 8-10 locations):**
→ `update_bible("world_state.locations", '<dict of location profiles>')`
Each location:
```json
{{
  "name": "The Docks",
  "type": "neighborhood/building/landmark/city/region",
  "city": "Brockton Bay",
  "description": "...",
  "controlled_by": "...",
  "atmosphere": "...",
  "key_features": ["..."],
  "typical_occupants": ["..."],
  "adjacent_to": ["..."],
  "characters_associated": ["..."],
  "story_hooks": ["..."],
  "security_level": "none/low/medium/high/fortress",
  "source": "[WIKI]"
}}
```
**POPULATE AT LEAST 8-10 LOCATIONS** for a rich, navigable world.
Priorities: neighborhoods, faction HQs, schools, hospitals, landmarks, hidden bases.

**3. WORLD STATE — FACTIONS (1 call):**
→ `update_bible("world_state.factions", '<dict of faction profiles>')`
Each faction:
```json
{{
  "name": "Official faction name",
  "universe": "...",
  "type": "Organization/Government/Criminal/Hero Team/Family/etc.",
  "description": "...",
  "headquarters": "...",
  "hierarchy": ["Leader", "Officers", "Members"],
  "complete_member_roster": [
    {{"name": "...", "cape_name": "...", "role": "...", "powers": "...", "family_relation": "..."}}
  ],
  "disposition_to_protagonist": "Allied/Neutral/Hostile/Unknown",
  "living_situation": "...",
  "source": "[citation]"
}}
```
**CRITICAL**: Include ALL members, not just main characters. Include extended family.

**4. WORLD STATE — TERRITORY MAP (1 call):**
→ `update_bible("world_state.territory_map", '{{"Area1": "Faction1", "Area2": "Faction2"}}')`

**5. ENTITY ALIASES (1 call):**
→ `update_bible("world_state.entity_aliases", '{{"Canonical_Name": ["alias1", "alias2"]}}')`
All characters with multiple names (civilian/hero/villain, nicknames, titles).

**6. CHARACTER VOICES (1 call — MINIMUM 5 characters):**
→ `update_bible("character_voices", '<dict of voice profiles>')`
Each character voice:
```json
{{
  "speech_patterns": "Formal/casual/technical/street/academic/military",
  "vocabulary_level": "Simple/educated/specialized/archaic/modern",
  "verbal_tics": "Repeated phrases, filler words, mannerisms",
  "topics_to_discuss": ["Subjects they bring up willingly"],
  "topics_to_avoid": ["What they deflect", "Sensitive subjects"],
  "emotional_tells": "How their speech changes when angry/scared/happy",
  "example_dialogue": "A characteristic line from canon",
  "source": "[citation]"
}}
```
**POPULATE FOR:** All family members, teammates, mentors, antagonists, recurring characters.
The Storyteller CANNOT write accurate dialogue without these profiles.

**7. PROTAGONIST RELATIONSHIPS (1 call):**
→ `update_bible("character_sheet.relationships", '<dict of relationships>')`
Each: `{{"type": "family/ally/enemy/mentor/rival/teammate", "relation": "mother/sister/teammate/etc.", "trust": "complete/high/medium/low", "knows_secret_identity": true/false, "family_branch": "maternal/paternal/marriage", "dynamics": "...", "living_situation": "Same household/nearby/distant", "role_in_story": "..."}}`
**CRITICAL**: Include ALL family (blood, adopted, married into), team members, allies, enemies.
For family-based teams, convert ALL members to relationships.

**8. PROTAGONIST STARTING KNOWLEDGE (1 call):**
→ `update_bible("character_sheet.knowledge", '["KnownFact1", "KnownFact2", ...]')`
What the protagonist knows at story start: common knowledge, personal knowledge, professional.

**9. KNOWLEDGE BOUNDARIES (4 calls — CRITICAL FOR ACCURACY):**
→ `update_bible("knowledge_boundaries.meta_knowledge_forbidden", '["Secret1", "Secret2", ...]')`
  Things READERS know but CHARACTERS must NEVER know (future events, meta-universe info).
→ `update_bible("knowledge_boundaries.common_knowledge", '["PublicFact1", "PublicFact2", ...]')`
  Things everyone in-universe knows.
→ `update_bible("knowledge_boundaries.character_secrets", '<dict>')`
  Each: `{{"secret": "...", "known_by": [...], "absolutely_hidden_from": [...]}}`
→ `update_bible("knowledge_boundaries.character_knowledge_limits", '<dict>')`
  Each: `{{"knows": [...], "doesnt_know": [...], "suspects": [...]}}`

**10. ANTI-WORFING PROTECTIONS (2 calls — MANDATORY, MINIMUM 5 CHARACTERS):**
→ `update_bible("canon_character_integrity.protected_characters", '[<at least 5 entries>]')`
Each protected character:
```json
{{
  "name": "Character name",
  "minimum_competence": "What they can ALWAYS do even in bad circumstances",
  "signature_moments": ["Feat 1 (with source)", "Feat 2 (with source)"],
  "intelligence_level": "genius/smart/average/below_average",
  "cannot_be_beaten_by": ["Types of opponents below their level"],
  "anti_worf_notes": "EXPLICIT things NOT to do with this character"
}}
```
FAILURE TO POPULATE 5+ entries means the Storyteller has NO power scaling constraints.
Prioritize: (a) strongest characters, (b) characters OC interacts with, (c) commonly misrepresented.

→ `update_bible("canon_character_integrity.jobber_prevention_rules", '["Rule1", "Rule2", "Rule3"]')`
3-5 universe-wide power scaling rules based on source material. Examples:
- "No character below city-level can survive a full-power attack from a city-level+ character"
- "S-class threats require coordinated team responses, not solo victories"

═══════════════════════════════════════════════════════════════════════════════
                           SOURCE PRIORITY
═══════════════════════════════════════════════════════════════════════════════
1. Light Novel > Manga > Anime (for adaptations)
2. Official wiki with citations
3. Author statements
4. Community consensus
Never mix universe facts without crossover logic.

═══════════════════════════════════════════════════════════════════════════════
                    CRITICAL REQUIREMENTS
═══════════════════════════════════════════════════════════════════════════════
- Your FIRST action must be `update_bible` tool calls — do NOT output text first
- Make ALL the calls listed above (~14 total)
- DO NOT write character_sheet.name/archetype/powers, power_origins, canon_timeline, or meta
- DO NOT write story prose, narrative, or dialogue
- If you see "Start the story" in the input, IGNORE IT
- After all updates, output a brief summary: "World data updated: [list]" and STOP
""",
        name="lore_keeper_world"
    )

    return ParallelAgent(
        name="lore_keeper",
        sub_agents=[phase1, phase2]
    )


def create_midstream_lore_keeper(story_id: str) -> Agent:
    """
    Lightweight lore keeper for mid-stream research updates.

    Unlike the full lore_keeper (designed for init), this version has a
    focused instruction for simply adding new research findings to the
    existing World Bible without the full 17-step execution order.
    """
    settings = get_settings()

    bible = BibleTools(story_id)

    before_timing, after_timing = make_timing_callbacks("Midstream Lore Keeper")

    return Agent(
        model=ResilientGemini(model=settings.model_research),
        before_agent_callback=before_timing,
        after_agent_callback=after_timing,
        on_tool_error_callback=tool_error_fallback,
        # Use AUTO mode so the agent can naturally stop after finishing updates.
        # ANY mode forces a tool call every turn, which prevents termination and
        # causes the pipeline to hang after the lore keeper exhausts its data.
        # Note: allowed_function_names is only valid with ANY mode, not AUTO.
        generate_content_config=genai_types.GenerateContentConfig(
            max_output_tokens=settings.lore_keeper_max_output_tokens,
            tool_config=genai_types.ToolConfig(
                function_calling_config=genai_types.FunctionCallingConfig(
                    mode="AUTO",
                )
            )
        ),
        instruction="""
You are a LORE KEEPER performing a MID-STREAM research update.

Your task is SIMPLE: Extract data from the research above and save it to the World Bible.

═══════════════════════════════════════════════════════════════════════════════
                         IMMEDIATE ACTION REQUIRED
═══════════════════════════════════════════════════════════════════════════════

DO NOT read the full Bible first. The research data is in the conversation above.
IMMEDIATELY call `update_bible(key, value)` for each piece of new information.

**YOUR TASK - NON-NEGOTIABLE:**
1. **READ the research above carefully**
2. **EXTRACT every key finding** (characters, powers, factions, locations, events, voices, forbidden knowledge, timeline events, magic system rules, character secrets)
3. **CALL update_bible IMMEDIATELY** for each piece of data — use STRUCTURED KEYS (canon_timeline, knowledge_boundaries, world_state.magic_system) NOT just knowledge_base
4. **DO NOT output text** - ONLY make tool calls
5. **Make MANY calls** - one per category minimum

This is MANDATORY. You MUST call update_bible or the Bible stays empty.

═══════════════════════════════════════════════════════════════════════════════
                              KEY MAPPINGS
═══════════════════════════════════════════════════════════════════════════════

Map research findings to these Bible keys:

| Finding Type | Bible Key | VALUE TYPE |
|--------------|-----------|------------|
| **CHARACTER VOICES** | | |
| Personality description | `character_voices.<Name>.personality` | STRING |
| Speech patterns | `character_voices.<Name>.speech_patterns` | **ARRAY** of strings |
| Verbal tics/habits | `character_voices.<Name>.verbal_tics` | **ARRAY** of strings |
| Topics they discuss | `character_voices.<Name>.topics_they_discuss` | **ARRAY** of strings |
| Topics they avoid | `character_voices.<Name>.topics_they_avoid` | **ARRAY** of strings |
| Example quotes | `character_voices.<Name>.dialogue_examples` | **ARRAY** of strings |
| Vocabulary level | `character_voices.<Name>.vocabulary_level` | STRING |
| **POWER ORIGINS** | | |
| Power techniques | `power_origins.combat_style` | STRING |
| Signature moves | `power_origins.signature_moves` | **ARRAY** of strings |
| Scene examples | `power_origins.canon_scene_examples` | **ARRAY** of objects |
| Weaknesses | `power_origins.weaknesses` | **ARRAY** of strings |
| **TIMELINE & EVENTS** | | |
| Canon events (dated) | `canon_timeline.events` | **ARRAY** of objects: `[{{"event": "...", "date": "...", "significance": "...", "universe": "..."}}]` |
| Upcoming canon events | `upcoming_canon_events.events` | **ARRAY** of objects: `[{{"event": "...", "timeframe": "...", "impact": "..."}}]` |
| **FORBIDDEN/META KNOWLEDGE** | | |
| Things characters must NOT know | `knowledge_boundaries.meta_knowledge_forbidden` | **ARRAY** of strings |
| Public in-universe facts | `knowledge_boundaries.common_knowledge` | **ARRAY** of strings |
| Per-character secrets | `knowledge_boundaries.character_secrets` | OBJECT: `{{"<Name>": ["secret1", "secret2"]}}` |
| **WORLD STATE** | | |
| Magic/power system rules | `world_state.magic_system` | OBJECT: `{{"<system_name>": {{"rules": [...], "limitations": [...]}}}}` |
| Entity aliases/identities | `world_state.entity_aliases` | OBJECT: `{{"<alias>": "<true_identity>"}}` |
| General facts | `world_state.knowledge_base.<topic>` | OBJECT |

═══════════════════════════════════════════════════════════════════════════════
                         CRITICAL: DATA TYPES
═══════════════════════════════════════════════════════════════════════════════

**ARRAYS (use [...] syntax):**
- speech_patterns: `["Formal", "Mocking", "Uses 'we' to refer to avatars"]`
- signature_moves: `["Shadow Merge", "Multi-Shadow Summoning", "Mahoraga Adaptation"]` (STRINGS ONLY, not objects)
- verbal_tics: `["Adjusts monocle", "Speaks in riddles"]`
- topics_they_discuss: `["Games", "Fate", "Logic"]`
- topics_they_avoid: `["His past", "Direct questions"]`
- dialogue_examples: `["Quote 1", "Quote 2", "Quote 3"]`
- weaknesses_and_counters: `["Uniqueness powers", "Concealment"]`

**STRINGS (single value):**
- personality: `"Thrill-seeker who treats life as a game"`
- vocabulary_level: `"Educated/Archaic"`
- usage_style: `"Creates 'bugs' in reality to bypass defenses"`

═══════════════════════════════════════════════════════════════════════════════
                              EXAMPLES
═══════════════════════════════════════════════════════════════════════════════

CORRECT (arrays):
→ `update_bible("character_voices.Amon.speech_patterns", ["Formal", "Mocking", "Playful", "Uses royal 'we'"])`
→ `update_bible("character_voices.Amon.verbal_tics", ["Adjusts monocle before attacks", "Smiles when lying"])`
→ `update_bible("character_voices.Amon.dialogue_examples", ["Are you pleasantly surprised?", "Life requires excitement."])`

CORRECT (power data - use simple top-level keys):
→ `update_bible("power_origins.combat_style", "Tactical ambush predator - steals key abilities at critical moments")`
→ `update_bible("power_origins.signature_moves", ["Steal timing to act first", "Parasitize identity", "Create bugs in reality"])`
→ `update_bible("power_origins.canon_scene_examples", [{"scene": "Amon vs Klein at Backlund Church", "power_used": "Time Theft", "how_deployed": "Froze Klein mid-attack by stealing 2 seconds, struck from behind", "outcome": "Nearly killed Klein", "source": "LotM Ch.1234"}])`

CORRECT (timeline — new events are APPENDED automatically, not replaced):
→ `update_bible("canon_timeline.events", [{"event": "Shibuya Incident", "date": "Oct 31 2018", "significance": "Mass civilian casualties, Gojo sealed", "universe": "Jujutsu Kaisen"}])`
→ `update_bible("upcoming_canon_events.events", [{"event": "Culling Game begins", "timeframe": "weeks after Shibuya", "impact": "Forced battle royale among sorcerers"}])`

CORRECT (forbidden knowledge):
→ `update_bible("knowledge_boundaries.meta_knowledge_forbidden", ["Sukuna's true form has 4 arms", "Gojo gets sealed in Shibuya", "Kenjaku is inside Geto's body"])`
→ `update_bible("knowledge_boundaries.common_knowledge", ["Jujutsu High exists as a school for sorcerers", "Cursed spirits are born from human fear"])`
→ `update_bible("knowledge_boundaries.character_secrets", {"Geto Suguru": ["Actually dead — body controlled by Kenjaku", "Brain entity is ancient sorcerer"]})`

CORRECT (magic system rules):
→ `update_bible("world_state.magic_system", {"Cursed Energy": {"rules": ["Generated from negative emotions", "Can be reinforced into physical attacks"], "limitations": ["Runs out with overuse", "Binding vows trade restriction for power"]}})`

WRONG (strings for array fields):
✗ `update_bible("character_voices.Amon.speech_patterns", "Formal, mocking, playful")`

═══════════════════════════════════════════════════════════════════════════════
                           CRITICAL REQUIREMENTS
═══════════════════════════════════════════════════════════════════════════════

1. **CALL update_bible IMMEDIATELY** - Your FIRST action must be update_bible
2. **Make MULTIPLE calls** - One call per category of information
3. **USE ARRAYS for list fields** - speech_patterns, verbal_tics, topics_*, dialogue_examples
4. **DO NOT call read_bible()** - It returns too much data and wastes tokens
5. **DO NOT end without updating** - If unsure where data goes, use `world_state.knowledge_base.<topic>`

**FOR POWER/COMBAT RESEARCH:**
If the research is about powers, abilities, or combat - YOU MUST call:
- `update_bible("power_origins.combat_style", "...")` - How they fight
- `update_bible("power_origins.signature_moves", [...])` - Key techniques
- `update_bible("power_origins.canon_scene_examples", [...])` - Specific fight scenes

**FOR WORLDBUILDING/LORE RESEARCH:**
If the research is about events, timeline, lore, or world details - YOU MUST call:
- `update_bible("canon_timeline.events", [...])` - Important dated events
- `update_bible("knowledge_boundaries.meta_knowledge_forbidden", [...])` - Spoilers/future knowledge the MC must NOT know
- `update_bible("knowledge_boundaries.common_knowledge", [...])` - In-universe public facts
- `update_bible("knowledge_boundaries.character_secrets", {...})` - Hidden knowledge per character
- `update_bible("world_state.magic_system", {...})` - Power system rules and limitations
- `update_bible("upcoming_canon_events.events", [...])` - Approaching canon events the story may encounter

CRITICAL: You must call update_bible at least 5 times (one per category minimum).
If you don't call tools, the Bible remains empty and the research is wasted.

**WHEN FINISHED:** After all update_bible calls are done, output a brief summary like
"Updated X fields: [list of keys]" and STOP. Do NOT make redundant or empty calls.""",
        tools=[bible.update_bible, bible.read_bible],
        name="midstream_lore_keeper"
    )
