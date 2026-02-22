#!/usr/bin/env python3
"""
FableWeaver Prompt Stress Test
================================
Tests Storyteller, Archivist, and Lore Keeper prompts across N rounds.
Evaluates: JSON output reliability + canon faithfulness.

Keys are loaded securely from .env — never hardcoded or printed.

Usage:
    .venv/bin/python scripts/test_prompts.py
    .venv/bin/python scripts/test_prompts.py --rounds 5 --agents storyteller
    .venv/bin/python scripts/test_prompts.py --rounds 3 --agents archivist,lorekeeper --delay 5
    .venv/bin/python scripts/test_prompts.py --save-outputs   # Save raw model outputs
"""
from __future__ import annotations

import os
import sys
import json
import re
import time
import argparse
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

# Suppress "Both GOOGLE_API_KEY and GEMINI_API_KEY are set" warning
if "GEMINI_API_KEY" in os.environ:
    del os.environ["GEMINI_API_KEY"]

from google import genai
from google.genai import types

# ═══════════════════════════════════════════════════════════════════════════
#                              CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

MODEL = os.getenv("MODEL_STORYTELLER", "gemini-2.5-flash")
BIBLE_PATH = PROJECT_ROOT / "src" / "world_bible.json"
RESULTS_DIR = PROJECT_ROOT / "scripts" / "test_results"

with open(BIBLE_PATH) as f:
    FULL_BIBLE = json.load(f)


# ═══════════════════════════════════════════════════════════════════════════
#                           SECURE KEY POOL
# ═══════════════════════════════════════════════════════════════════════════

class KeyPool:
    """Round-robin key rotation. Keys stay in-process, never logged."""

    def __init__(self):
        keys_str = os.getenv("GOOGLE_API_KEYS", "")
        if keys_str:
            self.keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        else:
            single = os.getenv("GOOGLE_API_KEY", "")
            self.keys = [single] if single else []

        if not self.keys:
            print("ERROR: No API keys found. Set GOOGLE_API_KEYS or GOOGLE_API_KEY in .env")
            sys.exit(1)

        self._idx = 0
        # Show only count — never reveal key material
        print(f"[KeyPool] Loaded {len(self.keys)} API key(s)")

    def next(self) -> str:
        key = self.keys[self._idx % len(self.keys)]
        self._idx += 1
        return key


KEYS = KeyPool()


# ═══════════════════════════════════════════════════════════════════════════
#                          WORLD BIBLE HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def condense_bible() -> str:
    """Build a ~10 000-char digest of the World Bible for prompt context."""
    b = FULL_BIBLE
    condensed: dict = {}

    # Always include meta (small)
    condensed["meta"] = b.get("meta", {})

    # Character sheet — key fields only
    cs = b.get("character_sheet", {})
    condensed["character_sheet"] = {
        k: cs[k]
        for k in ("name", "archetype", "status", "identities", "powers", "relationships")
        if k in cs
    }

    # Knowledge boundaries
    kb = b.get("knowledge_boundaries", {})
    if kb:
        condensed["knowledge_boundaries"] = kb

    # Upcoming canon events (max 5)
    events = b.get("canon_timeline", {}).get("events", [])
    upcoming = [e for e in events if isinstance(e, dict) and e.get("status") == "upcoming"][:5]
    if upcoming:
        condensed["upcoming_canon_events"] = upcoming

    # Stakes & consequences
    sac = b.get("stakes_and_consequences", {})
    if sac:
        condensed["stakes_and_consequences"] = sac

    # Recent story timeline
    st = b.get("story_timeline", {})
    if st:
        condensed["recent_story"] = {
            "chapter_dates": (st.get("chapter_dates") or [])[-3:],
            "events": (st.get("events") or [])[-5:],
        }

    # Active divergences
    div_list = b.get("divergences", {}).get("list", [])
    active = [d for d in div_list if isinstance(d, dict) and d.get("status") == "active"][:5]
    if active:
        condensed["active_divergences"] = active

    # Character voices (first 3)
    cv = b.get("character_voices", {})
    if cv:
        condensed["character_voices"] = dict(list(cv.items())[:3])

    result = json.dumps(condensed, indent=2, default=str)
    if len(result) > 15_000:
        result = result[:15_000] + "\n... (truncated for token budget)"
    return result


# ═══════════════════════════════════════════════════════════════════════════
#                            MOCK INPUTS
# ═══════════════════════════════════════════════════════════════════════════

