"""
Script to fix World Bible by programmatically invoking the Archivist
with explicit chapter metadata and instructions to call update_bible.
"""
import asyncio
import json
import os
from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.genai import Client

# Add parent to path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.auth import get_api_key
from src.tools.core_tools import BibleTools
from src.config import get_settings

STORY_ID = "d41bbcb6-b9ba-4696-ad25-fc075e6a58dc"

# Chapter 13 metadata
CHAPTER_13_DATA = {
    "chapter_number": 13,
    "summary": "A slice-of-life chapter focusing on the Dallon-Pelham family dynamics following the Boardwalk event. The family relaxes with pizza and video games, but tensions regarding the 'Blindfold' vigilante persist. Amy confesses to Lucian that she felt a familiar safety with the rogue, noticing similarities in their protective mannerisms, though she accepts the logical impossibility of them being the same person. Lucian nearly exposes himself with a slip of the tongue during a game. The chapter ends with a tender moment between Lucian and Amy, reinforcing his vow to protect her, before he sneaks out as Blindfold to proactively hunt down threats like Bakuda.",
    "timeline": {
        "chapter_start_date": "April 16, 2011 (Evening)",
        "chapter_end_date": "April 16, 2011 (Night)",
        "time_elapsed": "4 hours",
        "canon_events_addressed": ["Bakuda's initial testing explosions (referenced)"],
        "divergences_created": ["None significant this chapter (character focus)"]
    },
    "stakes_tracking": {
        "costs_paid": ["Emotional guilt over lying to Amy"],
        "near_misses": ["Lucian almost revealing identity with 'blindfolded' joke"],
        "power_debt_incurred": {"Limitless": "none"},
        "consequences_triggered": ["Amy's suspicion of a connection between Lucian and Blindfold deepens"]
    },
    "character_voices_used": ["Amy Dallon (vulnerable, observant)", "Crystal (sarcastic, relaxed)", "Eric (gamer, sibling rivalry)", "Carol (pragmatic, rigid)"],
    "relationship_changes": [
        {"character": "Amy Dallon", "change": "Confessed feeling safe with Blindfold, suspects connection to Lucian but dismisses it"},
        {"character": "Crystal", "change": "Relaxed family bonding during game night"},
        {"character": "Eric", "change": "Sibling rivalry during video games"}
    ]
}

# Chapter 14 metadata
CHAPTER_14_DATA = {
    "chapter_number": 14,
    "summary": "Lucian and Amy spend time together preparing for an upcoming gala. Amy opens up about her body image issues while Victoria helps with fashion. Lucian investigates Bakuda's bombing pattern as Blindfold. The chapter explores the deepening bond between Lucian and Amy, with Amy becoming emotionally reliant on her interactions with 'Blindfold' without knowing it's Lucian.",
    "timeline": {
        "chapter_start_date": "April 17, 2011 (Early Morning)",
        "chapter_end_date": "April 17, 2011 (Night)",
        "time_elapsed": "18 hours",
        "canon_events_addressed": ["Bakuda's testing phase (Investigated)", "Public support for New Wave growing"],
        "divergences_created": ["None significant, purely character development"]
    },
    "stakes_tracking": {
        "costs_paid": ["Lucian's guilt over Amy's attachment to his lie"],
        "near_misses": ["Amy sensing biological anomalies in Lucian due to prolonged proximity"],
        "power_debt_incurred": {"Six Eyes": "low"},
        "consequences_triggered": ["Amy's emotional reliance on 'Blindfold' increases"]
    },
    "character_voices_used": ["Victoria (bubbly, pushy)", "Amy (withdrawn, sarcastic)", "Lucian (protective, dual-natured)", "Crystal (grounded, observant)"],
    "relationship_changes": [
        {"character": "Amy Dallon", "change": "Emotional reliance on Blindfold increases, sensed biological anomalies in Lucian"},
        {"character": "Victoria Dallon", "change": "Helped Amy with fashion, bubbly and supportive"},
        {"character": "Crystal", "change": "Grounded observer of family dynamics"}
    ]
}


