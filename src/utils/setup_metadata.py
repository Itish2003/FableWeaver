"""
Setup Metadata Utilities

Safe extraction and application of setup wizard metadata to agent prompts.
Only generates conditional instructions when metadata explicitly requires them.
Preserves all existing prompt logic unchanged.
"""
import json
import logging
from typing import Dict, Any, Optional
from sqlalchemy import select
from src.database import AsyncSessionLocal
from src.models import WorldBible

logger = logging.getLogger("fable.setup_metadata")


async def get_setup_metadata(story_id: str) -> Dict[str, Any]:
    """
    Safely read setup metadata from World Bible.

    Returns dict with keys:
    - power_level: str (street|city|planetary|cosmic)
    - isolation_strategy: bool
    - story_tone: str (dark|balanced|comedic|grimdark)
    - themes: list[str]
    - research_focus: list[str]
    - user_intent: str

    Returns empty dict if metadata not found (backward compatible with old stories).
    """
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(WorldBible).where(WorldBible.story_id == story_id)
            result = await session.execute(stmt)
            bible = result.scalar_one_or_none()

            if not bible or "meta" not in bible.content:
                return {}

            meta = bible.content.get("meta", {})

            return {
                "power_level": meta.get("power_level", "city"),
                "isolation_strategy": meta.get("isolation_strategy", False),
                "story_tone": meta.get("story_tone", "balanced"),
                "themes": meta.get("themes", []),
                "research_focus": meta.get("research_focus", []),
                "user_intent": meta.get("user_intent", ""),
            }
    except Exception as e:
        logger.warning(f"Could not read setup metadata for {story_id}: {str(e)}")
        return {}


def generate_lore_keeper_metadata_section(metadata: Dict[str, Any]) -> str:
    """
    Generate ONLY a Lore Keeper section if isolation strategy is enabled.

    This is a PURE ADDITION to existing prompts - nothing is removed or changed.
    Only appears in prompt if user explicitly enabled isolation.
    """
    if not metadata.get("isolation_strategy", False):
        return ""  # No addition needed for normal workflows

    research_focus = metadata.get("research_focus", [])
    focus_text = ""
    if "power_systems" in research_focus:
        focus_text += "\n   - POWER MECHANICS (isolated): Focus on how powers work mechanically"

    return f"""
═══════════════════════════════════════════════════════════════════════════════
                    SETUP CONTEXT: POWERSET ISOLATION STRATEGY
═══════════════════════════════════════════════════════════════════════════════

User explicitly requested ISOLATED POWERSET from source universe context.

**FOR THIS STORY:**
- Extract and document ONLY power mechanics (how it works)
- Exclude source-universe-specific lore, culture, politics, timeline
- Put any source-context references in 'source_universe_context' field (for reference only)
- Storyteller will IGNORE source_universe_context field

**WHEN UPDATING POWER ORIGINS:**
If OC has powers from another universe:
1. Document techniques, limitations, mechanics in `canon_techniques`
2. Document combat style and signature moves
3. Include scene examples showing POWER USAGE (tactics, outcomes)
4. For source-universe-specific references: put in 'source_universe_context' object, clearly marked
5. Storyteller will read mechanics only, ignore context

**CRITICAL:** Do NOT let source universe concepts bleed into main Bible fields.
Example of WRONG:
  - "Uses Pathways [JJK concept]" → WRONG (JJK-specific)

Example of RIGHT:
  - "Uses specialized power tracks with mastery levels" → CORRECT (mechanics only)
{focus_text}
"""


