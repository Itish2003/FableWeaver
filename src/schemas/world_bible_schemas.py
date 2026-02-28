"""
World Bible Schema Definitions

This module defines the canonical schemas for all World Bible data structures.
These Pydantic models serve as the single source of truth for data validation
between the backend and frontend.

Usage:
    from src.schemas import CostPaid, Divergence, PendingConsequence

    # Validate incoming data
    cost = CostPaid(cost="Emotional guilt", severity="medium", chapter=13)

    # Convert to dict for storage
    cost_dict = cost.model_dump()
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any, Union


class GeminiCompatibleModel(BaseModel):
    """
    Base model that removes 'additionalProperties' from JSON schema.
    Gemini API doesn't support this field, even when set to false.
    """
    model_config = ConfigDict(extra="forbid")

    @classmethod
    def model_json_schema(cls, **kwargs):
        schema = super().model_json_schema(**kwargs)
        # Remove additionalProperties from root and all nested schemas
        cls._remove_additional_properties(schema)
        return schema

    @staticmethod
    def _remove_additional_properties(schema: Dict[str, Any]) -> None:
        """Recursively remove additionalProperties from schema tree."""
        if isinstance(schema, dict):
            schema.pop("additionalProperties", None)
            for value in schema.values():
                GeminiCompatibleModel._remove_additional_properties(value)
        elif isinstance(schema, list):
            for item in schema:
                GeminiCompatibleModel._remove_additional_properties(item)


class CostPaid(GeminiCompatibleModel):
    """Represents a cost/sacrifice the protagonist paid in a chapter.

    Frontend expects: {cost, severity, chapter}
    """
    model_config = ConfigDict(extra="forbid")

    cost: str = Field(..., description="Description of what was lost/sacrificed")
    severity: str = Field(
        default="medium",
        description="Impact level: low | medium | high | critical"
    )
    chapter: int = Field(..., description="Chapter number where this cost was paid")

    # Note: No extra="allow" - Gemini API doesn't support additionalProperties


class NearMiss(GeminiCompatibleModel):
    """Represents a close call or near-disaster that was avoided.

    Frontend expects: {what_almost_happened, saved_by, chapter}
    """
    model_config = ConfigDict(extra="forbid")

    what_almost_happened: str = Field(
        ...,
        description="Description of what nearly went wrong"
    )
    saved_by: str = Field(
        default="Unknown",
        description="What prevented the disaster"
    )
    chapter: int = Field(..., description="Chapter number of the near miss")



class PendingConsequence(GeminiCompatibleModel):
    """Represents a future consequence that may occur due to past actions.

    Frontend expects: {action, predicted_consequence, due_by}
    Note: Does NOT include 'chapter' field - that was the old format.
    """
    model_config = ConfigDict(extra="forbid")

    action: str = Field(..., description="What the character did")
    predicted_consequence: str = Field(
        ...,
        description="What will likely happen as a result"
    )
    due_by: str = Field(
        ...,
        description="When this might occur: 'Chapter X', 'immediate', or a date"
    )



class Divergence(GeminiCompatibleModel):
    """Represents a point where the story diverges from canon.

    Frontend expects: {id, chapter, what_changed, severity, status,
                       canon_event, cause, ripple_effects, affected_canon_events}
    """
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique divergence ID (e.g., 'div_001')")
    chapter: int = Field(..., description="Chapter where divergence occurred")
    what_changed: str = Field(..., description="Description of the divergence")
    severity: str = Field(
        default="minor",
        description="Impact level: minor | moderate | major | critical"
    )
    status: str = Field(
        default="active",
        description="Current state: active | resolved | escalating"
    )
    canon_event: Optional[str] = Field(
        default="",
        description="Which canon event was affected"
    )
    cause: Optional[str] = Field(
        default="OC intervention",
        description="What caused this divergence"
    )
    ripple_effects: List[Union[str, Dict[str, Any]]] = Field(
        default_factory=list,
        description="Predicted downstream effects (strings or effect objects)"
    )
    affected_canon_events: List[str] = Field(
        default_factory=list,
        description="List of canon events affected by this divergence"
    )



class ChapterDate(GeminiCompatibleModel):
    """Represents the in-story date for a chapter.

    Frontend expects: {chapter, date}
    Note: Single 'date' field, not separate 'start'/'end' fields.
    """
    model_config = ConfigDict(extra="forbid")

    chapter: int = Field(..., description="Chapter number")
    date: str = Field(
        ...,
        description="Date string (e.g., 'April 16, 2011' or 'April 16-17, 2011')"
    )



class TimelineEvent(GeminiCompatibleModel):
    """Represents an event in the story timeline.

    Frontend expects: {event, date, chapter, type}
    """
    model_config = ConfigDict(extra="forbid")

    event: str = Field(..., description="Description of the event")
    date: str = Field(..., description="When the event occurred")
    chapter: Optional[int] = Field(default=None, description="Related chapter")
    type: str = Field(
        default="story",
        description="Event type: story | canon | divergence"
    )



class ButterflyEffect(GeminiCompatibleModel):
    """Represents a predicted butterfly effect from a divergence.

    Frontend expects: {prediction, probability, materialized, source_divergence}
    """
    model_config = ConfigDict(extra="forbid")

    prediction: str = Field(..., description="What might happen")
    probability: Optional[int] = Field(
        default=None,
        description="Likelihood percentage (0-100)"
    )
    materialized: bool = Field(
        default=False,
        description="Whether this effect has occurred"
    )
    source_divergence: Optional[str] = Field(
        default=None,
        description="ID of the divergence that caused this"
    )



class StakesTracking(GeminiCompatibleModel):
    """Container for all stakes-related data.

    Groups costs_paid, near_misses, pending_consequences, and power_debt.
    """
    model_config = ConfigDict(extra="forbid")

    costs_paid: List[CostPaid] = Field(default_factory=list)
    near_misses: List[NearMiss] = Field(default_factory=list)
    pending_consequences: List[PendingConsequence] = Field(default_factory=list)
    power_debt: Dict[str, Any] = Field(default_factory=dict)



# =============================================================================
#                  STORYTELLER OUTPUT SCHEMA (ChapterMetadata)
# =============================================================================

class ChapterMetadata(GeminiCompatibleModel):
    """
    Validated schema for the JSON metadata block the Storyteller appends
    after the narrative text in each chapter.

    All fields except ``summary`` are optional so that partial but usable
    metadata is never rejected outright.
    """
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(..., description="5-10 sentence chapter summary")
    choices: List[str] = Field(default_factory=list, description="Player choices for next chapter")
    choice_timeline_notes: Optional[Dict[str, Any]] = Field(default=None, description="Per-choice timeline impact notes")
    timeline: Optional[Dict[str, Any]] = Field(default=None, description="Chapter timeline data (start/end dates, canon events, divergences)")
    canon_elements_used: List[str] = Field(default_factory=list, description="Canon facts referenced in chapter")
    power_limitations_shown: List[str] = Field(default_factory=list, description="Power limitations demonstrated")
    stakes_tracking: Optional[Dict[str, Any]] = Field(default=None, description="Costs, near misses, consequences, power debt")
    character_voices_used: List[str] = Field(default_factory=list, description="Characters who spoke in chapter")
    questions: Optional[List[str]] = Field(default=None, description="Optional clarifying questions for next turn")


# Schema field mappings for legacy format conversion
LEGACY_FIELD_MAPPINGS = {
    "near_misses": {
        "event": "what_almost_happened",  # old -> new
    },
    "pending_consequences": {
        "consequence": "predicted_consequence",  # old -> new
    },
    "divergences": {
        "divergence": "what_changed",  # old -> new
    },
    "chapter_dates": {
        # start/end -> date (requires special handling)
    },
}


# =============================================================================
#                    ARCHIVIST OUTPUT SCHEMA (BibleDelta)
# =============================================================================

class RelationshipUpdate(GeminiCompatibleModel):
    """Update to a single relationship."""
    model_config = ConfigDict(extra="forbid")

    character_name: str = Field(..., description="Name of the character")
    type: str = Field(default="ally", description="family | ally | enemy | neutral | romantic")
    relation: Optional[str] = Field(default=None, description="Specific relation (sister, cousin, mentor)")
    trust: str = Field(default="medium", description="low | medium | high | complete")
    knows_secret_identity: Optional[bool] = Field(default=None)
    dynamics: Optional[str] = Field(default=None, description="Brief description of relationship dynamic")
    last_interaction: Optional[str] = Field(default=None, description="Chapter X - what happened")



class CharacterVoiceUpdate(GeminiCompatibleModel):
    """Update to a character's voice profile."""
    model_config = ConfigDict(extra="forbid")

    character_name: str = Field(..., description="Name of the character")
    speech_patterns: Optional[str] = Field(default=None)
    vocabulary_level: Optional[str] = Field(default=None)
    verbal_tics: Optional[str] = Field(default=None)
    emotional_tells: Optional[str] = Field(default=None)
    example_dialogue: Optional[str] = Field(default=None)