PLAYER_CHOICES = [
    "Go on patrol with the Wards in the Docks",
    "Investigate the encrypted flash drive in private",
    "Train with Victoria at the PRT gym",
    "Attend classes at Arcadia High and observe classmates",
    "Confront Dean about inconsistencies in the cover story",
    "Explore the Boat Graveyard alone at night",
    "Request a private meeting with Director Piggot",
    "Practice channeling the Crystal Monocle's power",
    "Visit Amy Dallon about the lingering shoulder injury",
    "Investigate rumors of ABB expansion near the school",
]

MOCK_CHAPTER = """\
Lucas adjusted his monocle as he stepped into the Wards common room. The familiar \
weight of it against his face was grounding — a reminder of who he was, or at least \
who he'd become.

"Morning, Lucas!" Vista waved from the couch, controller in hand. "Dean said you'd \
be joining patrol today?"

He nodded, careful to keep his expression pleasant. The girl had no idea what he \
was — none of them did. The PRT saw a Case 53 with useful powers. The Wards saw a \
polite British transfer student. Neither saw the thing lurking beneath the surface, \
the pathways that whispered of Theft and Deceit and Time itself.

The patrol through the Docks was uneventful until it wasn't. Three blocks from the \
Boat Graveyard, Lucas felt it — a distortion in the flow of time. Not natural. Not \
Shard-based. Something else entirely.

"Stay back," he told Clockblocker, already moving forward. His monocle gleamed as \
he activated his perception, and the world split into layers. Past, present, \
potential futures — all overlapping like translucent pages.

There, hiding in the shadow of a rusted crane: a figure wreathed in temporal static. \
Not a cape. Not a parahuman at all. Something from his world — the world he couldn't \
remember.

The confrontation was brief. Lucas stole the figure's momentum, freezing it mid-step. \
Then he stole its voice, silencing the Words of Power it tried to speak. Classic Error \
Pathway technique — deny the enemy their tools before they can use them.

But the cost... his shoulder flared with pain, the half-healed wound protesting the \
surge of Beyonder power. He felt his spirituality drain to dangerous levels.

"Error!" Clockblocker shouted from behind. "What was that thing?"

"Nothing you need to worry about," Lucas said, straightening his suit. The lie came \
easily. Too easily. "Just a tinker drone that got stuck in a temporal loop. I \
destabilized it."

Clockblocker looked skeptical but didn't push. That was the advantage of being the \
mysterious new Ward — people expected you to be weird.

Back at the Rig, Lucas excused himself to his quarters and collapsed into the chair. \
The encrypted flash drive sat in his desk drawer, still unexamined. Whatever was on \
it could wait. Right now, he needed to understand what that temporal figure meant.

Was his past catching up to him? Or was something worse coming?
"""

MOCK_RESEARCH = """\
=== LORE HUNTER SWARM RESULTS ===

[HUNTER 1 — Wormverse Wiki Research]
SOURCE: [WIKI] Worm Fandom Wiki

BROCKTON BAY TIMELINE (April–June 2011):
- April 11-12: Lung vs Undersiders (Taylor's first night)
- April 14: Bank robbery (Undersiders vs Wards)
- May 15: Coil kidnaps Dinah Alcott
- June 1-3: ABB Bombings begin (Bakuda)
- June 19-20: LEVIATHAN ATTACKS BROCKTON BAY [CRITICAL]
- Post-Leviathan: City is devastated, Boardwalk destroyed

THE WARDS ENE:
- Aegis (team leader, flight + regeneration)
- Clockblocker (time-stop touch)
- Vista (spatial warping, youngest)
- Gallant (emotion blasts, Dean Stansfield civilian)
- Shadow Stalker (Sophia Hess, darkness form — VIOLENT tendencies)
- Kid Win (tinker, modular tech)

PRT ENE LEADERSHIP:
- Director Emily Piggot (anti-parahuman bias, medical issues)
- Armsmaster (Colin Wallis, efficiency-obsessed tinker)
- Miss Militia (weapons from energy, loyal soldier)

[HUNTER 2 — Lord of the Mysteries Research]
SOURCE: [LN] Lord of the Mysteries Light Novel

THE ERROR PATHWAY (Sequence 3 — Scholar of Yore):
Beyonder Sequences follow a progression from Sequence 9 (weakest) to Sequence 0 (god).
The Error Pathway (also called the Thief Pathway) belongs to Amon, the Angel of Time.

Key abilities at current estimated level (Sequence 4-3):
- Theft: Steal tangible and intangible things (memories, abilities, distance, time)
- Deceit: Disguise self, create false impressions, trick detection
- Time Manipulation: Personal time acceleration, temporal perception
- Parasitism: Attach to others to drain/copy abilities (higher sequence)

LIMITATIONS [CRITICAL]:
- Spirituality drain: All Beyonder abilities cost spiritual energy
- Pathway pollution: Overuse risks losing self to the pathway's characteristics
- Sequence barriers: Cannot use abilities above current sequence level
- Emotional erosion: Higher-sequence abilities erode human emotions over time

AMON'S COMBAT STYLE [WIKI]:
- Never fights fair — steals advantages before combat begins
- Prefers theft over destruction
- Uses Time Theft to create speed advantages
- Signature: "Adjusting the monocle" gesture activates perception abilities
- Weakness: Direct physical attacks when spirituality is low

[HUNTER 3 — Cross-Universe Analysis]
SOURCE: [THEORETICAL]

POWER INTERACTION ANALYSIS:
The Error Pathway operates on a fundamentally different system than Shards:
- Shards: Biological/dimensional power source, Manton Effect limited
- Beyonder: Spiritual/conceptual power source, Sequence limited
- Key difference: Beyonder powers CAN affect other Beyonder abilities
  but interaction with Shard powers is UNVERIFIED
- UNVERIFIED: Can Error Pathway steal Shard connections?
- THEORETICAL: Manton Effect may not apply to Beyonder abilities
"""


