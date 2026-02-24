"""
Complete World Bible Schema - Issue #11 Schema Enforcement

This module defines the canonical unified schema for all World Bible data structures.
Consolidates partial schemas into a single source of truth with validators for:
- Legacy field name normalization (stakes_and_consequences → stakes_tracking)
- Divergence stats auto-sync
- PowerOrigin validation in sources list

All models use extra="allow" to preserve Lore Keeper free-form additions.
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, model_validator, ConfigDict
from enum import Enum

# ─── Re-export all existing partial schemas ───────────────────────────────────
from src.schemas.world_bible_schemas import (
    CostPaid, NearMiss, PendingConsequence, Divergence,
    ChapterDate, TimelineEvent, ButterflyEffect, StakesTracking,
)
from src.schemas.power_origin_schema import PowerOrigin, CanonTechnique


# ─── Enums ────────────────────────────────────────────────────────────────────

class SeverityLevel(str, Enum):
    """Severity levels for stakes and divergences"""
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TrustLevel(str, Enum):
    """Trust levels for relationships"""
    complete = "complete"
    high = "high"
    medium = "medium"
    low = "low"
    strained = "strained"
    hostile = "hostile"


class RelationshipType(str, Enum):
    """Types of relationships between characters"""
    family = "family"
    ally = "ally"
    enemy = "enemy"
    neutral = "neutral"
    romantic = "romantic"
    mentor = "mentor"
    rival = "rival"
    teammate = "teammate"


# ─── Meta ─────────────────────────────────────────────────────────────────────

class WorldMeta(BaseModel):
    """Top-level story metadata. Stored under 'meta' key in DB."""
    model_config = ConfigDict(extra="allow")

    title: str = Field(default="", description="Story title")
    universes: List[str] = Field(default_factory=list)
    timeline_deviation: str = Field(default="")
    genre: str = Field(default="")
    theme: str = Field(default="")
    story_start_date: str = Field(default="")
    current_story_date: str = Field(default="")
    current_chapter: int = Field(default=0)


# ─── Character Sheet ──────────────────────────────────────────────────────────

class CharacterStatus(BaseModel):
    """Character current physical/mental status"""
    model_config = ConfigDict(extra="allow")

    health: Optional[str] = None
    mental_state: Optional[str] = None
    power_level: Optional[str] = None
    power_strain: Optional[str] = None
    injuries: List[str] = Field(default_factory=list)
    magical_afflictions: List[str] = Field(default_factory=list)


class CharacterRelationship(BaseModel):
    """Relationship entry for one connected character"""
    model_config = ConfigDict(extra="allow")

    type: str = Field(default="ally")
    relation: Optional[str] = None
    trust: str = Field(default="medium")
    knows_secret_identity: Optional[bool] = None
    dynamics: Optional[str] = None
    last_interaction: Optional[str] = None
    family_branch: Optional[str] = None
    living_situation: Optional[str] = None
    role_in_story: Optional[str] = None


class IdentityEntry(BaseModel):
    """One identity (civilian, hero, villain, etc.) of the character"""
    model_config = ConfigDict(extra="allow")

    name: str = Field(default="")
    type: str = Field(default="civilian")
    is_public: bool = Field(default=False)
    team_affiliation: Optional[str] = None
    known_by: List[str] = Field(default_factory=list)
    suspected_by: List[str] = Field(default_factory=list)
    linked_to: List[str] = Field(default_factory=list)
    activities: List[str] = Field(default_factory=list)
    reputation: Optional[str] = None
    costume_description: Optional[str] = None


class CharacterSheet(BaseModel):
    """Complete protagonist character sheet"""
    model_config = ConfigDict(extra="allow")

    name: str = Field(default="")
    archetype: str = Field(default="")
    background: str = Field(default="")
    personality: Optional[str] = None
    motivations: List[str] = Field(default_factory=list)
    fears: List[str] = Field(default_factory=list)
    status: CharacterStatus = Field(default_factory=CharacterStatus)
    powers: Dict[str, Any] = Field(default_factory=dict)
    inventory: List[Any] = Field(default_factory=list)
    knowledge: List[str] = Field(default_factory=list)
    relationships: Dict[str, CharacterRelationship] = Field(default_factory=dict)
    identities: Dict[str, IdentityEntry] = Field(default_factory=dict)
    cape_name: Optional[str] = None


# ─── Power Origins ────────────────────────────────────────────────────────────

class PowerUsageTracking(BaseModel):
    """Track power usage across chapters"""
    model_config = ConfigDict(extra="allow")

    last_chapter: int = Field(default=0)
    strain_level: str = Field(default="low")


class PowerOriginsSection(BaseModel):
    """
    Models the actual power_origins structure agents write:
    {
      "sources": [PowerOrigin objects...],
      "power_interactions": [...],
      "theoretical_evolutions": [...],
      "usage_tracking": {power_name: PowerUsageTracking}
    }
    """
    model_config = ConfigDict(extra="allow")

    sources: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of PowerOrigin objects - validated item-by-item"
    )
    power_interactions: List[Any] = Field(default_factory=list)
    theoretical_evolutions: List[Any] = Field(default_factory=list)
    usage_tracking: Dict[str, PowerUsageTracking] = Field(default_factory=dict)
    combat_style: Optional[str] = None
    signature_moves: List[str] = Field(default_factory=list)
    canon_scene_examples: List[Dict[str, Any]] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_sources_items(self) -> "PowerOriginsSection":
        """Validate each source entry against PowerOrigin schema. Non-blocking."""
        import logging
        logger = logging.getLogger("fable.schema")
        validated = []
        for i, source in enumerate(self.sources):
            if isinstance(source, dict) and "power_name" in source and "original_wielder" in source:
                try:
                    PowerOrigin(**source)
                except Exception as e:
                    logger.warning(
                        "power_origins.sources[%d] failed PowerOrigin validation: %s", i, e
                    )
            validated.append(source)
        self.sources = validated
        return self


# ─── World State ──────────────────────────────────────────────────────────────

class LocationEntry(BaseModel):
    """One location in the world"""
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    type: Optional[str] = None
    city: Optional[str] = None
    description: Optional[str] = None
    controlled_by: Optional[str] = None
    atmosphere: Optional[str] = None
    key_features: List[str] = Field(default_factory=list)
    typical_occupants: List[str] = Field(default_factory=list)
    adjacent_to: List[str] = Field(default_factory=list)
    story_hooks: List[Any] = Field(default_factory=list)
    canon_events_here: List[Any] = Field(default_factory=list)
    current_state: Optional[str] = None
    security_level: Optional[str] = None
    source: Optional[str] = None


class FactionMember(BaseModel):
    """One member of a faction"""
    model_config = ConfigDict(extra="allow")

    name: str = Field(default="")
    cape_name: Optional[str] = None
    role: Optional[str] = None
    powers: Optional[str] = None
    family_relation: Optional[str] = None


class FactionEntry(BaseModel):
    """One faction in the world"""
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    universe: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    hierarchy: List[str] = Field(default_factory=list)
    complete_member_roster: List[FactionMember] = Field(default_factory=list)
    disposition_to_protagonist: Optional[str] = None
    source: Optional[str] = None


class WorldState(BaseModel):
    """All world-level state: locations, factions, magic systems, etc."""
    model_config = ConfigDict(extra="allow")

    characters: Dict[str, Any] = Field(default_factory=dict)
    factions: Dict[str, FactionEntry] = Field(default_factory=dict)
    locations: Dict[str, LocationEntry] = Field(default_factory=dict)
    territory_map: Dict[str, str] = Field(default_factory=dict)
    magic_system: Dict[str, Any] = Field(default_factory=dict)
    entity_aliases: Dict[str, List[str]] = Field(default_factory=dict)


# ─── Character Voices ────────────────────────────────────────────────────────

class CharacterVoiceProfile(BaseModel):
    """Voice/dialogue profile for a character"""
    model_config = ConfigDict(extra="allow")

    speech_patterns: Any = Field(default_factory=list)  # str or List[str]
    vocabulary_level: Optional[str] = None
    verbal_tics: Any = Field(default_factory=list)
    topics_to_discuss: List[str] = Field(default_factory=list)
    topics_to_avoid: List[str] = Field(default_factory=list)
    emotional_tells: Optional[str] = None
    example_dialogue: Optional[str] = None
    dialogue_examples: List[str] = Field(default_factory=list)
    source: Optional[str] = None


# ─── Knowledge Boundaries ────────────────────────────────────────────────────

class CharacterSecret(BaseModel):
    """One secret a character might know or not know"""
    model_config = ConfigDict(extra="allow")

    secret: str = Field(default="")
    known_by: List[str] = Field(default_factory=list)
    absolutely_hidden_from: List[str] = Field(default_factory=list)


class CharacterKnowledgeLimit(BaseModel):
    """What one character knows/suspects about something"""
    model_config = ConfigDict(extra="allow")

    knows: List[str] = Field(default_factory=list)
    doesnt_know: List[str] = Field(default_factory=list)
    suspects: List[str] = Field(default_factory=list)


class KnowledgeBoundaries(BaseModel):
    """All knowledge and secret boundaries"""
    model_config = ConfigDict(extra="allow")

    meta_knowledge_forbidden: List[str] = Field(default_factory=list)
    character_secrets: Dict[str, CharacterSecret] = Field(default_factory=dict)
    character_knowledge_limits: Dict[str, CharacterKnowledgeLimit] = Field(default_factory=dict)
    common_knowledge: List[str] = Field(default_factory=list)


# ─── Canon Character Integrity ───────────────────────────────────────────────

class ProtectedCharacter(BaseModel):
    """Rules for protecting a canon character from Worfing"""
    model_config = ConfigDict(extra="allow")

    name: str = Field(default="")
    minimum_competence: Optional[str] = None
    signature_moments: List[str] = Field(default_factory=list)
    intelligence_level: Optional[str] = None
    cannot_be_beaten_by: List[str] = Field(default_factory=list)
    anti_worf_notes: Optional[str] = None


class CanonCharacterIntegrity(BaseModel):
    """Anti-Worfing rules and protected character definitions"""
    model_config = ConfigDict(extra="allow")

    protected_characters: List[ProtectedCharacter] = Field(default_factory=list)
    jobber_prevention_rules: List[str] = Field(default_factory=list)


# ─── Canon Timeline ───────────────────────────────────────────────────────────

class CanonTimelineEvent(BaseModel):
    """One event in the canon timeline"""
    model_config = ConfigDict(extra="allow")

    date: str = Field(default="")
    event: str = Field(default="")
    universe: Optional[str] = None
    source: Optional[str] = None
    importance: str = Field(default="minor")
    status: str = Field(default="upcoming")
    characters_involved: List[str] = Field(default_factory=list)
    consequences: List[str] = Field(default_factory=list)


class CanonTimeline(BaseModel):
    """Timeline of canon events in source universe"""
    model_config = ConfigDict(extra="allow")

    events: List[CanonTimelineEvent] = Field(default_factory=list)
    current_position: str = Field(default="")
    notes: str = Field(default="")


# ─── Story Timeline ───────────────────────────────────────────────────────────

class StoryTimeline(BaseModel):
    """The story's personal timeline (separate from canon timeline)"""
    model_config = ConfigDict(extra="allow")

    events: List[TimelineEvent] = Field(default_factory=list)
    chapter_dates: List[ChapterDate] = Field(default_factory=list)