class KnowledgeUpdate(GeminiCompatibleModel):
    """Update to knowledge boundaries."""
    model_config = ConfigDict(extra="forbid")

    character_name: str = Field(..., description="Character whose knowledge changed")
    learned: List[str] = Field(default_factory=list, description="New things they learned")
    now_suspects: List[str] = Field(default_factory=list, description="New suspicions")



class DivergenceRefinement(GeminiCompatibleModel):
    """Refinement to an existing divergence entry."""
    model_config = ConfigDict(extra="forbid")

    divergence_id: str = Field(..., description="ID of divergence to refine (e.g., 'div_001')")
    canon_event: Optional[str] = Field(default=None, description="Fill in affected canon event")
    cause: Optional[str] = Field(default=None, description="Fill in cause")
    severity: Optional[str] = Field(default=None, description="Refine severity if needed")
    ripple_effects: List[str] = Field(default_factory=list, description="Add ripple effects")



class NewDivergence(GeminiCompatibleModel):
    """A new divergence to record."""
    model_config = ConfigDict(extra="forbid")

    canon_event: str = Field(..., description="The canon event that was affected")
    what_changed: str = Field(..., description="How it changed")
    cause: str = Field(default="OC intervention", description="What caused it")
    severity: str = Field(default="minor", description="minor | moderate | major | critical")
    ripple_effects: List[str] = Field(default_factory=list)
    affected_canon_events: List[str] = Field(default_factory=list)