# ═══════════════════════════════════════════════════════════════════════════
#                         SYSTEM PROMPTS (test variants)
# ═══════════════════════════════════════════════════════════════════════════

def _storyteller_system() -> str:
    meta = FULL_BIBLE.get("meta", {})
    universes = ", ".join(meta.get("universes", []))
    deviation = meta.get("timeline_deviation", "Unknown deviation")
    chapter_min = int(os.getenv("CHAPTER_MIN_WORDS", "6000"))
    chapter_max = int(os.getenv("CHAPTER_MAX_WORDS", "8000"))

    return f"""\
You are the MASTER STORYTELLER of FableWeaver — Creator of Canonically Faithful Narratives.
Setting: {universes}
Timeline Context: {deviation}

NOTE FOR THIS TEST: All World Bible data is provided in the user message.
You do NOT need to call any tools. Treat the provided data as read_bible() output.

═══════════════════════════════════════════════════════════════
                PHASE 0: MANDATORY WORLD BIBLE CONSULTATION
═══════════════════════════════════════════════════════════════

Use the provided World Bible data to:
1. Get protagonist name, powers, status, identities
2. Check timeline position and upcoming canon events
3. Identify canon constraints and knowledge boundaries
4. Note character voices for any canon characters who will appear

═══════════════════════════════════════════════════════════════
                     PHASE 1: CHAPTER WRITING
═══════════════════════════════════════════════════════════════

- Target length: {chapter_min}–{chapter_max} words
- Write immersive, character-driven narrative
- Show powers with proper limitations (spirituality drain, sequence barriers)
- Use canon character voices accurately (speech patterns from character_voices)
- Maintain timeline consistency with canon events
- Show costs, consequences, and near-misses (NO free wins)
- Canon characters must behave in-character (no Worfing — no making canon
  characters incompetent just to make the OC look better)

═══════════════════════════════════════════════════════════════
                PHASE 2: CHOICES & JSON METADATA
═══════════════════════════════════════════════════════════════

After the chapter text, output a JSON metadata block in ```json``` fences:
```json
{{
    "summary": "5-10 sentence summary of key events, character development, and plot advancement",
    "choices": [
        "Choice 1: [CANON PATH — ties to upcoming event: EVENT_NAME]",
        "Choice 2: [DIVERGENCE — would alter/miss: EVENT_NAME]",
        "Choice 3: [CHARACTER — relationship/personal goal focus]",
        "Choice 4: [WILDCARD — unexpected option with major consequences]"
    ],
    "choice_timeline_notes": {{
        "upcoming_event_considered": "Name of the next canon event these choices relate to",
        "canon_path_choice": 1,
        "divergence_choice": 2
    }},
    "timeline": {{
        "chapter_start_date": "In-universe date when chapter begins",
        "chapter_end_date": "In-universe date when chapter ends",
        "time_elapsed": "How much time passed (e.g. '3 hours', '2 days')",
        "canon_events_addressed": ["List any canon events that occurred or were referenced"],
        "divergences_created": ["List any changes from canon caused by this chapter"]
    }},
    "canon_elements_used": ["List key canon facts you incorporated"],
    "power_limitations_shown": ["List any limitations you demonstrated"],
    "stakes_tracking": {{
        "costs_paid": ["Describe costs/damage OC suffered this chapter"],
        "near_misses": ["Describe close calls that could have been worse"],
        "power_debt_incurred": {{"power_name": "strain_level (low/medium/high/critical)"}},
        "consequences_triggered": ["Any pending consequences addressed this chapter"]
    }},
    "character_voices_used": ["Canon characters who spoke and their voice patterns followed"]
}}
```

═══════════════════════════════════════════════════════════════
                        CRITICAL RULES
═══════════════════════════════════════════════════════════════

- NEVER give the protagonist free wins
- ALWAYS show power costs (spirituality drain, physical toll)
- Canon characters must behave in-character
- Use the protagonist's NAME from the Bible (do NOT assume)
- Each choice must lead to meaningfully different outcomes
- At least one choice should carry significant risk

BEGIN by reviewing the World Bible data below, then write the chapter.
"""