def create_fix_archivist(story_id: str) -> Agent:
    """Create a special Archivist agent focused on fixing missing Bible entries."""
    settings = get_settings()

    key = get_api_key()
    os.environ["GOOGLE_API_KEY"] = key

    bible = BibleTools(story_id)

    return Agent(
        name="fix_archivist",
        model=settings.model_archivist,
        tools=[
            bible.update_bible,
            bible.read_bible,
        ],
        instruction="""
You are a DATABASE REPAIR agent. Your ONLY job is to call `update_bible` to fix missing data.

## CRITICAL RULES:
1. You MUST call `update_bible` for EVERY item listed below
2. Do NOT just output text summaries - actually CALL THE TOOLS
3. After all tool calls complete, output a brief confirmation

## YOUR TASK:
Based on the chapter metadata provided, you must update the World Bible with:

### 1. CHARACTER VOICES (update `character_voices.<CharacterName>`)
For each character in `character_voices_used`, if they don't have a complete profile, add/update:
```
character_voices.<CharacterName>: {
    "speech_patterns": "...",
    "vocabulary_level": "...",
    "verbal_tics": "...",
    "emotional_tells": "How noted in the chapter data",
    "chapter_noted": <chapter_number>
}
```

### 2. RELATIONSHIPS (update `character_sheet.relationships.<CharacterName>`)
For each relationship change noted, update:
```
character_sheet.relationships.<CharacterName>: {
    "type": "family/ally/etc",
    "trust": "level",
    "dynamics": "Description from chapter",
    "last_interaction": "Chapter X - what happened"
}
```

### 3. KNOWLEDGE BOUNDARIES (if secrets were revealed/suspected)
Update `knowledge_boundaries.character_secrets` or `knowledge_boundaries.character_knowledge_limits`

## EXECUTION:
1. First, call `read_bible("character_voices")` to see existing entries
2. First, call `read_bible("character_sheet.relationships")` to see existing entries
3. Then call `update_bible` for EACH missing/outdated entry
4. Output "REPAIR COMPLETE" when done

DO NOT SKIP THE TOOL CALLS. Your output is worthless without the actual database updates.
"""
    )