def generate_storyteller_metadata_section(metadata: Dict[str, Any]) -> str:
    """
    Generate Storyteller section only if power_level requires explicit guidance.

    This is a PURE ADDITION to existing prompts.
    Only appears if power_level is planetary or cosmic (where auto-downplay is a risk).
    """
    power_level = metadata.get("power_level", "city")
    if power_level not in ["planetary", "cosmic"]:
        return ""  # No addition needed for street/city level

    tone_guidance = ""
    story_tone = metadata.get("story_tone", "balanced")
    if story_tone == "dark":
        tone_guidance = "\n- Show the weight and consequence of such power in a dark, serious tone"
    elif story_tone == "comedic":
        tone_guidance = "\n- Can play power's effectiveness for comedic effect while respecting mechanics"
    elif story_tone == "grimdark":
        tone_guidance = "\n- Show the terrible potential of such power - no holding back"

    return f"""
═══════════════════════════════════════════════════════════════════════════════
               SETUP CONTEXT: {power_level.upper()}-SCALE POWER USAGE
═══════════════════════════════════════════════════════════════════════════════

**CRITICAL POWER LEVEL GUIDANCE:**

User specified OC has {power_level.upper()}-LEVEL POWER.
This means: DEMONSTRATE THE FULL POWER AT SCALE.

**DO NOT:**
- ✗ Artificially limit power to create "challenge"
- ✗ Treat planetary-level power like city-level
- ✗ Invent limitations not documented in World Bible
- ✗ Make opposition match power through raw strength

**DO:**
- ✓ Use documented power at its stated scale
- ✓ Opposition must counter the power (strategy, weakness exploitation, specific counters)
- ✓ Show WHY character can't solo everything: cost/cooldown/mastery level/specific weakness
- ✓ Demonstrate the power exactly as originally wielder would use it{tone_guidance}

**EXAMPLE - WRONG:**
OC has Gojo's Infinity (planetary scale):
  - "Infinity creates minor inconvenience in combat"
  - "Attacker manages to graze OC despite Infinity"
  ✗ This violates documented power level

**EXAMPLE - RIGHT:**
OC has Gojo's Infinity (planetary scale):
  - "Nothing touches OC while Infinity is active (exactly as documented)"
  - "Opposition must counter with Technique Reversal or similar specific counter"
  - "Or OC has limited energy/cooldown limiting sustained use"
  ✓ This respects documented power level while showing balance through mechanics

**IF YOU FIND YOURSELF LIMITING POWER:**
- Ask: Is this limitation documented in `power_origins`?
- If NO: Don't invent it. Use power at full scale.
- If YES: Apply it consistently.

Remember: CANONICAL CONSTRAINTS (cooldowns, costs, weaknesses) ARE THE BALANCE.
Do NOT add extra artificial limits.
"""


def generate_archivist_metadata_section(metadata: Dict[str, Any]) -> str:
    """
    Generate Archivist section only if isolation strategy needs reinforcement.

    This is a PURE ADDITION to existing prompts.
    Helps prevent context leakage during updates.
    """
    if not metadata.get("isolation_strategy", False):
        return ""  # No addition needed for normal workflows

    return """
═══════════════════════════════════════════════════════════════════════════════
                    SETUP CONTEXT: POWERSET ISOLATION MONITORING
═══════════════════════════════════════════════════════════════════════════════

**WATCH FOR CONTEXT LEAKAGE:**

User requested ISOLATED POWERSET. As you update the World Bible this turn,
monitor for source-universe context bleeding in:

**DANGER ZONES:**
- Character voice updates that sound like source-universe speech patterns
- Power usage descriptions that reference source-universe mechanics/names
- Knowledge boundaries that assume source-universe rules apply
- Relationships that reference source-universe characters/factions

**IF YOU DETECT LEAKAGE:**
If a power update mentions source-universe concepts:
1. Extract the mechanic (what actually happened)
2. Move source references to `source_universe_context` field
3. Rewrite mechanic in story-universe terms

Example WRONG:
  - "OC used Cursed Technique Reversal on the attacker"
  - "OC's Infinity blocked the Domain"

Example RIGHT:
  - "OC used their signature defensive technique counter on the attacker"
  - "OC's primary protective power blocked the spatial manipulation"

Note: This is OPTIONAL cleanup. Only if you notice obvious source-universe terminology.
"""