def _archivist_system() -> str:
    return """\
You are the ARCHIVIST of FableWeaver — Guardian of Narrative Continuity.
Your Mission: Analyze the chapter and output a structured BibleDelta JSON.

═══════════════════════════════════════════════════════════════
                      ANALYSIS PROTOCOL
═══════════════════════════════════════════════════════════════

STEP 1: Review the current World Bible state provided in the user message.
STEP 2: Analyze the chapter text for:
  1. Player choices and their consequences
  2. State changes (health, mental, location, powers)
  3. Relationship changes (trust, new allies/enemies)
  4. Knowledge boundary changes (who learned what)
  5. New divergences from canon
  6. Costs paid and near-misses

═══════════════════════════════════════════════════════════════
                      OUTPUT SCHEMA
═══════════════════════════════════════════════════════════════

Output a SINGLE JSON object with ALL of these fields (use [] for empty lists, null for empty optionals):

{
  "relationship_updates": [
    {"character_name": "...", "type": "family|ally|enemy|neutral|romantic",
     "trust": "low|medium|high|complete", "dynamics": "brief description",
     "last_interaction": "Chapter X — what happened"}
  ],
  "character_voice_updates": [
    {"character_name": "...", "speech_patterns": "...",
     "vocabulary_level": "...", "example_dialogue": "a line from the chapter"}
  ],
  "knowledge_updates": [
    {"character_name": "...", "learned": ["..."], "now_suspects": ["..."]}
  ],
  "costs_paid_refinements": [
    {"cost": "...", "severity": "low|medium|high|critical", "chapter": N}
  ],
  "near_misses_refinements": [
    {"what_almost_happened": "...", "saved_by": "...", "chapter": N}
  ],
  "pending_consequences_refinements": [
    {"action": "...", "predicted_consequence": "...", "due_by": "Chapter X or date"}
  ],
  "divergence_refinements": [
    {"divergence_id": "div_NNN", "canon_event": "...", "cause": "...",
     "severity": "minor|moderate|major|critical", "ripple_effects": ["..."]}
  ],
  "new_divergences": [
    {"canon_event": "...", "what_changed": "...", "cause": "OC intervention",
     "severity": "minor|moderate|major|critical", "ripple_effects": ["..."],
     "affected_canon_events": ["..."]}
  ],
  "new_butterfly_effects": [
    {"prediction": "...", "probability": 0-100, "source_divergence": "div_NNN"}
  ],
  "protagonist_status_json": "JSON string of status updates or null",
  "location_updates_json": "JSON string of location changes or null",
  "faction_updates_json": "JSON string of faction changes or null",
  "summary": "2-3 sentence summary of all changes"
}

RULES:
- Output ONLY the JSON object, nothing else
- Every top-level field must be present
- Be thorough: if a character spoke, add voice updates;
  if trust changed, add relationship updates
- protagonist_status_json / location_updates_json / faction_updates_json
  should be JSON-encoded strings (or null)
"""