class KnowledgeViolation(GeminiCompatibleModel):
    """Records a character who referenced knowledge they should not have."""
    model_config = ConfigDict(extra="forbid")

    character_name: str = Field(..., description="Character who committed the violation")
    concept_referenced: str = Field(..., description="The forbidden/unknown concept they referenced")
    violation_type: str = Field(
        default="forbidden",
        description="Type: 'forbidden' (meta_knowledge_forbidden) | 'doesnt_know' (character_knowledge_limits) | 'secret' (character_secrets)"
    )
    chapter: int = Field(..., description="Chapter where the violation occurred")
    quote_or_context: Optional[str] = Field(
        default=None,
        description="Brief quote or scene context where the violation occurred"
    )


class PowerUsageEntry(GeminiCompatibleModel):
    """A single power usage strain update from the Archivist."""
    model_config = ConfigDict(extra="forbid")

    power_name: str = Field(
        ...,
        description="Canonical power source name (e.g., 'Cursed Spirit Manipulation', 'Ten Shadows Technique')"
    )
    technique_used: Optional[str] = Field(
        default=None,
        description="Specific technique name if applicable"
    )
    strain_level: str = Field(
        ...,
        description="Current strain: none | low | medium | high | critical"
    )
    chapter: int = Field(
        ...,
        description="Chapter where power was used"
    )


class PowerScalingViolation(GeminiCompatibleModel):
    """Records a protected character written below their documented competence level."""
    model_config = ConfigDict(extra="forbid")

    character_name: str = Field(..., description="Protected character who was Worfed")
    what_happened: str = Field(..., description="How they were written below their competence level")
    minimum_competence_violated: Optional[str] = Field(
        default=None,
        description="Which minimum_competence rule was broken"
    )
    chapter: int = Field(..., description="Chapter where the violation occurred")
    severity: str = Field(
        default="moderate",
        description="Impact level: minor | moderate | major | critical"
    )


