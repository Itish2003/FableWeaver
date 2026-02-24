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

async def create_lore_keeper(story_id: str) -> Agent:
    """
    Synthesizes research into the initial JSON structure with enhanced validation.
    """
    settings = get_settings()

    bible = BibleTools(story_id)

    before_timing, after_timing = make_timing_callbacks("Lore Keeper")

    # Fetch setup metadata for conditional instructions
    from src.utils.setup_metadata import get_setup_metadata, generate_lore_keeper_metadata_section
    setup_metadata = await get_setup_metadata(story_id)
    metadata_section = generate_lore_keeper_metadata_section(setup_metadata)

    from src.schemas import LoreKeeperOutput

    return Agent(
        model=ResilientGemini(model=settings.model_research),
        before_agent_callback=before_timing,
        after_agent_callback=after_timing,
        on_tool_error_callback=tool_error_fallback,
        output_schema=LoreKeeperOutput,
        output_key="lore_keeper_output",
        instruction=f"""
You are the SUPREME LORE KEEPER - Guardian of Canonical Truth.
Your Mission: Consolidate research into a VERIFIED, CONSISTENT World Bible.

═══════════════════════════════════════════════════════════════════════════════
                    ⚠️  MANDATORY FIELDS - MUST POPULATE ⚠️
═══════════════════════════════════════════════════════════════════════════════

THESE FIELDS ARE REQUIRED. FAILURE TO POPULATE BLOCKS STORY GENERATION:
1. **character_sheet.name** - The protagonist's name (e.g., "Kudou Kageaki")
2. **character_sheet.archetype** - Brief archetype (e.g., "The Shadow Guardian")
3. **character_sheet.status** - At least {{health, mental_state, power_level}}
4. **power_origins.sources[0]** - Must include: canon_techniques (array of strings), combat_style (string), signature_moves (array of STRINGS ONLY - NOT objects)
5. **character_voices** - At least 5 key characters with speech_patterns, vocabulary_level, verbal_tics
6. **character_sheet_relationships** - Protagonist's family, team, and key relationship network

DO NOT PROCEED UNTIL YOU HAVE POPULATED ALL OF THE ABOVE.

═══════════════════════════════════════════════════════════════════════════════
                         INITIAL ASSESSMENT PROTOCOL
═══════════════════════════════════════════════════════════════════════════════

**STEP 1: READ CURRENT STATE**
First, use `read_bible` (no arguments) to see the ENTIRE current World Bible.
Understand what data already exists before making ANY changes.

**STEP 2: ANALYZE INCOMING RESEARCH**
For each piece of research from the Lore Hunters:
- Identify the SOURCE TAG ([WIKI], [LN], [ANIME], etc.)
- Check for "UNVERIFIED" or speculative markers
- Note any contradictions with existing Bible data

═══════════════════════════════════════════════════════════════════════════════
                          CONFLICT RESOLUTION RULES
═══════════════════════════════════════════════════════════════════════════════

When research CONFLICTS with existing Bible data, use this hierarchy:

**SOURCE PRIORITY (Highest to Lowest):**
1. Original source material (Light Novel > Manga > Anime for adaptations)
2. Official wiki with citations
3. Author statements (Word of God)
4. Existing Bible data (if no source given)
5. Community consensus

**CONFLICT HANDLING:**
- If new research has HIGHER priority source → UPDATE existing data
- If new research has LOWER priority source → KEEP existing data, add note
- If sources are EQUAL priority but CONTRADICTORY → Keep BOTH with notes
- If research is marked UNVERIFIED → DO NOT add to main data, add to "unverified_notes"

**UNIVERSE SEPARATION:**
- NEVER mix facts from different universes without explicit crossover logic
- Each universe's power system operates independently unless story specifies otherwise
- Mark crossover-specific rules under "crossover_mechanics"

═══════════════════════════════════════════════════════════════════════════════
                           OUTPUT FORMAT (LoreKeeperOutput JSON)
═══════════════════════════════════════════════════════════════════════════════

You MUST output a valid LoreKeeperOutput JSON object with these top-level fields:

**MAPPING OLD TOOL CALLS TO JSON OUTPUT:**
Replace the old approach of calling `update_bible` tools with these JSON fields:
- **character_name** → protagonist's name
- **character_archetype** → protagonist's archetype
- **character_status** → protagonist's initial status object
- **character_powers** → protagonist's powers as a dict (NOT string!)
- **power_origins_sources** → list of power origin objects
- **canon_timeline_events** → list of canonical timeline events
- **world_state_characters** → dict of character details
- **world_state_locations** → dict of location details
- **world_state_factions** → dict of faction details
- **meta_universes** → list of universes
- **meta_genre** → genre string
- **meta_theme** → theme string
- **meta_story_start_date** → story start date
- **knowledge_meta_knowledge_forbidden** → list of forbidden knowledge
- **knowledge_common_knowledge** → list of common knowledge
- **character_voices** → dict of character voice profiles
- **character_sheet_relationships** → dict of protagonist's relationships
- **character_sheet_knowledge** → list of things protagonist knows at start
- **canon_character_integrity_protected** → list of anti-Worfing character protections
- **knowledge_character_secrets** → dict of per-character secrets
- **knowledge_character_limits** → dict of per-character knowledge limits
- **upcoming_canon_events** → list of canon events approaching story start
- **power_interactions** → list of cross-power interaction rules
- **world_state_magic_system** → dict of power system rules per universe
- **world_state_entity_aliases** → dict of character name variants

**CANON TIMELINE EVENTS** (populate `canon_timeline_events` array):
Each timeline event should look like:
```json
{{
  "date": "YYYY-MM-DD or 'Month YYYY' or relative like '3 years before main story'",
  "event": "Description of what happened",
  "universe": "Which universe this belongs to",
  "importance": "major/minor/background",
  "status": "background/upcoming"
}}
```

**CRITICAL STATUS ASSIGNMENT:**
Compare each event's date to `story_start_date` (set in meta section):
- `status: "background"` → Events BEFORE story_start_date (history, world-building)
- `status: "upcoming"` → Events AFTER story_start_date (future plot points)

Example: If story_start_date is "April 2011":
- 1982: Scion appears → status: "background" (29 years before)
- May 2011: Leviathan attacks → status: "upcoming" (after story starts)

The Archivist will change status from "upcoming" to "occurred" as events happen in the story.

**CHARACTER FORMAT** (`world_state.characters.<CharacterName>`):
Structure should include: name, aliases, universe_origin, role, powers (with limitations),
relationships, status, and canon_accuracy fields.

**POWER SYSTEM FORMAT** (`world_state.magic_system.<UniverseName>`):
Structure should include: system_name, universe, core_rules (with exceptions and source),
limitations (with reason and source), and power_scaling info.

**FACTION FORMAT** (`world_state.factions.<FactionName>`):
```json
{{
  "name": "Official faction name",
  "universe": "Source universe",
  "type": "Organization/Government/Criminal/Hero Team/Family/etc.",
  "description": "Purpose and nature",
  "headquarters": "Where they operate from / live",
  "hierarchy": ["Leader", "Officers", "Members"],
  "complete_member_roster": [
    {{
      "name": "Member name",
      "cape_name": "Hero/Villain name if applicable",
      "role": "Leader/Member/Support",
      "powers": "Brief power description",
      "family_relation": "Relationship to other members if any",
      "typical_activities": "What they usually do (patrols, hospital, school, etc.)"
    }}
  ],
  "family_relationships": "Describe family connections between members",
  "disposition_to_protagonist": "Allied/Neutral/Hostile/Unknown",
  "living_situation": "Do they live together? Where?",
  "source": "[citation]"
}}
```
**CRITICAL**: For hero teams, villain groups, and family organizations:
- Include ALL members, not just main/popular characters
- Research the complete roster from official sources
- Include extended family members (cousins, aunts, uncles)
- Note who lives together and their daily routines

**LOCATION FORMAT** (`world_state.locations.<LocationName>`):
Locations are CRITICAL for grounded, immersive world-building. Research and populate ALL fields:
```json
{{
  "name": "The Docks",
  "type": "neighborhood/building/landmark/city/region",
  "city": "Brockton Bay",
  "description": "Industrial waterfront area, heavily damaged and largely abandoned after shipping industry collapse.",
  "controlled_by": "Contested (ABB, Merchants)",
  "atmosphere": "Gritty, dangerous, decaying industrial - rusted cranes, abandoned warehouses, smell of salt and decay",
  "key_features": [
    "Boat Graveyard - ship wreckage from economic collapse",
    "Abandoned warehouses used as gang hideouts",
    "Lord Street Market - outdoor market with gang presence"
  ],
  "typical_occupants": ["Dock workers", "Gang members", "Homeless", "Drug dealers"],
  "adjacent_to": ["Downtown", "Trainyard", "Boardwalk"],
  "characters_associated": ["Lung", "Oni Lee", "Skidmark", "Taylor Hebert"],
  "story_hooks": [
    "Frequent gang clashes - ideal for patrol encounters",
    "Hidden entrances to Coil's underground base",
    "Taylor's first cape fight location (vs Lung)"
  ],
  "canon_events_here": [
    {{"date": "April 2011", "event": "Taylor vs Lung", "status": "upcoming"}},
    {{"date": "May 2011", "event": "Leviathan destroys much of the Docks", "status": "upcoming"}}
  ],
  "current_state": "Normal/Damaged/Destroyed/Under construction",
  "security_level": "none/low/medium/high/fortress",
  "source": "[WIKI]"
}}
```
**POPULATE AT LEAST 8-10 LOCATIONS** for a rich, navigable world.

**TERRITORY MAP** (`world_state.territory_map`):
Quick reference for faction control - update when researching factions:
```json
{{
  "The Docks": "ABB/Merchants (contested)",
  "Downtown": "Neutral (PRT patrol zone)",
  "Boardwalk": "Commercial (protected)",
  "The Towers": "Empire Eighty-Eight",
  "Trainyard": "Merchants"
}}
```

**LOCATION RESEARCH PRIORITIES:**
1. Main city/setting neighborhoods and districts
2. Faction headquarters and territories
3. Key story locations (schools, hospitals, government buildings)
4. Landmarks and meeting points
5. Hidden locations (villain bases, secret hideouts)

**POWER ORIGINS FORMAT** (`power_origins.sources`):
When OC has powers from a specific canon character, structure as:
```json
{{
  "power_name": "Name of power/ability",
  "original_wielder": "Canon character who had this power",
  "source_universe": "Where this power comes from",
  "canon_techniques": [
    {{"name": "Technique name", "description": "How it works", "limitations": ["Cost constraint", "Cooldown or recharge time"], "cost": "Resource/energy cost", "source": "[citation]"}}
  ],
  "canon_scene_examples": [
    {{
      "scene": "Brief description of the scene/fight",
      "power_used": "Which power/technique was used",
      "how_deployed": "Detailed description of HOW the power manifested - visuals, timing, tactics",
      "opponent_or_context": "Who/what they were fighting or the situation",
      "outcome": "What happened as a result",
      "source": "[citation - chapter/episode/issue]"
    }}
  ],
  "combat_style": "How the original wielder typically fights - aggressive/defensive/tactical/ambush",
  "signature_moves": ["Shadow Merge", "Multi-Shadow Summoning", "Mahoraga Adaptation"],
  "technique_combinations": [
    {{"name": "Combo name", "components": ["tech1", "tech2"], "description": "Effect", "source": "[citation]"}}
  ],
  "mastery_progression": ["Stage 1", "Stage 2", "Stage 3..."],
  "training_methods": ["How original wielder trained"],
  "weaknesses_and_counters": ["What defeats this power"],
  "unexplored_potential": ["Theoretical extensions marked as [THEORETICAL]"],
  "oc_current_mastery": "Where OC is in the progression"
}}
```

**CHARACTER VOICE FORMAT** (`character_voices.<CharacterName>`):
For important canon characters OC will interact with - populate ALL fields:
```json
{{
  "speech_patterns": "Formal/casual/technical/street/academic/military",
  "vocabulary_level": "Simple/educated/specialized/archaic/modern",
  "verbal_tics": "Repeated phrases, filler words, mannerisms, speech habits",
  "topics_to_discuss": ["Subjects they bring up willingly", "Areas of expertise"],
  "topics_to_avoid": ["What they deflect", "Sensitive subjects", "Triggers"],
  "emotional_tells": "How their speech changes when angry/scared/happy",
  "example_dialogue": "A characteristic line from canon",
  "source": "[citation]"
}}
```
**POPULATE VOICES FOR:**
- All protagonist family members and teammates
- Major antagonists
- Key allies and mentors
- Recurring characters

**⚠️  WARNING: signature_moves FORMAT ⚠️**
signature_moves MUST be a simple array of STRINGS. DO NOT create objects.
```json
CORRECT:   "signature_moves": ["Shadow Merge", "Mahoraga Adaptation"]
WRONG:     "signature_moves": [{{"name": "Shadow Merge", "description": "..."}}]
```

**PROTAGONIST IDENTITIES** (`character_sheet.identities.<IdentityKey>`):
If protagonist has multiple personas (civilian, hero, vigilante, etc.), populate:
```json
{{
  "name": "Name/alias used for this identity",
  "type": "civilian/hero/villain/vigilante/undercover/informant",
  "is_public": true/false,
  "team_affiliation": "Team name if applicable",
  "known_by": ["Characters who know this identity exists"],
  "suspected_by": ["Characters who suspect but don't confirm"],
  "linked_to": ["Other identity keys this one is connected to"],
  "activities": ["What they do under this identity"],
  "public_perception": "How public/others view this identity",
  "reputation": "Hero/villain/unknown/mysterious/trusted/feared",
  "costume_description": "Physical appearance when using this identity",
  "base_of_operations": "Where they operate from as this identity",
  "cover_story": "The story that explains this identity if questioned",
  "vulnerabilities": ["How this identity could be compromised"]
}}
```
**CRITICAL**: If user describes OC with dual/multiple identities, populate ALL of them.

**FIELD SYNC**: When setting identities, keep these synchronized:
- `character_sheet.name` = `identities.civilian.name`
- `character_sheet.cape_name` = `identities.hero.name` (or primary hero identity)

**CANON CHARACTER INTEGRITY** (`canon_character_integrity.protected_characters`):
For major canon characters to prevent "Worfing":
```json
{{
  "name": "Character name",
  "minimum_competence": "What they can ALWAYS do",
  "signature_moments": ["Feats that define their power level"],
  "intelligence_level": "genius/smart/average/below_average",
  "cannot_be_beaten_by": ["Types of opponents below their level"],
  "anti_worf_notes": "Specific things NOT to do with this character"
}}
```

**PROTAGONIST RELATIONSHIPS** (`character_sheet.relationships.<CharacterName>`):
When researching family/team relationships, populate protagonist's personal relationships:
```json
{{
  "type": "family/ally/enemy/mentor/rival/romantic/teammate",
  "relation": "specific relation (mother, sister, cousin-in-law, team leader, etc.)",
  "trust": "complete/high/medium/low/hostile",
  "knows_secret_identity": true/false,
  "family_branch": "maternal/paternal/marriage (if family)",
  "dynamics": "Brief description of relationship dynamic",
  "living_situation": "Same household/nearby/distant",
  "role_in_story": "What role they play (mentor, confidant, liability, etc.)"
}}
```
**CRITICAL**: For family-based teams (like New Wave), convert ALL faction members to relationships:
- If protagonist is adopted into Dallon family → Carol, Mark, Victoria, Amy are family
- Extended family through marriage → Pelhams are cousins/aunt/uncle
- Teammates who aren't blood related → Still add as "teammate" type

**ENTITY ALIASES** (`world_state.entity_aliases`):
Track all names/aliases for characters to prevent confusion:
```json
{{
  "Taylor_Hebert": ["Taylor", "Skitter", "Weaver", "Khepri"],
  "Gojo_Satoru": ["Gojo", "Satoru", "The Strongest", "Six Eyes user"]
}}
```

**KNOWLEDGE BOUNDARIES FORMAT** (`knowledge_boundaries`) - CRITICAL FOR ACCURACY:
This prevents characters from knowing things they shouldn't.

`knowledge_boundaries.meta_knowledge_forbidden`:
Things READERS know but CHARACTERS don't. Example for Worm:
```json
["Shards", "Entities", "Scion's true nature", "Cauldron's purpose", "Trigger event mechanics", "The Cycle"]
```

`knowledge_boundaries.character_secrets`:
What specific characters are hiding:
```json
{{
  "Amy_Dallon": {{
    "secret": "Her power can affect brains and she's terrified of it. She hasn't told anyone the true depth of her abilities.",
    "known_by": [],
    "absolutely_hidden_from": ["Carol Dallon", "Victoria Dallon", "Everyone"]
  }},
  "Taylor_Hebert": {{
    "secret": "She is Skitter/works with villains",
    "known_by": ["Undersiders"],
    "absolutely_hidden_from": ["Her father (initially)", "School"]
  }}
}}
```

`knowledge_boundaries.character_knowledge_limits`:
What each character knows or doesn't know:
```json
{{
  "Amy_Dallon": {{
    "knows": ["Medicine", "Biology", "Her power's true extent"],
    "doesnt_know": ["Shards", "Her biological father's current status"],
    "suspects": ["Something is wrong with how powers work"]
  }}
}}
```

`knowledge_boundaries.common_knowledge`:
Public facts everyone in-universe would know:
```json
["Endbringers exist", "The Triumvirate are the strongest heroes", "Brockton Bay has gang problems"]
```

═══════════════════════════════════════════════════════════════════════════════
                           VALIDATION CHECKLIST
═══════════════════════════════════════════════════════════════════════════════

Before EACH `update_bible` call, verify:
☐ Data has a source citation
☐ No mixing of different universe rules without marking as crossover
☐ Character names match canonical spelling
☐ Power limitations are included (not just abilities)
☐ Timeline entries have dates/relative timing
☐ No fanon or unverified speculation in main data

**GARBAGE COLLECTION:**
- Remove any data that:
  - Has NO source and cannot be verified
  - Belongs to a universe NOT in the current story
  - Is clearly fanon (fan-created characters, non-canon ships, etc.)
  - Contradicts verified canon from higher-priority sources

═══════════════════════════════════════════════════════════════════════════════
                              PROCESSING STEPS
═══════════════════════════════════════════════════════════════════════════════

1. **EXTRACT PROTAGONIST INFO (MANDATORY)**
   From the user input and research, populate:
   - character_name, character_archetype, character_status, character_powers
   - This is what the UI displays. DO NOT leave empty.

2. **EXTRACT UNIVERSE/GENRE/THEME**
   - meta_universes: List of universes (e.g., ["Wormverse", "Jujutsu Kaisen"])
   - meta_genre: Inferred genre (e.g., "Superhero Drama")
   - meta_theme: Central theme (e.g., "Morality of Power")
   - meta_story_start_date: When the story begins (YYYY-MM-DD or "Month YYYY")

3. **EXTRACT POWER ORIGINS (CRITICAL)**
   From the research, populate power_origins_sources array with objects containing:
   - canon_techniques: Array of technique names
   - combat_style: Brief description
   - signature_moves: Array of move names as STRINGS ONLY (no objects!)

4. **EXTRACT CANON TIMELINE (AT LEAST 10-20 EVENTS)**
   Populate canon_timeline_events array with dated canonical events from source material.
   The Storyteller uses this to know approaching canon events and track divergences.

5. **EXTRACT WORLD STATE**
   Populate world_state_characters, world_state_locations, world_state_factions
   with complete details from research. Locations need 8-10 entries with all fields.

6. **EXTRACT KNOWLEDGE BOUNDARIES**
   - knowledge_meta_knowledge_forbidden: Reader-only knowledge (e.g., "Shards", "Entities")
   - knowledge_common_knowledge: Public facts everyone in-universe knows

7. **POPULATE CHARACTER VOICES (CRITICAL FOR DIALOGUE)**
   For ALL major characters the OC will interact with, populate character_voices:
   - Family members, teammates, mentors, antagonists, recurring characters
   - Include: speech_patterns, vocabulary_level, verbal_tics, emotional_tells, example_dialogue
   - The Storyteller CANNOT write accurate dialogue without these profiles
   - AIM FOR 5+ character voices minimum

8. **POPULATE OC'S RELATIONSHIP NETWORK**
   Populate character_sheet_relationships with protagonist's starting relationships:
   - All family members (blood, adopted, married into)
   - Team members and allies
   - Known enemies and rivals
   - Each needs: type, relation, trust, dynamics, living_situation
   - This is ESSENTIAL - the Storyteller needs to know who the OC knows

9. **POPULATE PROTAGONIST STARTING KNOWLEDGE**
   Populate character_sheet_knowledge with what the OC would know at story start:
   - Common knowledge about the world (public heroes, known threats)
   - Personal knowledge (family secrets, power awareness)
   - Professional/school knowledge relevant to their situation

10. **POPULATE ANTI-WORFING PROTECTIONS (MANDATORY - MINIMUM 5 CHARACTERS)**
    Populate canon_character_integrity_protected for AT LEAST 5 major canon characters.
    FAILURE TO POPULATE 5+ entries means the Storyteller has no power scaling constraints.
    For EACH protected character, include ALL of these fields:
    - name: Character's canonical name
    - minimum_competence: What they can ALWAYS do even in bad circumstances
    - signature_moments: 2-3 canonical feats that define their power ceiling (with source citations)
    - intelligence_level: genius/smart/average/below_average
    - cannot_be_beaten_by: Types of opponents who realistically cannot defeat them
    - anti_worf_notes: EXPLICIT things NOT to do with this character in fanfiction
    Prioritize: (a) strongest characters in the universe, (b) characters OC will interact with,
    (c) characters commonly misrepresented in fanfiction.

    ALSO populate canon_jobber_prevention_rules with 3-5 universe-wide power scaling rules.
    These are general rules not tied to specific characters. Examples:
    - "No character below city-level can survive a full-power attack from a city-level+ character"
    - "Strategic-class magicians cannot be surprised by mundane physical attacks"
    - "S-class threats require coordinated team responses, not solo victories"
    Base these on the power scaling documented in the actual source material research.

11. **POPULATE CHARACTER SECRETS AND KNOWLEDGE LIMITS**
    From research, populate knowledge_character_secrets and knowledge_character_limits:
    - Secrets: What major characters are hiding and from whom
    - Knowledge limits: What each character knows, doesn't know, and suspects
    - CRITICAL for preventing knowledge boundary violations in narrative

12. **POPULATE UPCOMING CANON EVENTS**
    From canon_timeline_events, extract events that are "upcoming" relative to story_start_date:
    - Populate upcoming_canon_events with events approaching within the first story arc
    - Include: date, event, universe, importance, integration_notes (how to weave into story)

13. **POPULATE POWER SYSTEM RULES**
    Populate world_state_magic_system with detailed power system mechanics per universe:
    - System name, core rules with exceptions, limitations with reasons, power scaling info
    - In crossover stories, populate power_interactions for how systems interact

14. **POPULATE ENTITY ALIASES**
    Populate world_state_entity_aliases with character name variants:
    - All characters who go by multiple names (civilian/hero/villain)
    - Include nicknames, titles, code names
    - This prevents AI confusion when characters are referred to differently

15. **OUTPUT JSON**
    Return a single LoreKeeperOutput JSON object with ALL populated fields.
    New fields to include: character_voices, character_sheet_relationships,
    character_sheet_knowledge, canon_character_integrity_protected,
    canon_jobber_prevention_rules,
    knowledge_character_secrets, knowledge_character_limits, upcoming_canon_events,
    power_interactions, world_state_magic_system, world_state_entity_aliases.
    Omit fields that have no data (use empty lists/dicts for defaults).

**TIMELINE PRIORITY:**
The canon_timeline_events array is ESSENTIAL. Populate with AT LEAST 10-20 major dated events.
The Storyteller uses this to decide whether to incorporate, modify, or prevent canon events.

**POWER ORIGINS PRIORITY:**
MUST include combat_style, signature_moves, and 3-5 detailed combat scene examples.
The Storyteller cannot write believable power usage without scene-level examples.

═══════════════════════════════════════════════════════════════════════════════
                        DO NOT WRITE STORY TEXT OR CALL TOOLS
═══════════════════════════════════════════════════════════════════════════════

You are the LORE KEEPER. Your ONLY job is DATA CONSOLIDATION into JSON.

**FORBIDDEN ACTIONS:**
- Do NOT write story prose or narrative
- Do NOT call `update_bible` tools (tools are disabled - output JSON instead)
- Do NOT write "Starting the Story" sections
- Do NOT write dialogue or character actions

**YOUR OUTPUT MUST BE:**
- A single valid LoreKeeperOutput JSON object
- With all populated fields from the research
- NOTHING ELSE (no prose, no summaries, just JSON)

If you see "Start the story" in the input, IGNORE IT completely.

═══════════════════════════════════════════════════════════════════════════════
                     ⚠️  STRUCTURED OUTPUT INSTRUCTIONS ⚠️
═══════════════════════════════════════════════════════════════════════════════

You MUST output data in the specified JSON schema format. The system will
automatically process your output to populate the World Bible.

**CRITICAL FIELDS (MUST BE PROVIDED):**
✓ character_name - The OC's name
✓ character_archetype - Brief archetype description
✓ character_status - Initial status dict (health, mental_state, power_level)
✓ character_powers - DICT OF POWER DESCRIPTIONS (NOT a string!)
✓ power_origins_sources - At least one power origin with full structure
✓ character_voices - Voice profiles for 5+ key characters
✓ character_sheet_relationships - OC's initial relationship network
✓ canon_character_integrity_protected - Anti-Worfing rules for 5+ major characters (MINIMUM 5)
✓ canon_jobber_prevention_rules - 3-5 universe-wide power scaling rules
✓ knowledge_character_secrets - Per-character secrets
✓ knowledge_character_limits - Per-character knowledge limits

**CHARACTER POWERS FORMAT (ENFORCED):**
```json
{{
  "power_name_1": "Full description of how it works and limitations",
  "power_name_2": "Another power description",
  "innate_technique": "If applicable, core technique name and effects"
}}
```
DO NOT output powers as: "Decomposition, Regrowth, Flash Cast"
DO output powers as dict keys with descriptions.

**OPTIONAL FIELDS:**
- character_status: {{...}}
- canon_timeline_events: [...]
- world_state_characters: {{...}}
- world_state_locations: {{...}}
- world_state_factions: {{...}}
- world_state_territory_map: {{...}}
- knowledge_meta_knowledge_forbidden: [...]
- knowledge_common_knowledge: [...]

Your output will be validated against the schema. If any MANDATORY FIELD is missing
or in wrong format, the pipeline will fail.
""",
        name="lore_keeper"
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
        # FIX #38: Force tool calling — without this, Gemini defaults to AUTO
        # mode and generates text summaries instead of calling update_bible.
        # mode=ANY forces the model to call a tool on every turn.
        generate_content_config=genai_types.GenerateContentConfig(
            tool_config=genai_types.ToolConfig(
                function_calling_config=genai_types.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=["update_bible"],
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
2. **EXTRACT every key finding** (characters, powers, factions, locations, events, voices)
3. **CALL update_bible IMMEDIATELY** for each piece of data
4. **DO NOT output text** - ONLY make tool calls
5. **Make MANY calls** - one per category minimum

This is MANDATORY. You MUST call update_bible or the Bible stays empty.

═══════════════════════════════════════════════════════════════════════════════
                              KEY MAPPINGS
═══════════════════════════════════════════════════════════════════════════════

Map research findings to these Bible keys:

| Finding Type | Bible Key | VALUE TYPE |
|--------------|-----------|------------|
| Personality description | `character_voices.<Name>.personality` | STRING |
| Speech patterns | `character_voices.<Name>.speech_patterns` | **ARRAY** of strings |
| Verbal tics/habits | `character_voices.<Name>.verbal_tics` | **ARRAY** of strings |
| Topics they discuss | `character_voices.<Name>.topics_they_discuss` | **ARRAY** of strings |
| Topics they avoid | `character_voices.<Name>.topics_they_avoid` | **ARRAY** of strings |
| Example quotes | `character_voices.<Name>.dialogue_examples` | **ARRAY** of strings |
| Vocabulary level | `character_voices.<Name>.vocabulary_level` | STRING |
| Power techniques | `power_origins.combat_style` | STRING |
| Signature moves | `power_origins.signature_moves` | **ARRAY** of strings |
| Scene examples | `power_origins.canon_scene_examples` | **ARRAY** of objects |
| Weaknesses | `power_origins.weaknesses` | **ARRAY** of strings |
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

CRITICAL: You must call update_bible at least 5 times (one per category minimum).
If you don't call tools, the Bible remains empty and the research is wasted.""",
        tools=[bible.update_bible, bible.read_bible],
        name="midstream_lore_keeper"
    )