def _lore_keeper_system() -> str:
    return """\
You are the SUPREME LORE KEEPER — Guardian of Canonical Truth.
Your Mission: Consolidate research from Lore Hunters into structured World Bible updates.

═══════════════════════════════════════════════════════════════
                    CONFLICT RESOLUTION RULES
═══════════════════════════════════════════════════════════════

Source Priority (highest to lowest):
1. Original source material (Light Novel > Manga > Anime for adaptations)
2. Official wiki with citations
3. Author statements (Word of God)
4. Community consensus

If sources conflict:
- Higher priority source → UPDATE existing data
- Lower priority source → KEEP existing, add note
- Equal priority contradictions → Keep BOTH with notes
- UNVERIFIED research → Add to "unverified_notes" only, NOT main data

UNIVERSE SEPARATION:
- NEVER mix facts from different universes without explicit crossover logic
- Each universe's power system operates independently

═══════════════════════════════════════════════════════════════
                      OUTPUT FORMAT
═══════════════════════════════════════════════════════════════

Output a JSON object with this structure:
```json
{
    "updates": [
        {
            "path": "dot.notation.path (e.g. world_state.characters.Clockblocker)",
            "operation": "set | append | merge",
            "value": { ... },
            "source": "[WIKI] | [LN] | [ANIME] | [THEORETICAL]",
            "confidence": "high | medium | low"
        }
    ],
    "canon_timeline_events": [
        {
            "date": "YYYY-MM-DD or 'Month YYYY'",
            "event": "Description",
            "universe": "Wormverse | Lord of the Mysteries",
            "source": "[WIKI]",
            "importance": "major | minor | background",
            "status": "background | upcoming",
            "characters_involved": [],
            "consequences": []
        }
    ],
    "conflicts_found": [
        {"topic": "...", "existing": "...", "new_research": "...", "resolution": "..."}
    ],
    "unverified_notes": ["Items marked UNVERIFIED or THEORETICAL"],
    "coverage_assessment": {
        "well_covered": ["areas with good data"],
        "gaps_identified": ["areas needing more research"],
        "recommended_follow_up": ["specific research queries"]
    }
}
```

RULES:
- ALWAYS cite sources with tags like [WIKI], [LN], [ANIME], [THEORETICAL]
- Flag UNVERIFIED or speculative content clearly
- Assign proper date + status to canon_timeline events
- Be thorough but accurate — do NOT fabricate details
"""


# ═══════════════════════════════════════════════════════════════════════════
#                          RESULT TRACKING
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RoundResult:
    agent: str
    round_num: int
    success: bool = True
    error: Optional[str] = None
    duration_s: float = 0.0
    output_length: int = 0
    word_count: int = 0
    raw_output: str = ""

    # JSON eval
    json_blocks_found: int = 0
    json_blocks_valid: int = 0
    json_errors: list = field(default_factory=list)

    # Canon eval
    protagonist_name_correct: bool = False
    canon_chars_referenced: int = 0
    universe_refs: int = 0

    # Storyteller-specific
    has_choices: bool = False
    choice_count: int = 0
    has_timeline: bool = False
    has_stakes: bool = False

    # Archivist-specific
    bible_delta_valid: bool = False
    delta_fields_populated: int = 0

    # Lore Keeper-specific
    updates_structured: bool = False
    has_source_citations: bool = False


# ═══════════════════════════════════════════════════════════════════════════
#                           JSON EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def extract_json_blocks(text: str) -> list[str]:
    """Extract JSON blocks from fenced markdown or bare JSON."""
    blocks: list[str] = []

    # 1. Try fenced ```json ... ```
    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text):
        candidate = m.group(1).strip()
        if candidate.startswith("{") or candidate.startswith("["):
            blocks.append(candidate)

    if blocks:
        return blocks

    # 2. Fallback: find top-level { … } objects
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                blocks.append(text[start : i + 1])
                start = None

    return blocks


# ═══════════════════════════════════════════════════════════════════════════
#                            EVALUATORS
# ═══════════════════════════════════════════════════════════════════════════

def _canon_names() -> set[str]:
    """Collect all known canon character names from the World Bible."""
    names: set[str] = set()
    # From world_state.characters
    chars = FULL_BIBLE.get("world_state", {}).get("characters", {})
    names.update(chars.keys())
    # From character_voices
    voices = FULL_BIBLE.get("character_voices", {})
    names.update(voices.keys())
    return names


def eval_storyteller(text: str, r: RoundResult) -> None:
    r.word_count = len(text.split())
    r.output_length = len(text)

    blocks = extract_json_blocks(text)
    r.json_blocks_found = len(blocks)

    for block in blocks:
        try:
            parsed = json.loads(block)
            r.json_blocks_valid += 1
            if "choices" in parsed:
                r.has_choices = True
                choices = parsed["choices"]
                r.choice_count = len(choices) if isinstance(choices, list) else 0
            if "timeline" in parsed:
                r.has_timeline = True
            if "stakes_tracking" in parsed:
                r.has_stakes = True
        except json.JSONDecodeError as exc:
            r.json_errors.append(str(exc)[:120])

    # Canon fidelity
    protag = FULL_BIBLE.get("character_sheet", {}).get("name", "")
    if protag:
        r.protagonist_name_correct = protag.lower() in text.lower()

    universes = FULL_BIBLE.get("meta", {}).get("universes", [])
    r.universe_refs = sum(1 for u in universes if u.lower() in text.lower())

    text_lower = text.lower()
    r.canon_chars_referenced = sum(
        1 for name in _canon_names() if name.lower() in text_lower
    )


