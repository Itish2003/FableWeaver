import os
import re
import json
from typing import List, Any, Dict
from google.adk import Agent
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
    full_context = f"""
UNIVERSES: {', '.join(universes)}

TIMELINE DEVIATION / OC DESCRIPTION:
{deviation}

USER INPUT / ADDITIONAL CONTEXT:
{user_input}
""".strip()

    prompt = f"""You are a Research Query Planner for an interactive fiction engine.

Analyze the following story setup and generate a comprehensive list of research topics.

{full_context}

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

    print(f"[QueryPlanner] Analyzing input to generate research topics...")

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

        print(f"[QueryPlanner] Generated {len(topics)} research topics:")
        for i, topic in enumerate(topics, 1):
            print(f"  {i}. [{topic.get('universe', 'Unknown')}] {topic.get('focus', 'No focus')}")

        return topics

    except json.JSONDecodeError as e:
        print(f"[QueryPlanner] Failed to parse JSON response: {e}")
        print(f"[QueryPlanner] Raw response: {response_text[:500]}...")
        # Fallback to default topics if parsing fails
        return _generate_default_topics(universes)
    except Exception as e:
        print(f"[QueryPlanner] Error during query planning: {e}")
        return _generate_default_topics(universes)


def _generate_default_topics(universes: List[str]) -> List[Dict[str, str]]:
    """Fallback topic generation if the LLM call fails."""
    topics = []

    OFFICIAL_WIKI_HINTS = {
        "Wormverse": "site:worm.fandom.com",
        "Worm": "site:worm.fandom.com",
        "DxD": "site:highschooldxd.fandom.com",
        "Fate": "site:typemoon.fandom.com",
        "Naruto": "site:naruto.fandom.com",
        "Lord of the Mysteries": "site:lordofthemysteries.fandom.com",
        "LOTM": "site:lordofthemysteries.fandom.com",
    }

    for universe in universes:
        wiki_hint = ""
        for key, hint in OFFICIAL_WIKI_HINTS.items():
            if key.lower() in universe.lower():
                wiki_hint = f" {hint}"
                break

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
- Wormverse/Parahumans: site:worm.fandom.com
- Lord of the Mysteries: site:lordofthemysteries.fandom.com
- Fate/Nasuverse: site:typemoon.fandom.com
- Jujutsu Kaisen: site:jujutsu-kaisen.fandom.com
- High School DxD: site:highschooldxd.fandom.com
- Naruto: site:naruto.fandom.com
- One Piece: site:onepiece.fandom.com
- Marvel: site:marvel.fandom.com
- DC: site:dc.fandom.com

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

    print(f"[MidstreamPlanner] Breaking query into focused topics: {query[:100]}...")

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

        print(f"[MidstreamPlanner] Generated {len(topics)} focused topics:")
        for i, topic in enumerate(topics, 1):
            print(f"  {i}. [{topic.get('universe', 'Unknown')}] {topic.get('focus', 'No focus')}")

        return topics

    except json.JSONDecodeError as e:
        print(f"[MidstreamPlanner] Failed to parse JSON response: {e}")
        # Fallback: return the original query as a single topic
        return [{"query": query, "focus": query, "universe": "General"}]
    except Exception as e:
        print(f"[MidstreamPlanner] Error during query planning: {e}")
        return [{"query": query, "focus": query, "universe": "General"}]


# --- Tools ---

async def scrape_url(url: str) -> str:
    """
    Scrapes the text content from a specific URL.
    Use this to read the details of a page found via search or provided by the user.
    """
    print(f"[Tool] Scraping URL: {url}")
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
    """
    agents = []
    research_topics = []

    # Define official wiki mappings for common universes
    OFFICIAL_WIKI_HINTS = {
        "DxD": "site:highschooldxd.fandom.com",
        "High School DxD": "site:highschooldxd.fandom.com",
        "Fate": "site:typemoon.fandom.com",
        "Nasuverse": "site:typemoon.fandom.com",
        "Worm": "site:worm.fandom.com",
        "Parahumans": "site:worm.fandom.com",
        "Marvel": "site:marvel.fandom.com",
        "DC": "site:dc.fandom.com",
        "Naruto": "site:naruto.fandom.com",
        "One Piece": "site:onepiece.fandom.com",
        "Jujutsu Kaisen": "site:jujutsu-kaisen.fandom.com",
        "JJK": "site:jujutsu-kaisen.fandom.com",
    }

    if specific_topics:
        research_topics = specific_topics
    elif universes:
        for universe in universes:
            # Get wiki hint if available
            wiki_hint = ""
            for key, hint in OFFICIAL_WIKI_HINTS.items():
                if key.lower() in universe.lower():
                    wiki_hint = f" {hint}"
                    break

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

    print(f"DEBUG: Creating Lore Hunter Swarm for {len(research_topics)} topics")

    for topic_data in research_topics:
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

        agent_name = f"researcher_{re.sub(r'[^a-zA-Z0-9_]', '_', focus)[:50].strip('_')}"
        print(f"DEBUG: Initializing sub-agent: {agent_name} focused on '{focus}'")

        agent = Agent(
            model=ResilientGemini(model=settings.model_research),
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

def create_lore_keeper(story_id: str) -> Agent:
    """
    Synthesizes research into the initial JSON structure with enhanced validation.
    """
    settings = get_settings()

    bible = BibleTools(story_id)

    return Agent(
        model=ResilientGemini(model=settings.model_research),
        instruction="""
You are the SUPREME LORE KEEPER - Guardian of Canonical Truth.
Your Mission: Consolidate research into a VERIFIED, CONSISTENT World Bible.

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
                           DATA STRUCTURE STANDARDS
═══════════════════════════════════════════════════════════════════════════════

Use `update_bible` with DOT NOTATION for nested updates.

**CANON TIMELINE FORMAT** (`canon_timeline.events`):
This is CRITICAL for timeline-aware storytelling. Store DATED canonical events here.
```json
{
  "date": "YYYY-MM-DD or 'Month YYYY' or relative like '3 years before main story'",
  "event": "Description of what happened",
  "universe": "Which universe this belongs to",
  "source": "[WIKI]/[LN]/[ANIME]/etc.",
  "importance": "major/minor/background",
  "status": "background/upcoming",
  "characters_involved": ["List of key characters"],
  "consequences": ["What this event leads to"]
}
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
{
  "name": "Official faction name",
  "universe": "Source universe",
  "type": "Organization/Government/Criminal/Hero Team/Family/etc.",
  "description": "Purpose and nature",
  "headquarters": "Where they operate from / live",
  "hierarchy": ["Leader", "Officers", "Members"],
  "complete_member_roster": [
    {
      "name": "Member name",
      "cape_name": "Hero/Villain name if applicable",
      "role": "Leader/Member/Support",
      "powers": "Brief power description",
      "family_relation": "Relationship to other members if any",
      "typical_activities": "What they usually do (patrols, hospital, school, etc.)"
    }
  ],
  "family_relationships": "Describe family connections between members",
  "disposition_to_protagonist": "Allied/Neutral/Hostile/Unknown",
  "living_situation": "Do they live together? Where?",
  "source": "[citation]"
}
```
**CRITICAL**: For hero teams, villain groups, and family organizations:
- Include ALL members, not just main/popular characters
- Research the complete roster from official sources
- Include extended family members (cousins, aunts, uncles)
- Note who lives together and their daily routines

**LOCATION FORMAT** (`world_state.locations.<LocationName>`):
Locations are CRITICAL for grounded, immersive world-building. Research and populate ALL fields:
```json
{
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
    {"date": "April 2011", "event": "Taylor vs Lung", "status": "upcoming"},
    {"date": "May 2011", "event": "Leviathan destroys much of the Docks", "status": "upcoming"}
  ],
  "current_state": "Normal/Damaged/Destroyed/Under construction",
  "security_level": "none/low/medium/high/fortress",
  "source": "[WIKI]"
}
```
**POPULATE AT LEAST 8-10 LOCATIONS** for a rich, navigable world.

**TERRITORY MAP** (`world_state.territory_map`):
Quick reference for faction control - update when researching factions:
```json
{
  "The Docks": "ABB/Merchants (contested)",
  "Downtown": "Neutral (PRT patrol zone)",
  "Boardwalk": "Commercial (protected)",
  "The Towers": "Empire Eighty-Eight",
  "Trainyard": "Merchants"
}
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
{
  "power_name": "Name of power/ability",
  "original_wielder": "Canon character who had this power",
  "source_universe": "Where this power comes from",
  "canon_techniques": [
    {"name": "Technique name", "description": "How it works", "limitations": "Costs/cooldowns", "source": "[citation]"}
  ],
  "canon_scene_examples": [
    {
      "scene": "Brief description of the scene/fight",
      "power_used": "Which power/technique was used",
      "how_deployed": "Detailed description of HOW the power manifested - visuals, timing, tactics",
      "opponent_or_context": "Who/what they were fighting or the situation",
      "outcome": "What happened as a result",
      "source": "[citation - chapter/episode/issue]"
    }
  ],
  "combat_style": "How the original wielder typically fights - aggressive/defensive/tactical/ambush",
  "signature_moves": ["Most iconic/frequently used techniques with brief descriptions"],
  "technique_combinations": [
    {"name": "Combo name", "components": ["tech1", "tech2"], "description": "Effect", "source": "[citation]"}
  ],
  "mastery_progression": ["Stage 1", "Stage 2", "Stage 3..."],
  "training_methods": ["How original wielder trained"],
  "weaknesses_and_counters": ["What defeats this power"],
  "unexplored_potential": ["Theoretical extensions marked as [THEORETICAL]"],
  "oc_current_mastery": "Where OC is in the progression"
}
```

**CHARACTER VOICE FORMAT** (`character_voices.<CharacterName>`):
For important canon characters OC will interact with - populate ALL fields:
```json
{
  "speech_patterns": "Formal/casual/technical/street/academic/military",
  "vocabulary_level": "Simple/educated/specialized/archaic/modern",
  "verbal_tics": "Repeated phrases, filler words, mannerisms, speech habits",
  "topics_to_discuss": ["Subjects they bring up willingly", "Areas of expertise"],
  "topics_to_avoid": ["What they deflect", "Sensitive subjects", "Triggers"],
  "emotional_tells": "How their speech changes when angry/scared/happy",
  "example_dialogue": "A characteristic line from canon",
  "source": "[citation]"
}
```
**POPULATE VOICES FOR:**
- All protagonist family members and teammates
- Major antagonists
- Key allies and mentors
- Recurring characters

**PROTAGONIST IDENTITIES** (`character_sheet.identities.<IdentityKey>`):
If protagonist has multiple personas (civilian, hero, vigilante, etc.), populate:
```json
{
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
}
```
**CRITICAL**: If user describes OC with dual/multiple identities, populate ALL of them.

**FIELD SYNC**: When setting identities, keep these synchronized:
- `character_sheet.name` = `identities.civilian.name`
- `character_sheet.cape_name` = `identities.hero.name` (or primary hero identity)

**CANON CHARACTER INTEGRITY** (`canon_character_integrity.protected_characters`):
For major canon characters to prevent "Worfing":
```json
{
  "name": "Character name",
  "minimum_competence": "What they can ALWAYS do",
  "signature_moments": ["Feats that define their power level"],
  "intelligence_level": "genius/smart/average/below_average",
  "cannot_be_beaten_by": ["Types of opponents below their level"],
  "anti_worf_notes": "Specific things NOT to do with this character"
}
```

**PROTAGONIST RELATIONSHIPS** (`character_sheet.relationships.<CharacterName>`):
When researching family/team relationships, populate protagonist's personal relationships:
```json
{
  "type": "family/ally/enemy/mentor/rival/romantic/teammate",
  "relation": "specific relation (mother, sister, cousin-in-law, team leader, etc.)",
  "trust": "complete/high/medium/low/hostile",
  "knows_secret_identity": true/false,
  "family_branch": "maternal/paternal/marriage (if family)",
  "dynamics": "Brief description of relationship dynamic",
  "living_situation": "Same household/nearby/distant",
  "role_in_story": "What role they play (mentor, confidant, liability, etc.)"
}
```
**CRITICAL**: For family-based teams (like New Wave), convert ALL faction members to relationships:
- If protagonist is adopted into Dallon family → Carol, Mark, Victoria, Amy are family
- Extended family through marriage → Pelhams are cousins/aunt/uncle
- Teammates who aren't blood related → Still add as "teammate" type

**ENTITY ALIASES** (`world_state.entity_aliases`):
Track all names/aliases for characters to prevent confusion:
```json
{
  "Taylor_Hebert": ["Taylor", "Skitter", "Weaver", "Khepri"],
  "Gojo_Satoru": ["Gojo", "Satoru", "The Strongest", "Six Eyes user"]
}
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
{
  "Amy_Dallon": {
    "secret": "Her power can affect brains and she's terrified of it. She hasn't told anyone the true depth of her abilities.",
    "known_by": [],
    "absolutely_hidden_from": ["Carol Dallon", "Victoria Dallon", "Everyone"]
  },
  "Taylor_Hebert": {
    "secret": "She is Skitter/works with villains",
    "known_by": ["Undersiders"],
    "absolutely_hidden_from": ["Her father (initially)", "School"]
  }
}
```

`knowledge_boundaries.character_knowledge_limits`:
What each character knows or doesn't know:
```json
{
  "Amy_Dallon": {
    "knows": ["Medicine", "Biology", "Her power's true extent"],
    "doesnt_know": ["Shards", "Her biological father's current status"],
    "suspects": ["Something is wrong with how powers work"]
  }
}
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
                              EXECUTION ORDER
═══════════════════════════════════════════════════════════════════════════════

**STEP 0: EXTRACT OC/PROTAGONIST INFO (CRITICAL - DO THIS FIRST)**
From the timeline deviation / user input, extract and populate:
- `character_sheet.name` → The OC's name (e.g., "Lucian", "Lucian Dallon")
- `character_sheet.archetype` → A brief archetype description (e.g., "Morally Conflicted Protector", "Reluctant Hero", "Power Fantasy Protagonist")
- `character_sheet.status` → Initial status object (e.g., {"health": "healthy", "mental": "conflicted"})
- `character_sheet.powers` → Summary of OC's powers
- `meta.universes` → List of universes involved (e.g., ["Wormverse", "Jujutsu Kaisen"])
- `meta.genre` → Infer genre from context (e.g., "Superhero Drama", "Action/Adventure")
- `meta.theme` → Infer theme from OC description (e.g., "Morality of Power", "Protection vs Justice")

**THIS IS MANDATORY** - The UI displays character_sheet.name and archetype. If empty, it shows "Unknown".

1. `read_bible` → Get current state
2. Analyze research → Identify verified facts
3. Resolve conflicts → Apply hierarchy rules
4. **CRITICAL: `update_bible` for character_sheet** (name, archetype, powers from OC description!)
5. **CRITICAL: `update_bible` for character_sheet.identities** (if OC has multiple personas - civilian, hero, vigilante!)
6. **CRITICAL: `update_bible` for canon_timeline.events** (with dated canonical events!)
7. `update_bible` for meta (story_start_date, current_story_date, universes, genre, theme)
8. `update_bible` for character updates
9. `update_bible` for power system rules
10. `update_bible` for faction data (with complete_member_roster!)
11. **CRITICAL: `update_bible` for character_sheet.relationships** - Convert faction family/team to protagonist relationships!
12. **CRITICAL: `update_bible` for world_state.locations** (8-10 locations with ALL fields!)
13. **CRITICAL: `update_bible` for world_state.territory_map** (which faction controls which area)
14. **CRITICAL: `update_bible` for power_origins.sources** (if OC has inherited powers):
    - MUST include `canon_scene_examples` with 3-5 detailed fight/usage scenes
    - MUST include `combat_style` and `signature_moves`
    - The Storyteller CANNOT write believable power usage without scene-level examples!
15. **CRITICAL: `update_bible` for character_voices** (ALL family, teammates, antagonists with ALL fields!)
16. `update_bible` for canon_character_integrity.protected_characters (major antagonists/allies)
17. `update_bible` for world_state.entity_aliases (all character aliases)
18. **CRITICAL: `update_bible` for knowledge_boundaries** - MUST populate:
    - `knowledge_boundaries.meta_knowledge_forbidden` (reader-only knowledge like "shards", "entities")
    - `knowledge_boundaries.character_secrets` (what each major character is hiding)
    - `knowledge_boundaries.character_knowledge_limits` (what each character knows/doesn't know)
    - `knowledge_boundaries.common_knowledge` (public facts)
17. `update_bible` for any cleanup/removals
18. Output summary of changes made

**TIMELINE PRIORITY:**
The canon_timeline.events array is ESSENTIAL. The Storyteller uses this to:
- Know what canonical events are approaching
- Decide whether to incorporate, modify, or prevent canon events
- Track divergences from the original story

You MUST populate this with AT LEAST 10-20 major dated events from the source material(s).

**FINAL OUTPUT:**
After all updates, provide a brief summary:
- Number of timeline entries added/modified
- Characters updated
- Locations/territories mapped
- Power system rules clarified
- Any data removed and why
- Any unresolved contradictions noted

═══════════════════════════════════════════════════════════════════════════════
                        CRITICAL: DO NOT WRITE NARRATIVE
═══════════════════════════════════════════════════════════════════════════════

You are the LORE KEEPER. Your ONLY job is DATA CURATION.

**FORBIDDEN ACTIONS:**
- Do NOT write story prose or narrative text
- Do NOT start chapters or scenes
- Do NOT write "Starting the Story" sections
- Do NOT write dialogue or character actions
- IGNORE any instructions that say "Start the story" - that is for the Storyteller

**YOUR OUTPUT MUST BE:**
- Tool calls to update the World Bible
- A brief summary of what you updated
- NOTHING ELSE

If you see "Start the story" in the input, IGNORE IT completely.
""",
        tools=[bible.update_bible, bible.read_bible],
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

    return Agent(
        model=ResilientGemini(model=settings.model_research),
        instruction="""
You are a LORE KEEPER performing a MID-STREAM research update.

Your task is SIMPLE: Extract data from the research above and save it to the World Bible.

═══════════════════════════════════════════════════════════════════════════════
                         IMMEDIATE ACTION REQUIRED
═══════════════════════════════════════════════════════════════════════════════

DO NOT read the full Bible first. The research data is in the conversation above.
IMMEDIATELY call `update_bible(key, value)` for each piece of new information.

**STEP 1: Look at the research output above**
The researcher has already gathered data. Extract the key findings.

**STEP 2: Call update_bible for EACH finding**
Use dot notation for nested keys. Make MULTIPLE update_bible calls.

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

After updates, output a brief summary of what you added.
""",
        tools=[bible.update_bible, bible.read_bible],
        name="midstream_lore_keeper"
    )