class BibleDelta(GeminiCompatibleModel):
    """
    Structured output schema for the Archivist agent.

    This represents all updates the Archivist wants to make to the World Bible.
    The system will process this delta and apply changes programmatically.
    """
    model_config = ConfigDict(extra="forbid")  # Gemini doesn't support additionalProperties

    # Relationship updates (character_sheet.relationships)
    relationship_updates: List[RelationshipUpdate] = Field(
        default_factory=list,
        description="Updates to character relationships"
    )

    # Character voice updates (character_voices)
    character_voice_updates: List[CharacterVoiceUpdate] = Field(
        default_factory=list,
        description="New or updated character voice profiles"
    )

    # Knowledge boundary updates
    knowledge_updates: List[KnowledgeUpdate] = Field(
        default_factory=list,
        description="Updates to what characters know/suspect"
    )

    # Stakes refinements (refine auto-added entries)
    costs_paid_refinements: List[CostPaid] = Field(
        default_factory=list,
        description="Refined cost entries with proper severity"
    )
    near_misses_refinements: List[NearMiss] = Field(
        default_factory=list,
        description="Refined near-miss entries with saved_by filled"
    )
    pending_consequences_refinements: List[PendingConsequence] = Field(
        default_factory=list,
        description="Refined or new pending consequences"
    )

    # Divergence handling
    divergence_refinements: List[DivergenceRefinement] = Field(
        default_factory=list,
        description="Refinements to auto-added divergences (fill canon_event, cause, etc.)"
    )
    new_divergences: List[NewDivergence] = Field(
        default_factory=list,
        description="Completely new divergences to record"
    )

    # Butterfly effects (predicted downstream consequences)
    new_butterfly_effects: List[ButterflyEffect] = Field(
        default_factory=list,
        description="Predicted butterfly effects from divergences"
    )

    # Protagonist status updates (JSON string to avoid additionalProperties issue)
    protagonist_status_json: Optional[str] = Field(
        default=None,
        description="JSON string of updates to character_sheet.status (health, mental state, etc.)"
    )

    # World state updates (JSON strings to avoid additionalProperties issue)
    location_updates_json: Optional[str] = Field(
        default=None,
        description="JSON string of updates to world_state.locations"
    )
    faction_updates_json: Optional[str] = Field(
        default=None,
        description="JSON string of updates to world_state.factions"
    )

    # Context leakage detection (set by Archivist when cross-universe terms are found)
    context_leakage_detected: bool = Field(
        default=False,
        description="True if source-universe terminology was found in power_origins or other lore fields"
    )
    context_leakage_details: Optional[str] = Field(
        default=None,
        description="Description of what leaked and where (e.g., 'JJK term Cursed Technique in power_origins')"
    )

    # Knowledge and power scaling violations detected by Archivist
    knowledge_violations: List[KnowledgeViolation] = Field(
        default_factory=list,
        description="Characters who referenced forbidden/unknown knowledge in this chapter"
    )
    power_scaling_violations: List[PowerScalingViolation] = Field(
        default_factory=list,
        description="Protected characters written below their documented competence level"
    )

    # Power usage strain tracking (feeds enforcement block for next chapter)
    power_usage_updates: List[PowerUsageEntry] = Field(
        default_factory=list,
        description="Power strain updates from this chapter. Track ALL powers used with their resulting strain level."
    )

    # Brief summary for logging
    summary: str = Field(
        default="",
        description="2-3 sentence summary of changes made"
    )


# ─── Lore Keeper Output Schema ─────────────────────────────────────────────────