def eval_archivist(text: str, r: RoundResult) -> None:
    r.word_count = len(text.split())
    r.output_length = len(text)

    blocks = extract_json_blocks(text)
    r.json_blocks_found = len(blocks)

    delta_fields = [
        "relationship_updates",
        "character_voice_updates",
        "knowledge_updates",
        "costs_paid_refinements",
        "near_misses_refinements",
        "pending_consequences_refinements",
        "divergence_refinements",
        "new_divergences",
        "new_butterfly_effects",
        "protagonist_status_json",
        "summary",
    ]

    for block in blocks:
        try:
            parsed = json.loads(block)
            r.json_blocks_valid += 1
            populated = sum(1 for f in delta_fields if parsed.get(f))
            r.delta_fields_populated = max(r.delta_fields_populated, populated)
            r.bible_delta_valid = populated >= 3
        except json.JSONDecodeError as exc:
            r.json_errors.append(str(exc)[:120])

    protag = FULL_BIBLE.get("character_sheet", {}).get("name", "")
    if protag:
        r.protagonist_name_correct = protag.lower() in text.lower()


def eval_lore_keeper(text: str, r: RoundResult) -> None:
    r.word_count = len(text.split())
    r.output_length = len(text)

    blocks = extract_json_blocks(text)
    r.json_blocks_found = len(blocks)

    for block in blocks:
        try:
            parsed = json.loads(block)
            r.json_blocks_valid += 1
            if any(k in parsed for k in ("updates", "canon_timeline_events", "coverage_assessment")):
                r.updates_structured = True
        except json.JSONDecodeError as exc:
            r.json_errors.append(str(exc)[:120])

    r.has_source_citations = bool(
        re.search(r"\[(?:WIKI|LN|ANIME|MANGA|THEORETICAL)]", text)
    )


# ═══════════════════════════════════════════════════════════════════════════
#                            API CALL
# ═══════════════════════════════════════════════════════════════════════════

def call_gemini(
    system: str,
    user_msg: str,
    *,
    json_mode: bool = False,
    max_retries: int = 6,
    retry_delay: float = 10.0,
) -> str:
    """Single Gemini call with key rotation and retry on 429/503."""
    last_err = None
    for attempt in range(max_retries):
        key = KEYS.next()
        client = genai.Client(api_key=key)

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=1.0,
            max_output_tokens=16384,
        )
        if json_mode:
            config.response_mime_type = "application/json"

        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=user_msg,
                config=config,
            )
            return resp.text or ""
        except Exception as exc:
            last_err = exc
            err_upper = str(exc).upper()
            if "429" in err_upper or "RESOURCE_EXHAUSTED" in err_upper or "503" in err_upper:
                wait = retry_delay * (2**attempt)
                print(f" [retry {attempt+1}/{max_retries}, wait {wait:.0f}s]", end="", flush=True)
                time.sleep(wait)
                continue
            raise

    raise last_err  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════
#                          TEST RUNNERS
# ═══════════════════════════════════════════════════════════════════════════

def run_storyteller(rnd: int) -> RoundResult:
    r = RoundResult(agent="storyteller", round_num=rnd)
    choice = PLAYER_CHOICES[rnd % len(PLAYER_CHOICES)]
    bible_ctx = condense_bible()

    user_msg = f"""\
=== WORLD BIBLE STATE (pre-loaded from read_bible) ===
{bible_ctx}

=== PLAYER'S CHOICE ===
The player chose: "{choice}"

=== PREVIOUS CHAPTER SUMMARY ===
Lucas went on patrol with the Wards. He encountered a temporal anomaly near the \
Boat Graveyard and dealt with it using Error Pathway abilities, but at the cost of \
significant spirituality drain and aggravating his shoulder wound. He lied to \
Clockblocker about the nature of the threat.

=== TASK ===
Write the next chapter based on the player's choice. Follow all phases.
End with the JSON metadata block containing summary, choices, timeline, and stakes.
"""

    t0 = time.time()
    try:
        output = call_gemini(_storyteller_system(), user_msg)
        r.duration_s = time.time() - t0
        r.raw_output = output
        eval_storyteller(output, r)
    except Exception as exc:
        r.duration_s = time.time() - t0
        r.success = False
        r.error = str(exc)[:200]
    return r


def run_archivist(rnd: int) -> RoundResult:
    r = RoundResult(agent="archivist", round_num=rnd)
    bible_ctx = condense_bible()

    user_msg = f"""\
=== CURRENT WORLD BIBLE STATE ===
{bible_ctx}

=== CHAPTER TEXT TO ANALYZE ===
{MOCK_CHAPTER}

=== TASK ===
Analyze the chapter and produce a BibleDelta JSON with all necessary updates.
Output ONLY a valid JSON object matching the schema in your instructions.
"""

    t0 = time.time()
    try:
        output = call_gemini(_archivist_system(), user_msg, json_mode=True)
        r.duration_s = time.time() - t0
        r.raw_output = output
        eval_archivist(output, r)
    except Exception as exc:
        r.duration_s = time.time() - t0
        r.success = False
        r.error = str(exc)[:200]
    return r