# ─── Divergences ──────────────────────────────────────────────────────────────

class DivergenceStats(BaseModel):
    """Statistics about divergences"""
    total: int = Field(default=0)
    major: int = Field(default=0)
    minor: int = Field(default=0)


class DivergencesSection(BaseModel):
    """Complete divergences section with statistics"""
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    list: List[Divergence] = Field(default_factory=lambda: [], alias="list")
    butterfly_effects: List[ButterflyEffect] = Field(default_factory=lambda: [])
    stats: DivergenceStats = Field(default_factory=DivergenceStats)

    @model_validator(mode="after")
    def sync_stats(self) -> "DivergencesSection":
        """Automatically sync stats from the list of divergences."""
        items = self.list
        if items:
            major = sum(1 for d in items if d.severity in ("major", "critical"))
            self.stats = DivergenceStats(
                total=len(items),
                major=major,
                minor=len(items) - major,
            )
        return self


# ─── Upcoming Canon Events ────────────────────────────────────────────────────

class UpcomingCanonEvents(BaseModel):
    """Upcoming events from canon that might intersect with story"""
    model_config = ConfigDict(extra="allow")

    events: List[Any] = Field(default_factory=list)
    integration_notes: str = Field(default="")


# ─── ROOT WorldBible ──────────────────────────────────────────────────────────

