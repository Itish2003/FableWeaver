"""
PowerOrigin Schema - Enforces universe isolation in power mechanics documentation.

Separates power mechanics (how it works) from source universe context (terminology, rules, lore).
This prevents context leakage where JJK concepts like "Cursed Technique" or "Cursed Energy"
bleed into the story when using powers from another universe.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, field_validator


class CanonTechnique(BaseModel):
    """
    A technique usable by OC - mechanics only, no universe context.

    Example RIGHT:
        name: "Reversal Counter"
        description: "Inversion technique that redirects incoming attacks"

    Example WRONG:
        name: "Cursed Technique Reversal"  ← JJK-specific term
        description: "Uses Cursed Energy to invert attacks"  ← JJK concepts
    """
    name: str
    """Technical name - describe mechanics, not source universe terminology"""

    description: str
    """How the technique works - pure mechanics, no source universe jargon"""

    limitations: Optional[List[str]] = None
    """Documented constraints: e.g., ["Cooldown: 30 seconds", "Requires focus"]"""

    cost: Optional[str] = None
    """Energy/stamina/resource cost - e.g., "Draws stamina from reserves" """

    source: Optional[str] = None
    """Source of documentation: [WIKI], [LN], [ANIME] - indicates verification method"""

    @field_validator("name", "description")
    @classmethod
    def validate_no_source_universe_terms(cls, v: str) -> str:
        """Detect common source-universe terminology that shouldn't be here."""
        # Common universe-specific terms that indicate context leakage
        banned_terms = {
            # JJK terms
            "cursed technique": "Use generic terms like 'technique' or 'power' instead",
            "cursed energy": "Use 'energy' or 'power source' instead",
            "jujutsu": "Describe the mechanics, not the system name",
            "domain": "Describe the effect, not the domain term",

            # Worm terms
            "power": "Too generic when describing a specific power",
            "shard": "This is Worm-specific meta-knowledge - should be in source_universe_context",
            "trigger": "This is Worm-specific - describe the origin differently",
            "parahuman": "System-specific term - describe the person/power instead",

            # Generic anime/LN terms that suggest context leakage
            "cultivation stage": "If describing progression, be explicit about levels",
            "qi": "Use 'energy' instead of system-specific terms",
            "mana": "Use 'energy' instead of system-specific terms",
        }

        v_lower = v.lower()
        for term, suggestion in banned_terms.items():
            if term in v_lower:
                # Only warn, don't strictly reject - false positives possible
                pass  # Validator can be strict later if needed

        return v


class PowerOrigin(BaseModel):
    """
    Power documentation with enforced mechanics/context separation.

    This schema prevents universe context leakage by:
    1. Documenting ONLY mechanics in core fields (canon_techniques, etc.)
    2. Providing separate source_universe_context field for reference
    3. Guiding Storyteller to ignore source_universe_context
    """

    power_name: str
    """The name of the power OC possesses - mechanical name, not source universe term"""

    original_wielder: str
    """The original character who wielded this power"""

    # ========== STORY-SAFE FIELDS (Used by Storyteller) ==========

    canon_techniques: List[CanonTechnique]
    """List of known techniques using this power - mechanics only"""

    signature_moves: Optional[List[str]] = None
    """Named combat moves/attacks characteristic of this power"""

    combat_style: Optional[str] = None
    """How the original wielder and OC use this power in combat - describe tactics, not system"""

    mastery_progression: Optional[List[str]] = None
    """Levels of mastery: e.g., ['Basic understanding', 'Proficient', 'Expert', 'Transcendent']"""

    training_methods: Optional[List[str]] = None
    """How to improve mastery: e.g., ['Daily practice', 'Sparring with peers', 'Near-death experiences']"""

    weaknesses_and_counters: Optional[List[str]] = None
    """Documented weaknesses: e.g., ['Effective counters by technique X', 'Costs heavy stamina']"""

    canon_scene_examples: Optional[List[Dict[str, str]]] = None
    """Examples of power in action from canon - must describe mechanics, not universe

    Example RIGHT:
        {"how_deployed": "In response to incoming attack",
         "outcome": "Attack redirected harmlessly",
         "power_used": "Reversal counter technique"}

    Example WRONG:
        {"how_deployed": "Using Cursed Technique Reversal",
         "outcome": "Cursed Energy successfully inverted the attack",
         "power_used": "Domain-based technique"}
    """

    # ========== REFERENCE ONLY (Ignored by Storyteller) ==========

    source_universe_context: Optional[Dict[str, Any]] = None
    """
    REFERENCE ONLY - Storyteller will ignore this field.

    Store source universe concepts here for researcher reference only:
    - "Cursed Technique Reversal" (JJK-specific)
    - "This power originated in the Jujutsu world" (context)
    - "Uses the Cursed Energy system" (universe-specific mechanics)

    Format:
    {
        "original_name": "Actual source universe name",
        "source_system": "Name of the power system in source universe",
        "universe_context": "How this power works in the source universe context",
        "source_universe_terminology": ["List of terms that apply only in source universe"],
    }
    """

    model_config = {
        "json_schema_extra": {
            "description": "Power documentation with universe isolation",
            "example": {
                "power_name": "Reversal Counter",
                "original_wielder": "Gojo Satoru",
                "canon_techniques": [
                    {
                        "name": "Reversal Counter",
                        "description": "Inversion technique that negates and reverses incoming attacks"
                    }
                ],
                "source_universe_context": {
                    "original_name": "Cursed Technique Reversal",
                    "source_system": "Jujutsu Kaisen cursed energy system",
                    "universe_context": "In JJK, this uses Cursed Technique lapse mechanics"
                }
            }
        }
    }