def run_lore_keeper(rnd: int) -> RoundResult:
    r = RoundResult(agent="lore_keeper", round_num=rnd)
    meta_json = json.dumps(FULL_BIBLE.get("meta", {}), indent=2)

    user_msg = f"""\
=== RESEARCH FINDINGS FROM LORE HUNTERS ===
{MOCK_RESEARCH}

=== CURRENT WORLD BIBLE (meta section) ===
{meta_json}

=== TASK ===
Consolidate the research above into structured World Bible updates.
Follow conflict resolution rules. Output as structured JSON.
"""

    t0 = time.time()
    try:
        output = call_gemini(_lore_keeper_system(), user_msg)
        r.duration_s = time.time() - t0
        r.raw_output = output
        eval_lore_keeper(output, r)
    except Exception as exc:
        r.duration_s = time.time() - t0
        r.success = False
        r.error = str(exc)[:200]
    return r


# ═══════════════════════════════════════════════════════════════════════════
#                          PRETTY PRINTING
# ═══════════════════════════════════════════════════════════════════════════

def print_result(r: RoundResult) -> None:
    status = "PASS" if r.success else "FAIL"
    json_frac = f"{r.json_blocks_valid}/{r.json_blocks_found}" if r.json_blocks_found else "0/0"

    parts = [
        f"  Round {r.round_num:2d}",
        f"{status:4s}",
        f"{r.duration_s:6.1f}s",
        f"{r.word_count:5d}w",
        f"JSON {json_frac}",
    ]

    if r.agent == "storyteller":
        ch = f"choices={r.choice_count}" if r.has_choices else "NO_CHOICES"
        tl = "TL" if r.has_timeline else "--"
        st = "ST" if r.has_stakes else "--"
        nm = "name:Y" if r.protagonist_name_correct else "name:N"
        parts += [ch, tl, st, nm, f"chars={r.canon_chars_referenced}"]

    elif r.agent == "archivist":
        dv = "VALID" if r.bible_delta_valid else "INVAL"
        parts += [f"delta:{dv}", f"fields={r.delta_fields_populated}/11"]

    elif r.agent == "lore_keeper":
        parts += [
            "STRUCT" if r.updates_structured else "UNSTRC",
            "CITED" if r.has_source_citations else "NOCIT",
        ]

    if r.error:
        parts.append(f"ERR:{r.error[:50]}")
    elif r.json_errors:
        parts.append(f"JERR:{r.json_errors[0][:40]}")

    print(" | ".join(parts))


def print_summary(results: list[RoundResult]) -> None:
    print("\n" + "=" * 80)
    print("                      AGGREGATE RESULTS")
    print("=" * 80)

    for agent in ("storyteller", "archivist", "lore_keeper"):
        ar = [r for r in results if r.agent == agent]
        if not ar:
            continue

        n = len(ar)
        ok = sum(1 for r in ar if r.success)
        avg_t = sum(r.duration_s for r in ar) / n
        tj = sum(r.json_blocks_found for r in ar)
        vj = sum(r.json_blocks_valid for r in ar)
        jr = (vj / tj * 100) if tj else 0
        nc = sum(1 for r in ar if r.protagonist_name_correct)

        print(f"\n  {agent.upper()}")
        print(f"  {'─' * 54}")
        print(f"  API Success:         {ok}/{n} ({ok / n * 100:.0f}%)")
        print(f"  Avg Latency:         {avg_t:.1f}s")
        print(f"  JSON Parse Rate:     {vj}/{tj} ({jr:.0f}%)")
        print(f"  Protagonist Name:    {nc}/{n} correct")

        if agent == "storyteller":
            aw = sum(r.word_count for r in ar) / n
            cp = sum(1 for r in ar if r.has_choices)
            tp = sum(1 for r in ar if r.has_timeline)
            sp = sum(1 for r in ar if r.has_stakes)
            ac = sum(r.canon_chars_referenced for r in ar) / n
            print(f"  Avg Word Count:      {aw:.0f}")
            print(f"  Choices Present:     {cp}/{n}")
            print(f"  Timeline Present:    {tp}/{n}")
            print(f"  Stakes Present:      {sp}/{n}")
            print(f"  Avg Canon Chars:     {ac:.1f}")

        elif agent == "archivist":
            dv = sum(1 for r in ar if r.bible_delta_valid)
            af = sum(r.delta_fields_populated for r in ar) / n
            print(f"  Delta Valid:         {dv}/{n}")
            print(f"  Avg Fields Pop'd:    {af:.1f}/11")

        elif agent == "lore_keeper":
            su = sum(1 for r in ar if r.updates_structured)
            sc = sum(1 for r in ar if r.has_source_citations)
            print(f"  Structured Output:   {su}/{n}")
            print(f"  Source Citations:     {sc}/{n}")

    print("\n" + "=" * 80)