class WorldBibleSchema(BaseModel):
    """
    Unified schema for the entire World Bible content.

    All fields optional with defaults to support partial Bibles during init pipeline.
    extra="allow" at every level to preserve Lore Keeper free-form additions.
    Field names match actual DB keys.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    meta: WorldMeta = Field(default_factory=WorldMeta)
    character_sheet: CharacterSheet = Field(default_factory=CharacterSheet)
    power_origins: PowerOriginsSection = Field(default_factory=PowerOriginsSection)
    world_state: WorldState = Field(default_factory=WorldState)
    character_voices: Dict[str, CharacterVoiceProfile] = Field(default_factory=dict)
    knowledge_boundaries: KnowledgeBoundaries = Field(default_factory=KnowledgeBoundaries)

    # Dual-key stakes: normalize stakes_and_consequences → stakes_tracking at parse time
    stakes_tracking: StakesTracking = Field(default_factory=StakesTracking)
    stakes_and_consequences: Optional[StakesTracking] = Field(
        default=None,
        description="Legacy key - merged into stakes_tracking at parse time"
    )

    canon_character_integrity: CanonCharacterIntegrity = Field(
        default_factory=CanonCharacterIntegrity
    )
    canon_timeline: CanonTimeline = Field(default_factory=CanonTimeline)
    story_timeline: StoryTimeline = Field(default_factory=StoryTimeline)
    divergences: DivergencesSection = Field(default_factory=DivergencesSection)
    upcoming_canon_events: UpcomingCanonEvents = Field(default_factory=UpcomingCanonEvents)

    @model_validator(mode="after")
    def merge_legacy_stakes(self) -> "WorldBibleSchema":
        """Merge stakes_and_consequences into stakes_tracking if both present."""
        if self.stakes_and_consequences is not None:
            # Merge: stakes_tracking wins on conflict, legacy provides defaults
            merged = StakesTracking(
                costs_paid=self.stakes_tracking.costs_paid or self.stakes_and_consequences.costs_paid,
                near_misses=self.stakes_tracking.near_misses or self.stakes_and_consequences.near_misses,
                pending_consequences=(
                    self.stakes_tracking.pending_consequences
                    or self.stakes_and_consequences.pending_consequences
                ),
                power_debt=self.stakes_tracking.power_debt or self.stakes_and_consequences.power_debt,
            )
            self.stakes_tracking = merged
        return self

    @model_validator(mode="after")
    def validate_divergence_consistency(self) -> "WorldBibleSchema":
        """Sync divergence stats after parse (handled by DivergencesSection.sync_stats)."""
        return self