class LoreKeeperOutput(GeminiCompatibleModel):
    """
    Structured output schema for the Lore Keeper agent during init.

    Instead of calling tools (update_bible), the Lore Keeper returns this
    structured output which is then processed to update the World Bible.
    This ensures consistent, validated data from the LLM.
    """
    model_config = ConfigDict(extra="forbid")  # Gemini doesn't support additionalProperties

    # ── Character Sheet (ALL REQUIRED) ──────────────────────────────────────
    character_name: str = Field(
        ...,
        description="The protagonist's full name (e.g., 'Kudou Kageaki')"
    )
    character_archetype: str = Field(
        ...,
        description="Brief archetype (e.g., 'The Irregular / God of Destruction')"
    )
    character_status: Dict[str, Any] = Field(
        ...,
        description="REQUIRED. Initial status: {health: str, mental_state: str, power_level: str, location: str}. Must have at least health and power_level."
    )
    character_powers: Dict[str, str] = Field(
        ...,
        description="REQUIRED. Dict of power names to descriptions. Example: {\"Cursed Spirit Manipulation\": \"Absorb and command spirits\", \"Ten Shadows\": \"Shadow-bound shikigami summoning\"}. Must list ALL protagonist powers."
    )

    # ── Power Origins (REQUIRED — at least one source) ────────────────────
    power_origins_sources: List[Dict[str, Any]] = Field(
        ...,
        description="REQUIRED. At least 1 power source. Each: {name, power_name, source_universe, canon_techniques: [{name, description, power_cost}], combat_style, signature_moves: [], limitations, weaknesses_and_counters: []}. This is the MOST IMPORTANT section."
    )

    # ── Canon Timeline Events (REQUIRED) ──────────────────────────────────
    canon_timeline_events: List[Dict[str, Any]] = Field(
        ...,
        description="REQUIRED. At least 5 dated events. Each: {date: str, event: str, universe: str, importance: 'critical'|'major'|'minor', status: 'upcoming'|'occurred'}. Include the major arcs/incidents from the source material."
    )

    # ── World State (ALL REQUIRED) ────────────────────────────────────────
    world_state_characters: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="REQUIRED. At least 5 major characters. {CharName: {role, affiliation, powers, threat_level, relationship_to_protagonist}}."
    )
    world_state_locations: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="REQUIRED. At least 3 locations. {LocationName: {description, controlled_by, key_features}}."
    )
    world_state_factions: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="REQUIRED. At least 2 factions. {FactionName: {description, members, hierarchy, disposition_to_protagonist}}."
    )
    world_state_territory_map: Dict[str, str] = Field(
        ...,
        description="REQUIRED. Quick reference: {area_name: controlling_faction}."
    )

    # ── Metadata (REQUIRED) ───────────────────────────────────────────────
    meta_universes: List[str] = Field(
        ...,
        description="REQUIRED. List of universes (e.g., ['Irregular at Magic High School', 'Jujutsu Kaisen'])"
    )
    meta_genre: str = Field(
        ...,
        description="REQUIRED. Genre (e.g., 'Dark Urban Fantasy')"
    )
    meta_theme: str = Field(
        ...,
        description="REQUIRED. Central theme/conflict"
    )
    meta_story_start_date: str = Field(
        ...,
        description="REQUIRED. Story start date (e.g., 'April 2095')"
    )

    # ── Knowledge Boundaries (REQUIRED) ───────────────────────────────────
    knowledge_meta_knowledge_forbidden: List[str] = Field(
        ...,
        description="REQUIRED. At least 3 items. Concepts characters must NEVER know (meta-knowledge from other universes, reader-only info)."
    )
    knowledge_common_knowledge: List[str] = Field(
        ...,
        description="REQUIRED. At least 3 items. Public facts everyone in-universe knows."
    )

    # ── Character Voices (REQUIRED for key characters) ────────────────────
    character_voices: Dict[str, Dict[str, str]] = Field(
        ...,
        description="REQUIRED. At least 3 characters. {CharName: {speech_patterns, vocabulary_level, verbal_tics, emotional_tells, example_dialogue}}."
    )

    # ── Character Relationships (REQUIRED) ────────────────────────────────
    character_sheet_relationships: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="REQUIRED. At least 3 relationships. {CharName: {type, relation, trust: 1-10, dynamics, knows_secret_identity: bool}}."
    )

    # ── Character Starting Knowledge (REQUIRED) ──────────────────────────
    character_sheet_knowledge: List[str] = Field(
        ...,
        description="REQUIRED. At least 5 items. What the protagonist knows at story start."
    )

    # ── Canon Character Integrity / Anti-Worfing (REQUIRED) ──────────────
    canon_character_integrity_protected: List[Dict[str, Any]] = Field(
        ...,
        description="REQUIRED. At least 3 protected characters. Each: {name, minimum_competence, signature_moments: [], anti_worf_notes}."
    )
    canon_jobber_prevention_rules: List[str] = Field(
        ...,
        description="REQUIRED. At least 3 rules preventing powerful characters from being trivialized."
    )

    # ── Character Secrets (REQUIRED) ──────────────────────────────────────
    knowledge_character_secrets: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="REQUIRED. At least 2 characters with secrets. {CharName: {secret: str, known_by: [], absolutely_hidden_from: []}}."
    )

    # ── Character Knowledge Limits (REQUIRED) ─────────────────────────────
    knowledge_character_limits: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="REQUIRED. At least 3 characters. {CharName: {knows: [], doesnt_know: [], suspects: []}}."
    )

    # ── Upcoming Canon Events (REQUIRED) ──────────────────────────────────
    upcoming_canon_events: List[Dict[str, Any]] = Field(
        ...,
        description="REQUIRED. At least 3 upcoming events the story must address. Each: {date, event, importance, integration_notes}."
    )

    # ── Power Interactions (REQUIRED for crossover stories) ───────────────
    power_interactions: List[Dict[str, str]] = Field(
        ...,
        description="REQUIRED. How powers from different sources interact. Each: {source_a, source_b, interaction, notes}."
    )

    # ── Magic System Rules (REQUIRED) ─────────────────────────────────────
    world_state_magic_system: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="REQUIRED. At least 1 system. {UniverseName: {system_name, core_rules, limitations, power_scaling}}."
    )

    # ── Entity Aliases (REQUIRED) ─────────────────────────────────────────
    world_state_entity_aliases: Dict[str, List[str]] = Field(
        ...,
        description="REQUIRED. At least 5 characters. {canonical_name: [alias1, alias2]}."
    )

    # ── Summary (REQUIRED) ────────────────────────────────────────────────
    summary: str = Field(
        ...,
        description="REQUIRED. 2-3 sentence summary of what was consolidated from the research data."
    )