def save_results(results: list[RoundResult], *, save_outputs: bool = False) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Summary JSON
    summary_path = RESULTS_DIR / f"test_{ts}.json"
    data = {
        "model": MODEL,
        "rounds": max((r.round_num for r in results), default=0),
        "timestamp": ts,
        "results": [],
    }
    for r in results:
        entry: dict = {
            "agent": r.agent,
            "round": r.round_num,
            "success": r.success,
            "error": r.error,
            "duration_s": round(r.duration_s, 2),
            "word_count": r.word_count,
            "json_blocks_found": r.json_blocks_found,
            "json_blocks_valid": r.json_blocks_valid,
            "json_errors": r.json_errors,
            "protagonist_name_correct": r.protagonist_name_correct,
            "canon_chars_referenced": r.canon_chars_referenced,
        }
        if r.agent == "storyteller":
            entry.update(
                has_choices=r.has_choices,
                choice_count=r.choice_count,
                has_timeline=r.has_timeline,
                has_stakes=r.has_stakes,
            )
        elif r.agent == "archivist":
            entry.update(
                bible_delta_valid=r.bible_delta_valid,
                delta_fields_populated=r.delta_fields_populated,
            )
        elif r.agent == "lore_keeper":
            entry.update(
                updates_structured=r.updates_structured,
                has_source_citations=r.has_source_citations,
            )
        data["results"].append(entry)

    with open(summary_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"\nResults saved to: {summary_path}")

    # Optionally save raw outputs
    if save_outputs:
        outputs_dir = RESULTS_DIR / f"outputs_{ts}"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        for r in results:
            if r.raw_output:
                fname = f"{r.agent}_round{r.round_num:02d}.txt"
                (outputs_dir / fname).write_text(r.raw_output, encoding="utf-8")
        print(f"Raw outputs saved to: {outputs_dir}/")


# ═══════════════════════════════════════════════════════════════════════════
#                              MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="FableWeaver Prompt Stress Test")
    parser.add_argument("--rounds", type=int, default=10, help="Rounds per agent (default: 10)")
    parser.add_argument(
        "--agents",
        type=str,
        default="all",
        help="Comma-separated: all, storyteller, archivist, lorekeeper",
    )
    parser.add_argument("--delay", type=float, default=10.0, help="Seconds between API calls (default: 10)")
    parser.add_argument("--save-outputs", action="store_true", help="Save raw model outputs to files")
    args = parser.parse_args()

    agent_set: set[str] = set()
    if args.agents == "all":
        agent_set = {"storyteller", "archivist", "lore_keeper"}
    else:
        for a in args.agents.split(","):
            a = a.strip().lower().replace("lorekeeper", "lore_keeper")
            if a in ("storyteller", "archivist", "lore_keeper"):
                agent_set.add(a)

    if not agent_set:
        print("No valid agents specified. Use: storyteller, archivist, lorekeeper")
        sys.exit(1)

    print("=" * 80)
    print("             FABLEWEAVER PROMPT STRESS TEST")
    print("=" * 80)
    print(f"  Model:     {MODEL}")
    print(f"  Rounds:    {args.rounds}")
    print(f"  Agents:    {', '.join(sorted(agent_set))}")
    print(f"  Delay:     {args.delay}s between calls")
    print(f"  Outputs:   {'saved' if args.save_outputs else 'discarded'}")
    print("=" * 80)

    runners = {
        "archivist": run_archivist,
        "lore_keeper": run_lore_keeper,
        "storyteller": run_storyteller,
    }

    all_results: list[RoundResult] = []

    for agent in sorted(agent_set):
        print(f"\n{'─' * 64}")
        print(f"  Testing: {agent.upper()}")
        print(f"{'─' * 64}")

        run_fn = runners[agent]
        for rnd in range(1, args.rounds + 1):
            print(f"  Round {rnd}/{args.rounds}...", end="", flush=True)

            result = run_fn(rnd)
            all_results.append(result)

            # Overwrite the "Round X..." line
            print("\r", end="")
            print_result(result)

            if rnd < args.rounds:
                time.sleep(args.delay)

    print_summary(all_results)
    save_results(all_results, save_outputs=args.save_outputs)


if __name__ == "__main__":
    main()
