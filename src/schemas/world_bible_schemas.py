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
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class CostPaid(BaseModel):
    """Represents a cost/sacrifice the protagonist paid in a chapter.

    Frontend expects: {cost, severity, chapter}
    """
    cost: str = Field(..., description="Description of what was lost/sacrificed")
    severity: str = Field(
        default="medium",
        description="Impact level: low | medium | high | critical"
    )
    chapter: int = Field(..., description="Chapter number where this cost was paid")

    # Note: No extra="allow" - Gemini API doesn't support additionalProperties


class NearMiss(BaseModel):
    """Represents a close call or near-disaster that was avoided.

    Frontend expects: {what_almost_happened, saved_by, chapter}
    """
    what_almost_happened: str = Field(
        ...,
        description="Description of what nearly went wrong"
    )
    saved_by: str = Field(
        default="Unknown",
        description="What prevented the disaster"
    )
    chapter: int = Field(..., description="Chapter number of the near miss")



class PendingConsequence(BaseModel):
    """Represents a future consequence that may occur due to past actions.

    Frontend expects: {action, predicted_consequence, due_by}
    Note: Does NOT include 'chapter' field - that was the old format.
    """
    action: str = Field(..., description="What the character did")
    predicted_consequence: str = Field(
        ...,
        description="What will likely happen as a result"
    )
    due_by: str = Field(
        ...,
        description="When this might occur: 'Chapter X', 'immediate', or a date"
    )



class Divergence(BaseModel):
    """Represents a point where the story diverges from canon.

    Frontend expects: {id, chapter, what_changed, severity, status,
                       canon_event, cause, ripple_effects, affected_canon_events}
    """
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
    ripple_effects: List[str] = Field(
        default_factory=list,
        description="Predicted downstream effects"
    )
    affected_canon_events: List[str] = Field(
        default_factory=list,
        description="List of canon events affected by this divergence"
    )



class ChapterDate(BaseModel):
    """Represents the in-story date for a chapter.

    Frontend expects: {chapter, date}
    Note: Single 'date' field, not separate 'start'/'end' fields.
    """
    chapter: int = Field(..., description="Chapter number")
    date: str = Field(
        ...,
        description="Date string (e.g., 'April 16, 2011' or 'April 16-17, 2011')"
    )



class TimelineEvent(BaseModel):
    """Represents an event in the story timeline.

    Frontend expects: {event, date, chapter, type}
    """
    event: str = Field(..., description="Description of the event")
    date: str = Field(..., description="When the event occurred")
    chapter: Optional[int] = Field(default=None, description="Related chapter")
    type: str = Field(
        default="story",
        description="Event type: story | canon | divergence"
    )



class ButterflyEffect(BaseModel):
    """Represents a predicted butterfly effect from a divergence.

    Frontend expects: {prediction, probability, materialized, source_divergence}
    """
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



class StakesTracking(BaseModel):
    """Container for all stakes-related data.

    Groups costs_paid, near_misses, pending_consequences, and power_debt.
    """
    costs_paid: List[CostPaid] = Field(default_factory=list)
    near_misses: List[NearMiss] = Field(default_factory=list)
    pending_consequences: List[PendingConsequence] = Field(default_factory=list)
    power_debt: Dict[str, Any] = Field(default_factory=dict)



# =============================================================================
#                  STORYTELLER OUTPUT SCHEMA (ChapterMetadata)
# =============================================================================

class ChapterMetadata(BaseModel):
    """
    Validated schema for the JSON metadata block the Storyteller appends
    after the narrative text in each chapter.

    All fields except ``summary`` are optional so that partial but usable
    metadata is never rejected outright.
    """
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

class RelationshipUpdate(BaseModel):
    """Update to a single relationship."""
    character_name: str = Field(..., description="Name of the character")
    type: str = Field(default="ally", description="family | ally | enemy | neutral | romantic")
    relation: Optional[str] = Field(default=None, description="Specific relation (sister, cousin, mentor)")
    trust: str = Field(default="medium", description="low | medium | high | complete")
    knows_secret_identity: Optional[bool] = Field(default=None)
    dynamics: Optional[str] = Field(default=None, description="Brief description of relationship dynamic")
    last_interaction: Optional[str] = Field(default=None, description="Chapter X - what happened")



class CharacterVoiceUpdate(BaseModel):
    """Update to a character's voice profile."""
    character_name: str = Field(..., description="Name of the character")
    speech_patterns: Optional[str] = Field(default=None)
    vocabulary_level: Optional[str] = Field(default=None)
    verbal_tics: Optional[str] = Field(default=None)
    emotional_tells: Optional[str] = Field(default=None)
    example_dialogue: Optional[str] = Field(default=None)



class KnowledgeUpdate(BaseModel):
    """Update to knowledge boundaries."""
    character_name: str = Field(..., description="Character whose knowledge changed")
    learned: List[str] = Field(default_factory=list, description="New things they learned")
    now_suspects: List[str] = Field(default_factory=list, description="New suspicions")



class DivergenceRefinement(BaseModel):
    """Refinement to an existing divergence entry."""
    divergence_id: str = Field(..., description="ID of divergence to refine (e.g., 'div_001')")
    canon_event: Optional[str] = Field(default=None, description="Fill in affected canon event")
    cause: Optional[str] = Field(default=None, description="Fill in cause")
    severity: Optional[str] = Field(default=None, description="Refine severity if needed")
    ripple_effects: List[str] = Field(default_factory=list, description="Add ripple effects")



class NewDivergence(BaseModel):
    """A new divergence to record."""
    canon_event: str = Field(..., description="The canon event that was affected")
    what_changed: str = Field(..., description="How it changed")
    cause: str = Field(default="OC intervention", description="What caused it")
    severity: str = Field(default="minor", description="minor | moderate | major | critical")
    ripple_effects: List[str] = Field(default_factory=list)
    affected_canon_events: List[str] = Field(default_factory=list)



class BibleDelta(BaseModel):
    """
    Structured output schema for the Archivist agent.

    This represents all updates the Archivist wants to make to the World Bible.
    The system will process this delta and apply changes programmatically.
    """
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

    # Brief summary for logging
    summary: str = Field(
        default="",
        description="2-3 sentence summary of changes made"
    )