async def run_fix():
    """Run the fix by directly calling Bible tools - no LLM needed."""
    print("=" * 60)
    print("WORLD BIBLE REPAIR SCRIPT")
    print("=" * 60)

    bible = BibleTools(STORY_ID)

    # ============================================
    # FIX 1: Update Character Voices
    # ============================================
    print("\n[STEP 1] Updating Character Voices...")

    voice_updates = {
        "Amy Dallon": {
            "speech_patterns": "Reserved, deflective, uses sarcasm as defense",
            "vocabulary_level": "educated/medical",
            "verbal_tics": "Sighs, self-deprecating humor",
            "emotional_tells": "Withdraws when uncomfortable, opens up when feels safe",
            "topics_to_avoid": ["Her powers' true nature", "Her feelings about Victoria"],
            "chapter_observations": {
                "13": "vulnerable, observant - confessed feeling safe with Blindfold",
                "14": "withdrawn, sarcastic - sensed biological anomalies in Lucian"
            }
        },
        "Crystal": {
            "speech_patterns": "Casual, uses humor to defuse tension",
            "vocabulary_level": "casual/modern",
            "verbal_tics": "Sarcastic remarks, eye-rolls",
            "emotional_tells": "Uses humor when observing family tension",
            "chapter_observations": {
                "13": "sarcastic, relaxed during game night",
                "14": "grounded, observant of family dynamics"
            }
        },
        "Eric": {
            "speech_patterns": "Competitive, uses gaming terminology",
            "vocabulary_level": "casual/gamer",
            "verbal_tics": "Trash talk, competitive banter",
            "emotional_tells": "Gets loud when losing, smug when winning",
            "chapter_observations": {
                "13": "gamer, sibling rivalry during video games"
            }
        },
        "Victoria Dallon": {
            "speech_patterns": "Enthusiastic, uses emphatic language",
            "vocabulary_level": "casual/expressive",
            "verbal_tics": "Says 'like' often, dramatic emphasis",
            "emotional_tells": "Voice rises when excited, protective growl when angry",
            "chapter_observations": {
                "14": "bubbly, pushy - helped Amy with fashion choices"
            }
        }
    }

    for char_name, voice_data in voice_updates.items():
        result = await bible.update_bible(f"character_voices.{char_name}", voice_data)
        print(f"  ✓ {char_name}: {result}")

    # ============================================
    # FIX 2: Update Relationships
    # ============================================
    print("\n[STEP 2] Updating Relationships...")

    relationship_updates = {
        "Amy Dallon": {
            "type": "family",
            "relation": "adoptive sister",
            "trust": "high",
            "knows_secret_identity": False,
            "suspects_blindfold_connection": True,
            "dynamics": "Feels safe with Lucian, emotionally reliant on 'Blindfold' persona, sensed biological anomalies",
            "last_interaction": "Chapter 14 - Shopping for gala, deepening emotional attachment",
            "emotional_state": "Growing attachment to both Lucian and Blindfold without connecting them"
        },
        "Crystal": {
            "type": "family",
            "relation": "cousin",
            "trust": "high",
            "dynamics": "Relaxed family bonding, uses humor to navigate family tensions",
            "last_interaction": "Chapter 13-14 - Game night and family activities"
        },
        "Eric": {
            "type": "family",
            "relation": "cousin",
            "trust": "medium",
            "dynamics": "Sibling-like rivalry, competitive during games",
            "last_interaction": "Chapter 13 - Video game competition"
        },
        "Victoria Dallon": {
            "type": "family",
            "relation": "adoptive sister",
            "trust": "high",
            "knows_secret_identity": True,
            "dynamics": "Supportive sister, helped Amy with fashion, bubbly and encouraging",
            "last_interaction": "Chapter 14 - Helped Amy prepare for gala"
        }
    }

    for char_name, rel_data in relationship_updates.items():
        result = await bible.update_bible(f"character_sheet.relationships.{char_name}", rel_data)
        print(f"  ✓ {char_name}: {result}")

    # ============================================
    # FIX 3: Update Knowledge Boundaries
    # ============================================
    print("\n[STEP 3] Updating Knowledge Boundaries...")

    # Read current knowledge boundaries
    current_kb = await bible.read_bible("knowledge_boundaries")
    kb_data = json.loads(current_kb)

    # Update Amy's knowledge limits
    kb_data["character_knowledge_limits"]["Amy Dallon"] = {
        "knows": [
            "Lucian is Infinity (public hero)",
            "Blindfold saved her at the bank",
            "Blindfold feels familiar/safe"
        ],
        "doesnt_know": [
            "Lucian is Blindfold",
            "Lucian's full power capabilities"
        ],
        "suspects": [
            "Some connection between Lucian and Blindfold (dismissed as impossible)",
            "Biological anomalies in Lucian (noticed during proximity)"
        ]
    }

    # Add Amy's secret about sensing anomalies
    if "character_secrets" not in kb_data:
        kb_data["character_secrets"] = {}

    kb_data["character_secrets"]["Amy Dallon (Blindfold suspicion)"] = {
        "secret": "Amy noticed familiar protective mannerisms in Blindfold similar to Lucian, and sensed biological anomalies when near him",
        "known_by": ["Amy (subconsciously)"],
        "absolutely_hidden_from": ["Carol", "Victoria"],
        "status": "dismissed as impossible but subconsciously noted"
    }

    result = await bible.update_bible("knowledge_boundaries", kb_data)
    print(f"  ✓ Knowledge boundaries: {result}")

    # ============================================
    # FIX 4: Fix Story Timeline Events with proper dates
    # ============================================
    print("\n[STEP 4] Fixing Story Timeline Events...")

    # Read current timeline
    current_timeline = await bible.read_bible("story_timeline")
    timeline_data = json.loads(current_timeline)

    # Fix events with missing dates
    fixed_events = []
    for event in timeline_data.get("events", []):
        if event.get("date") == "?" or not event.get("date"):
            # Try to infer date from event content
            event_text = event.get("event", "").lower()
            if "bakuda" in event_text and "testing" in event_text:
                event["date"] = "April 16-17, 2011"
            elif "public support" in event_text:
                event["date"] = "April 17, 2011"
            elif "bank heist" in event_text or "boardwalk" in event_text:
                event["date"] = "April 16, 2011"
        fixed_events.append(event)

    timeline_data["events"] = fixed_events
    result = await bible.update_bible("story_timeline", timeline_data)
    print(f"  ✓ Timeline events fixed: {result}")

    # ============================================
    # FIX 5: Fix Divergences with proper structure
    # ============================================
    print("\n[STEP 5] Fixing Divergences Structure...")

    # Read current divergences
    current_divs = await bible.read_bible("divergences")
    divs_data = json.loads(current_divs)

    # Ensure all divergences have proper structure
    fixed_divs = []
    for i, div in enumerate(divs_data.get("list", [])):
        if isinstance(div, dict):
            # Ensure it has an ID
            if "id" not in div or not div["id"] or div["id"] == "no-id":
                div["id"] = f"div_{i+1:03d}"
            # Ensure it has proper fields
            if "severity" not in div:
                div["severity"] = "minor"
            if "status" not in div:
                div["status"] = "active"
            if "ripple_effects" not in div:
                div["ripple_effects"] = []
            fixed_divs.append(div)
        elif isinstance(div, str):
            # Convert string to proper structure
            fixed_divs.append({
                "id": f"div_{i+1:03d}",
                "chapter": div.get("chapter", "?"),
                "severity": "minor",
                "status": "active",
                "canon_event": "Unknown",
                "what_changed": div if isinstance(div, str) else str(div),
                "cause": "OC intervention",
                "ripple_effects": []
            })

    divs_data["list"] = fixed_divs

    # Update stats
    major_count = sum(1 for d in fixed_divs if d.get("severity") == "major")
    minor_count = len(fixed_divs) - major_count
    divs_data["stats"] = {
        "total": len(fixed_divs),
        "major": major_count,
        "minor": minor_count
    }

    result = await bible.update_bible("divergences", divs_data)
    print(f"  ✓ Divergences fixed: {result}")

    print("-" * 60)
    print("Repair script complete!")

    # Verify the updates
    print("\n" + "=" * 60)
    print("VERIFICATION - Checking updated Bible...")
    print("=" * 60)

    # Check character voices
    voices = await bible.read_bible("character_voices")
    voices_data = json.loads(voices)
    print(f"\nCharacter Voices: {len(voices_data)} entries")
    print(f"  Keys: {list(voices_data.keys())}")

    # Check relationships
    rels = await bible.read_bible("character_sheet.relationships")
    rels_data = json.loads(rels)
    print(f"\nRelationships: {len(rels_data)} entries")
    print(f"  Keys: {list(rels_data.keys())}")

    # Check knowledge boundaries
    kb = await bible.read_bible("knowledge_boundaries")
    kb_data = json.loads(kb)
    print(f"\nKnowledge Boundaries:")
    print(f"  Character secrets: {list(kb_data.get('character_secrets', {}).keys())}")
    print(f"  Character knowledge limits: {list(kb_data.get('character_knowledge_limits', {}).keys())}")

    # Check story timeline
    timeline = await bible.read_bible("story_timeline")
    timeline_data = json.loads(timeline)
    events_with_dates = sum(1 for e in timeline_data.get("events", []) if e.get("date") and e.get("date") != "?")
    print(f"\nStory Timeline:")
    print(f"  Total events: {len(timeline_data.get('events', []))}")
    print(f"  Events with valid dates: {events_with_dates}")

    # Check divergences
    divs = await bible.read_bible("divergences")
    divs_data = json.loads(divs)
    divs_with_ids = sum(1 for d in divs_data.get("list", []) if d.get("id") and d.get("id") != "no-id")
    print(f"\nDivergences:")
    print(f"  Total: {len(divs_data.get('list', []))}")
    print(f"  With proper IDs: {divs_with_ids}")
    print(f"  Stats: {divs_data.get('stats', {})}")


if __name__ == "__main__":
    asyncio.run(run_fix())
