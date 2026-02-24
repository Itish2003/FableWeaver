import json
import asyncio
from typing import Optional, Any, List
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from src.database import AsyncSessionLocal
from src.models import WorldBible
from datetime import datetime
from src.utils.bible_validator import (
    validate_and_fix_bible_entry,
    check_power_origin_context_leakage,
    validate_bible_section,
    clean_power_origin_context,  # FIX #33: Automatic context isolation
)

# Paths
BIBLE_PATH = "src/world_bible.json"


def get_enhanced_default_bible():
    """Returns an enhanced World Bible template with timeline tracking."""
    return {
        "meta": {
            "title": "",
            "universes": [],
            "timeline_deviation": "",
            "genre": "",
            "theme": "",
            "story_start_date": "",  # When the story begins in-universe
            "current_story_date": "",  # Current point in the narrative
        },
        "character_sheet": {
            "name": "",
            "archetype": "",
            "status": {},
            "powers": {},
            "inventory": [],
            "relationships": {},
            "knowledge": []  # What the protagonist knows
        },
        "power_origins": {
            # Track where OC's powers come from and how they were used by the original wielder
            # This enables the Storyteller to write accurate power usage and explore potential
            "sources": [
                # Example structure:
                # {
                #     "power_name": "Limitless / Six Eyes",
                #     "original_wielder": "Gojo Satoru",
                #     "source_universe": "Jujutsu Kaisen",
                #     "canon_techniques": [
                #         {"name": "Infinity", "description": "...", "limitations": "..."},
                #         {"name": "Cursed Technique Lapse: Blue", "description": "...", "limitations": "..."},
                #     ],
                #     "technique_combinations": [
                #         {"name": "Hollow Purple", "components": ["Blue", "Red"], "description": "..."}
                #     ],
                #     "mastery_progression": ["Basic Infinity", "Six Eyes awakening", "Blue/Red mastery", "Hollow Purple", "Domain Expansion"],
                #     "unexplored_potential": ["Theoretical applications not shown in canon"],
                #     "weaknesses_and_counters": ["Domain Amplification", "Binding Vows"],
                #     "training_methods": ["How the original character trained"],
                #     "oc_current_mastery": "Where the OC is in the progression"
                # }
            ],
            "power_interactions": [],  # How powers from different sources might interact
            "theoretical_evolutions": []  # Unexplored combinations or developments
        },
        "world_state": {
            "characters": {},
            "factions": {},
            "locations": {
                # Structure for rich world-building and location-aware narratives
                # "LocationName": {
                #     "name": "The Docks",
                #     "type": "neighborhood/building/landmark/city/region",
                #     "city": "Brockton Bay",
                #     "description": "Industrial waterfront area, heavily damaged and largely abandoned.",
                #     "controlled_by": "Contested (ABB, Merchants)",
                #     "atmosphere": "Gritty, dangerous, decaying industrial",
                #     "key_features": [
                #         "Boat Graveyard - ship wreckage from economic collapse",
                #         "Abandoned warehouses used as gang hideouts"
                #     ],
                #     "adjacent_to": ["Downtown", "Trainyard", "Boardwalk"],
                #     "characters_associated": ["Lung", "Oni Lee", "Skidmark"],
                #     "story_hooks": [
                #         "Frequent gang clashes - good for patrol encounters",
                #         "Hidden entrances to Coil's underground base"
                #     ],
                #     "canon_events_here": [
                #         {"date": "April 2011", "event": "Taylor vs Lung", "status": "upcoming"}
                #     ],
                #     "current_state": "Damaged but functional",
                #     "security_level": "Low - gang territory",
                #     "source": "[WIKI]"
                # }
            },
            "territory_map": {
                # Quick reference for faction control over areas
                # "LocationName": "FactionName"
            },
            "magic_system": {},
            # Entity aliasing to prevent AI confusion (e.g., "Taylor" = "Skitter" = "Weaver")
            "entity_aliases": {
                # "canonical_name": ["alias1", "alias2", ...]
            }
        },
        "character_voices": {
            # Structure for maintaining consistent dialogue patterns
            # "CharacterName": {
            #     "speech_patterns": ["formal", "uses contractions", "verbose"],
            #     "vocabulary_level": "academic/casual/street/archaic",
            #     "verbal_tics": ["says 'you know' often", "trails off..."],
            #     "topics_they_discuss": ["magic theory", "combat tactics"],
            #     "topics_they_avoid": ["their past", "emotions"],
            #     "dialogue_examples": ["Actual quotes from canon"],
            #     "source": "[WIKI]/[LN]/[ANIME]"
            # }
        },
        "knowledge_boundaries": {
            # CRITICAL: Separates reader knowledge from character knowledge
            "meta_knowledge_forbidden": [
                # Things the READER knows but CHARACTERS don't
                # Example for Worm: "Shards", "Entities", "Cauldron's true purpose", "Trigger event mechanics"
            ],
            "character_secrets": {
                # What specific characters are hiding from others
                # "CharacterName": {
                #     "secret": "Description of what they're hiding",
                #     "known_by": ["List of characters who know"],
                #     "absolutely_hidden_from": ["Characters who must NOT know"]
                # }
            },
            "character_knowledge_limits": {
                # What each character DOES and DOESN'T know
                # "CharacterName": {
                #     "knows": ["List of things they know"],
                #     "doesnt_know": ["List of things they're unaware of"],
                #     "suspects": ["Things they suspect but can't confirm"]
                # }
            },
            "common_knowledge": [
                # Things that are public/common knowledge in-universe
                # (as opposed to reader-only or character-specific knowledge)
            ]
        },
        "stakes_and_consequences": {
            # Tracks costs paid and near-misses to prevent "effortless wins"
            "costs_paid": [
                # {"chapter": X, "cost": "description", "severity": "minor/moderate/severe/permanent"}
            ],
            "near_misses": [
                # {"chapter": X, "what_almost_happened": "description", "saved_by": "how they escaped"}
            ],
            "pending_consequences": [
                # {"action": "what OC did", "predicted_consequence": "what should happen", "due_by": "when"}
            ],
            "power_usage_debt": {
                # Track overuse of powers that should have consequences
                # "power_name": {"uses_this_chapter": N, "strain_level": "low/medium/high/critical"}
            }
        },
        "canon_character_integrity": {
            # Prevents "Worfing" - making canon characters weaker to make OC look good
            "protected_characters": [
                # {
                #     "name": "Character Name",
                #     "minimum_competence": "Description of their baseline capability",
                #     "signature_moments": ["Things they MUST be able to do"],
                #     "intelligence_level": "genius/smart/average/etc",
                #     "cannot_be_beaten_by": ["Types of opponents they'd realistically defeat"],
                #     "anti_worf_notes": "What NOT to do with this character"
                # }
            ],
            "jobber_prevention_rules": [
                # General rules like "Gojo cannot be easily surprised by basic attacks"
            ]
        },
        "canon_timeline": {
            # Structure: List of canonical events from source material
            # Each event: {"date": "...", "event": "...", "universe": "...", "importance": "major/minor", "status": "upcoming/occurred/modified/prevented"}
            "events": [],
            "current_position": "",  # Where we are in canon timeline
            "notes": ""
        },
        "story_timeline": {
            # Events that have happened in THIS story
            "events": [],
            "chapter_dates": []  # Track what date each chapter covers
        },
        "divergences": {
            # Track how this story differs from canon
            # Each: {"canon_event": "...", "what_changed": "...", "cause": "...", "ripple_effects": [...]}
            "list": [],
            "butterfly_effects": []  # Predicted consequences of divergences
        },
        "upcoming_canon_events": {
            # Events that should happen soon based on story's current timeline position
            # The Storyteller should either incorporate these or explain why they don't happen
            "events": [],
            "integration_notes": ""
        }
    }


async def get_default_bible_content():
    """Returns a fresh, empty World Bible template for new stories.

    NOTE: Previously this read from src/world_bible.json, but that caused
    data contamination between stories. New stories now always start fresh.
    """
    return get_enhanced_default_bible()

class BibleTools:
    def __init__(self, story_id: str):
        self.story_id = story_id

    async def read_bible(self, key: Optional[str] = None) -> str:
        """
        Reads a section of the World Bible from the database.
        Args:
            key: The key to read (e.g. 'world_state', 'characters'). If None, returns the whole bible.
        Keys can be nested using dot notation (e.g. 'character_sheet.status').
        """
        async with AsyncSessionLocal() as session:
            stmt = select(WorldBible).where(WorldBible.story_id == self.story_id)
            result = await session.execute(stmt)
            bible = result.scalar_one_or_none()
            
            if not bible:
                return "Error: World Bible not found for this story."
            
            data = bible.content
            
            if not key:
                return json.dumps(data, indent=2)
            
            keys = key.split('.')
            val = data
            for k in keys:
                if isinstance(val, dict) and k in val:
                    val = val[k]
                else:
                    return f"Key '{key}' not found."
            
            return json.dumps(val, indent=2)

    async def update_bible(self, key: str, value: Any, max_retries: int = 3) -> str:
        """
        Updates the World Bible in the database using optimistic concurrency control.
        Key should be dot notation. Value should be a JSON-serializable object or string.

        Implements optimistic locking with version_number field to handle concurrent updates
        from multiple agents (e.g., Lore Keeper batched updates + Archivist updates).

        Args:
            key: Dot-notation path to the field being updated (e.g., "power_origins.sources")
            value: The value to set
            max_retries: Number of times to retry on version conflict (default 3)

        Returns:
            Success or error message. On version conflict after max retries, returns error.
        """
        import copy
        import logging
        logger = logging.getLogger("fable.core_tools")

        for attempt in range(max_retries):
            try:
                async with AsyncSessionLocal() as session:
                    # Step 1: Read current version (no lock needed for optimistic)
                    stmt = select(WorldBible).where(
                        WorldBible.story_id == self.story_id
                    )
                    result = await session.execute(stmt)
                    bible = result.scalar_one_or_none()

                    if not bible:
                        return "Error: World Bible not found."

                    # Capture version at read time
                    original_version = bible.version_number

                    # Step 2: Make local modifications
                    data = copy.deepcopy(bible.content) if bible.content else {}
                    keys = key.split('.')
                    current = data
                    for k in keys[:-1]:
                        if k not in current:
                            current[k] = {}
                        current = current[k]

                    # Validate and fix the value before saving (converts legacy formats)
                    fixed_value = validate_and_fix_bible_entry(key, value)

                    # Step 2.5: Schema validation (non-blocking in warn mode)
                    from src.config import get_settings
                    settings = get_settings()
                    validation_mode = settings.bible_schema_validation_mode
                    validated_value = validate_bible_section(key, fixed_value, mode=validation_mode)
                    current[keys[-1]] = validated_value

                    # FIX #33: Check for and clean power context leakage
                    # Handle both dict (single power) and list (multiple powers) formats
                    if "power_origins" in key:
                        # First, detect any leakage (for monitoring)
                        targets = validated_value if isinstance(validated_value, list) else [validated_value]
                        cleaned_targets = []

                        for target in targets:
                            if isinstance(target, dict):
                                # Check for leakage
                                leakage_warnings = check_power_origin_context_leakage(target)
                                if leakage_warnings:
                                    for warning in leakage_warnings:
                                        logger.warning(
                                            f"⚠️  CONTEXT LEAKAGE DETECTED in '{key}': {warning}"
                                        )
                                    # Automatically clean the power origin
                                    cleaned_target = clean_power_origin_context(target)
                                    logger.info(
                                        f"✓ CONTEXT ISOLATION APPLIED: Universe-specific terms cleaned from '{key}'. "
                                        f"Power can now safely be used in any story setting."
                                    )
                                    cleaned_targets.append(cleaned_target)
                                else:
                                    cleaned_targets.append(target)
                            else:
                                cleaned_targets.append(target)

                        # Update with cleaned values
                        if isinstance(validated_value, list):
                            validated_value = cleaned_targets
                        elif cleaned_targets:
                            validated_value = cleaned_targets[0]

                        # Update the value in the dict
                        current[keys[-1]] = validated_value

                    # Step 3: Attempt write with version check
                    # Use scalar query to bypass SQLAlchemy identity map and get fresh version from DB
                    current_version = await session.scalar(
                        select(WorldBible.version_number).where(
                            WorldBible.story_id == self.story_id
                        )
                    )

                    if current_version != original_version:
                        # Version mismatch: another update occurred while we were modifying
                        await session.rollback()
                        if attempt < max_retries - 1:
                            wait_time = 0.1 * (2 ** attempt)  # Exponential backoff: 0.1s, 0.2s, 0.4s
                            logger.debug(
                                f"Version conflict on '{key}' (v{original_version} → v{current_version}). "
                                f"Retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})"
                            )
                            await asyncio.sleep(wait_time)
                            continue  # Retry the entire operation
                        else:
                            return (
                                f"Error updating '{key}': Version conflict after {max_retries} retries. "
                                "Too many concurrent updates."
                            )

                    # Step 4: Commit with incremented version
                    # Re-fetch bible object for commit (identity map has current version now)
                    bible_for_commit = await session.execute(
                        select(WorldBible).where(WorldBible.story_id == self.story_id)
                    )
                    bible_for_commit = bible_for_commit.scalar_one_or_none()
                    bible_for_commit.content = data
                    bible_for_commit.version_number += 1
                    flag_modified(bible_for_commit, "content")

                    await session.commit()

                    logger.debug(
                        f"Successfully updated '{key}' (v{original_version} → v{bible_for_commit.version_number})"
                    )

                    # Sync to disk for debugging (User Requirement)
                    try:
                        with open(BIBLE_PATH, 'w') as f:
                            json.dump(data, f, indent=2)
                    except Exception as e:
                        logger.warning("Failed to sync bible to disk: %s", e)

                    return f"Successfully updated '{key}'."

            except Exception as e:
                logger.error(f"Error in update_bible attempt {attempt + 1}: {str(e)}")
                try:
                    await session.rollback()
                except Exception:
                    pass
                if attempt == max_retries - 1:
                    return f"Error updating bible after {max_retries} retries: {str(e)}"
                # Otherwise, retry the loop

        return f"Error: Failed to update '{key}' after {max_retries} retries."

    async def get_upcoming_canon_events(self, count: int = 5) -> str:
        """
        Returns the next N canonical events that should occur based on current story position.
        Use this to check what canon events are approaching that should be incorporated or addressed.
        Filters events to only show those AFTER the current story date.
        """
        async with AsyncSessionLocal() as session:
            stmt = select(WorldBible).where(WorldBible.story_id == self.story_id)
            result = await session.execute(stmt)
            bible = result.scalar_one_or_none()

            if not bible or not bible.content:
                return "Error: World Bible not found."

            data = bible.content
            canon_events = data.get("canon_timeline", {}).get("events", [])
            current_date_str = data.get("meta", {}).get("current_story_date", "")

            # Parse current story date (handle various formats)
            def parse_year(date_str: str) -> int:
                """Extract year from date string for comparison."""
                if not date_str:
                    return 0
                import re
                # Try to find a 4-digit year
                match = re.search(r'(\d{4})', str(date_str))
                if match:
                    return int(match.group(1))
                return 0

            current_year = parse_year(current_date_str)

            # Filter for events that are:
            # 1. Marked as "upcoming" (not occurred/modified/prevented)
            # 2. Have a date AT or AFTER the current story date
            def is_upcoming(event):
                if event.get("status") != "upcoming":
                    return False
                event_year = parse_year(event.get("date", ""))
                # If we can't parse years, include it (safer)
                if current_year == 0 or event_year == 0:
                    return True
                # Only show events from current year onwards
                return event_year >= current_year

            upcoming_events = [e for e in canon_events if is_upcoming(e)]

            # Sort by date (approximate - by year)
            upcoming_events.sort(key=lambda e: parse_year(e.get("date", "9999")))

            # Take the closest N events
            upcoming_events = upcoming_events[:count]

            if not upcoming_events:
                return f"No upcoming canon events after {current_date_str or 'current position'}. The story may have diverged significantly or all major events have been addressed."

            result_text = f"**UPCOMING CANON EVENTS** (from {current_date_str or 'current position'}):\n\n"
            for event in upcoming_events:
                importance_marker = "⚠️ " if event.get('importance') == 'major' else ""
                result_text += f"{importance_marker}[{event.get('date', 'Unknown')}] {event.get('event', 'Unknown event')}\n"
                result_text += f"   Universe: {event.get('universe', 'Unknown')} | Characters: {', '.join(event.get('characters_involved', []))}\n\n"

            return result_text

    async def check_timeline_position(self) -> str:
        """
        Returns current story position in the canonical timeline, including:
        - Current in-story date
        - Recent canon events that should have occurred
        - Upcoming events to consider
        """
        async with AsyncSessionLocal() as session:
            stmt = select(WorldBible).where(WorldBible.story_id == self.story_id)
            result = await session.execute(stmt)
            bible = result.scalar_one_or_none()

            if not bible or not bible.content:
                return "Error: World Bible not found."

            data = bible.content
            meta = data.get("meta", {})
            canon_timeline = data.get("canon_timeline", {})
            story_timeline = data.get("story_timeline", {})
            divergences = data.get("divergences", {})

            report = "**TIMELINE STATUS REPORT**\n\n"
            report += f"Story Start Date: {meta.get('story_start_date', 'Not set')}\n"
            report += f"Current Story Date: {meta.get('current_story_date', 'Not set')}\n"
            report += f"Canon Position: {canon_timeline.get('current_position', 'Not set')}\n\n"

            # Recent story events
            story_events = story_timeline.get("events", [])[-5:]
            if story_events:
                report += "**Recent Story Events:**\n"
                for e in story_events:
                    report += f"- {e.get('date', '?')}: {e.get('event', '?')}\n"
                report += "\n"

            # Divergences
            divs = divergences.get("list", [])
            if divs:
                report += f"**Active Divergences from Canon:** {len(divs)}\n"
                for d in divs[-3:]:
                    report += f"- {d.get('canon_event', '?')} → {d.get('what_changed', '?')}\n"
                report += "\n"

            # Upcoming canon events
            canon_events = canon_timeline.get("events", [])
            upcoming = [e for e in canon_events if e.get("status") == "upcoming"][:3]
            if upcoming:
                report += "**Upcoming Canon Events to Address:**\n"
                for e in upcoming:
                    report += f"- [{e.get('date', '?')}] {e.get('event', '?')}\n"

            return report

    async def record_divergence(
        self,
        canon_event: str,
        what_changed: str,
        cause: str,
        ripple_effects: Optional[List[str]] = None,
        severity: str = "minor",
        affected_canon_events: Optional[List[str]] = None
    ) -> str:
        """
        Records a divergence from canon with enhanced tracking.
        Args:
            canon_event: The canonical event that was changed/prevented
            what_changed: How it changed in this story
            cause: What caused the divergence (usually OC's actions)
            ripple_effects: List of predicted consequences (each will be tracked with probability)
            severity: 'major' (changes core plot), 'minor' (character-level changes), 'cosmetic' (flavor only)
            affected_canon_events: List of canon event names this divergence impacts
        """
        async with AsyncSessionLocal() as session:
            stmt = select(WorldBible).where(WorldBible.story_id == self.story_id)
            result = await session.execute(stmt)
            bible = result.scalar_one_or_none()

            if not bible or not bible.content:
                return "Error: World Bible not found."

            data = bible.content
            if "divergences" not in data:
                data["divergences"] = {"list": [], "butterfly_effects": [], "stats": {"total": 0, "major": 0, "minor": 0}}

            # Generate unique divergence ID
            div_count = len(data["divergences"]["list"]) + 1
            div_id = f"div_{div_count:03d}"

            # Get current chapter from meta
            current_chapter = data.get("meta", {}).get("current_chapter", 1)

            # Enhanced ripple effects structure with probability tracking
            enhanced_ripples = []
            if ripple_effects:
                for effect in ripple_effects:
                    enhanced_ripples.append({
                        "effect": effect,
                        "probability": "high" if severity == "major" else "medium",
                        "materialized": False,
                        "materialized_chapter": None
                    })

            divergence = {
                "id": div_id,
                "chapter": current_chapter,
                "severity": severity,
                "status": "active",
                "canon_event": canon_event,
                "what_changed": what_changed,
                "cause": cause,
                "ripple_effects": enhanced_ripples,
                "affected_canon_events": affected_canon_events or [],
                "recorded_at": datetime.now().isoformat()
            }

            data["divergences"]["list"].append(divergence)

            # Update stats
            if "stats" not in data["divergences"]:
                data["divergences"]["stats"] = {"total": 0, "major": 0, "minor": 0}
            data["divergences"]["stats"]["total"] += 1
            if severity == "major":
                data["divergences"]["stats"]["major"] += 1
            else:
                data["divergences"]["stats"]["minor"] += 1

            # Add ripple effects to butterfly_effects for tracking
            if ripple_effects:
                data["divergences"]["butterfly_effects"].extend(ripple_effects)

            bible.content = data
            flag_modified(bible, "content")
            await session.commit()

            severity_emoji = "🔴" if severity == "major" else "🟡"
            return f"{severity_emoji} Recorded divergence [{div_id}]: '{canon_event}' → '{what_changed}' (Ch.{current_chapter}, {severity})"

    async def materialize_ripple_effect(self, divergence_id: str, effect_text: str, chapter: int) -> str:
        """
        Marks a predicted ripple effect as having actually occurred.
        Call when a previously predicted consequence actually happens.
        """
        async with AsyncSessionLocal() as session:
            stmt = select(WorldBible).where(WorldBible.story_id == self.story_id)
            result = await session.execute(stmt)
            bible = result.scalar_one_or_none()

            if not bible or not bible.content:
                return "Error: World Bible not found."

            data = bible.content
            divergences = data.get("divergences", {}).get("list", [])

            for div in divergences:
                if div.get("id") == divergence_id:
                    for ripple in div.get("ripple_effects", []):
                        if effect_text.lower() in ripple.get("effect", "").lower():
                            ripple["materialized"] = True
                            ripple["materialized_chapter"] = chapter
                            bible.content = data
                            flag_modified(bible, "content")
                            await session.commit()
                            return f"✓ Ripple effect materialized in Ch.{chapter}: {effect_text}"

            return "Ripple effect not found."

    async def advance_story_date(self, new_date: str, events_occurred: Optional[List[str]] = None) -> str:
        """
        Advances the current story date and records what happened.
        Use at the end of each chapter to track timeline progression.
        Args:
            new_date: The new current date in the story
            events_occurred: List of significant events that happened
        """
        async with AsyncSessionLocal() as session:
            stmt = select(WorldBible).where(WorldBible.story_id == self.story_id)
            result = await session.execute(stmt)
            bible = result.scalar_one_or_none()

            if not bible or not bible.content:
                return "Error: World Bible not found."

            data = bible.content

            # Update current date
            if "meta" not in data:
                data["meta"] = {}
            old_date = data["meta"].get("current_story_date", "Unknown")
            data["meta"]["current_story_date"] = new_date

            # Record in story timeline
            if "story_timeline" not in data:
                data["story_timeline"] = {"events": [], "chapter_dates": []}

            if events_occurred:
                for event in events_occurred:
                    data["story_timeline"]["events"].append({
                        "date": new_date,
                        "event": event,
                        "source": "story"
                    })

            data["story_timeline"]["chapter_dates"].append(new_date)

            bible.content = data
            flag_modified(bible, "content")
            await session.commit()

            return f"Advanced story date from {old_date} to {new_date}. Recorded {len(events_occurred or [])} events."

    # ═══════════════════════════════════════════════════════════════════════════════
    #                     CANON VS STORY COMPARISON TOOLS
    # ═══════════════════════════════════════════════════════════════════════════════

    def _parse_date(self, date_str: str):
        """Parse various date formats into datetime."""
        if not date_str:
            return None

        import re
        from datetime import datetime as dt

        # Common formats: "April 2011", "April 5, 2011", "2011-04-05"
        formats = [
            "%B %Y",           # "April 2011"
            "%B %d, %Y",       # "April 5, 2011"
            "%Y-%m-%d",        # "2011-04-05"
            "%d %B %Y",        # "5 April 2011"
        ]

        for fmt in formats:
            try:
                return dt.strptime(date_str, fmt)
            except ValueError:
                continue

        # Try to extract year at minimum
        year_match = re.search(r'(\d{4})', date_str)
        if year_match:
            return dt(int(year_match.group(1)), 1, 1)

        return None

    def _extract_keywords(self, text: str) -> set:
        """Extract meaningful keywords from event text."""
        stopwords = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "vs", "with", "by", "is", "was", "are", "were"}
        words = text.lower().split()
        return {w for w in words if w not in stopwords and len(w) > 2}

    async def find_matching_story_event(
        self,
        canon_event: dict,
        story_events: List[dict],
        tolerance_days: int = 30
    ) -> Optional[tuple]:
        """
        Multi-factor matching algorithm for canon-to-story event matching.
        Returns: (matching_event, similarity_score, match_type) or None
        """
        best_match = None
        best_score = 0.0
        best_type = "unaddressed"

        canon_date = self._parse_date(canon_event.get("date", ""))
        canon_characters = set(canon_event.get("characters_involved", []))
        canon_event_text = canon_event.get("event", "").lower()
        canon_keywords = self._extract_keywords(canon_event_text)

        for story_event in story_events:
            score = 0.0
            story_date = self._parse_date(story_event.get("date", ""))
            story_event_text = story_event.get("event", "").lower()

            # Factor 1: Date proximity (0-30 points)
            if canon_date and story_date:
                days_diff = abs((story_date - canon_date).days)
                if days_diff <= tolerance_days:
                    score += max(0, 30 - days_diff)

            # Factor 2: Character overlap (0-30 points)
            story_characters = set(story_event.get("characters_involved", []))
            if canon_characters and story_characters:
                overlap = len(canon_characters & story_characters)
                total = len(canon_characters | story_characters)
                score += (overlap / total) * 30 if total > 0 else 0

            # Factor 3: Keyword similarity (0-40 points)
            story_keywords = self._extract_keywords(story_event_text)
            keyword_overlap = len(canon_keywords & story_keywords)
            total_keywords = len(canon_keywords | story_keywords)
            score += (keyword_overlap / total_keywords) * 40 if total_keywords > 0 else 0

            # Normalize to 0-1 range
            normalized_score = score / 100.0

            if normalized_score > best_score:
                best_score = normalized_score
                best_match = story_event

                if normalized_score >= 0.8:
                    best_type = "exact"
                elif normalized_score >= 0.5:
                    best_type = "modified"
                elif normalized_score >= 0.3:
                    best_type = "partial"
                else:
                    best_type = "unaddressed"

        if best_match and best_score > 0.2:
            return (best_match, best_score, best_type)
        return None

    async def calculate_event_pressure(self, event: dict) -> dict:
        """
        Calculate pressure score for a canon event.
        Formula: P = (Ic * Td * Pd * Cd) / Nf
        - Ic = Importance (major=3, minor=1, background=0.5)
        - Td = Time Distance (10 / days_remaining)
        - Pd = Plot Dependency (events that depend on this)
        - Cd = Character Involvement (protagonist = 1.5x)
        - Nf = Narrative Flexibility (world events = 0.5)
        """
        async with AsyncSessionLocal() as session:
            stmt = select(WorldBible).where(WorldBible.story_id == self.story_id)
            result = await session.execute(stmt)
            bible = result.scalar_one_or_none()

            if not bible:
                return {"error": "World Bible not found"}

            data = bible.content

        current_date = data.get("meta", {}).get("current_story_date", "")
        current_dt = self._parse_date(current_date)
        event_dt = self._parse_date(event.get("date", ""))

        # Factor 1: Importance Coefficient (Ic)
        importance_map = {"major": 3.0, "minor": 1.0, "background": 0.5}
        Ic = importance_map.get(event.get("importance", "minor"), 1.0)

        # Factor 2: Time Distance (Td)
        if current_dt and event_dt:
            days_remaining = (event_dt - current_dt).days
        else:
            days_remaining = 30

        Td = max(0.1, 10 / (max(days_remaining, 0) + 1))

        # Factor 3: Plot Dependency (Pd)
        consequences = event.get("consequences", [])
        all_events = data.get("canon_timeline", {}).get("events", [])
        dependent_count = sum(
            1 for e in all_events
            if any(c in str(e) for c in consequences)
        )
        Pd = 1.0 + (dependent_count * 0.3)

        # Factor 4: Character Involvement (Cd)
        protagonist_name = data.get("character_sheet", {}).get("name", "")
        involved_characters = event.get("characters_involved", [])
        Cd = 1.5 if protagonist_name in involved_characters else 1.0

        # Factor 5: Narrative Flexibility (Nf)
        universe_scope = len(event.get("characters_involved", [])) > 5
        Nf = 0.5 if universe_scope else 1.0

        # Calculate final pressure
        pressure_score = min(10.0, (Ic * Td * Pd * Cd) / Nf)

        # Determine urgency level
        if pressure_score >= 8.0 or days_remaining <= 0:
            urgency = "critical"
            recommendation = "MUST address in next chapter"
        elif pressure_score >= 6.0 or days_remaining <= 3:
            urgency = "high"
            recommendation = "Should address within 1-2 chapters"
        elif pressure_score >= 4.0 or days_remaining <= 7:
            urgency = "medium"
            recommendation = "Plan to incorporate soon"
        elif pressure_score >= 2.0:
            urgency = "low"
            recommendation = "Can be addressed when narratively appropriate"
        else:
            urgency = "optional"
            recommendation = "Incorporate or skip based on story direction"

        return {
            "event": event.get("event", "Unknown"),
            "date": event.get("date", "?"),
            "pressure_score": round(pressure_score, 2),
            "urgency_level": urgency,
            "days_remaining": days_remaining,
            "factors": {
                "importance": round(Ic, 2),
                "time_distance": round(Td, 2),
                "plot_dependency": round(Pd, 2),
                "character_involvement": round(Cd, 2),
                "narrative_flexibility": round(Nf, 2)
            },
            "recommendation": recommendation
        }

    async def get_pressure_report(self, limit: int = 10) -> str:
        """
        Gets top N events by pressure score with recommendations.
        Use this to see which canon events need attention.
        """
        async with AsyncSessionLocal() as session:
            stmt = select(WorldBible).where(WorldBible.story_id == self.story_id)
            result = await session.execute(stmt)
            bible = result.scalar_one_or_none()

            if not bible:
                return "Error: World Bible not found."

            data = bible.content

        canon_events = data.get("canon_timeline", {}).get("events", [])
        upcoming_events = [e for e in canon_events if e.get("status") == "upcoming"]

        if not upcoming_events:
            return "No upcoming canon events to report on."

        # Calculate pressure for each event
        pressure_data = []
        for event in upcoming_events:
            pressure = await self.calculate_event_pressure(event)
            pressure_data.append(pressure)

        # Sort by pressure score descending
        pressure_data.sort(key=lambda x: x.get("pressure_score", 0), reverse=True)
        pressure_data = pressure_data[:limit]

        # Build report
        report = "**EVENT PRESSURE REPORT**\n\n"
        report += "Events sorted by urgency (highest first):\n\n"

        for p in pressure_data:
            urgency_icons = {
                "critical": "[!!!]",
                "high": "[!!]",
                "medium": "[!]",
                "low": "[-]",
                "optional": "[~]"
            }
            icon = urgency_icons.get(p["urgency_level"], "[-]")
            report += f"{icon} **{p['event']}** [{p['date']}]\n"
            report += f"    Pressure: {p['pressure_score']:.1f}/10 | Urgency: {p['urgency_level'].upper()}\n"
            report += f"    Days remaining: {p['days_remaining']} | {p['recommendation']}\n\n"

        return report

    async def get_mandatory_events(self) -> str:
        """
        Returns events that have crossed mandatory integration threshold.
        Events with pressure >= 7.0 or days_remaining <= 0 are mandatory.
        These MUST be addressed in the next chapter.
        """
        async with AsyncSessionLocal() as session:
            stmt = select(WorldBible).where(WorldBible.story_id == self.story_id)
            result = await session.execute(stmt)
            bible = result.scalar_one_or_none()

            if not bible:
                return "Error: World Bible not found."

            data = bible.content

        canon_events = data.get("canon_timeline", {}).get("events", [])
        upcoming_events = [e for e in canon_events if e.get("status") == "upcoming"]

        mandatory = []
        for event in upcoming_events:
            pressure = await self.calculate_event_pressure(event)
            if pressure.get("pressure_score", 0) >= 7.0 or pressure.get("days_remaining", 99) <= 0:
                mandatory.append(pressure)

        if not mandatory:
            return "No mandatory events. All upcoming events have acceptable pressure levels."

        report = "**MANDATORY EVENTS - MUST ADDRESS IN NEXT CHAPTER**\n\n"
        for m in mandatory:
            report += f"[!!!] **{m['event']}** [{m['date']}]\n"
            report += f"    Pressure: {m['pressure_score']:.1f}/10\n"
            report += f"    Days remaining: {m['days_remaining']}\n"
            report += f"    Action: {m['recommendation']}\n\n"

        return report

    async def compare_canon_to_story(self) -> str:
        """
        Compares canonical timeline events to story events.
        Returns a formatted comparison report showing matches, modifications, and divergences.
        """
        async with AsyncSessionLocal() as session:
            stmt = select(WorldBible).where(WorldBible.story_id == self.story_id)
            result = await session.execute(stmt)
            bible = result.scalar_one_or_none()

            if not bible:
                return "Error: World Bible not found."

            data = bible.content

        canon_events = data.get("canon_timeline", {}).get("events", [])
        story_events = data.get("story_timeline", {}).get("events", [])
        divergences = data.get("divergences", {}).get("list", [])
        current_date = data.get("meta", {}).get("current_story_date", "Unknown")

        report = f"""**CANON VS STORY COMPARISON REPORT**
Current Story Date: {current_date}

═══════════════════════════════════════════════════════════════════════════════
                           EVENT-BY-EVENT COMPARISON
═══════════════════════════════════════════════════════════════════════════════

"""
        matched_count = 0
        modified_count = 0
        prevented_count = 0
        unaddressed_count = 0

        for canon_event in canon_events:
            if canon_event.get("status") == "background":
                continue

            status = canon_event.get("status", "upcoming")

            if status == "prevented":
                status_icon = "[PREVENTED]"
                prevented_count += 1
                match_result = None
            elif status == "modified":
                status_icon = "[MODIFIED]"
                modified_count += 1
                match_result = await self.find_matching_story_event(canon_event, story_events)
            elif status == "occurred":
                status_icon = "[MATCHED]"
                matched_count += 1
                match_result = await self.find_matching_story_event(canon_event, story_events)
            else:
                match_result = await self.find_matching_story_event(canon_event, story_events)
                if match_result:
                    story_event, score, match_type = match_result
                    if match_type == "exact":
                        status_icon = "[MATCHED]"
                        matched_count += 1
                    else:
                        status_icon = f"[{match_type.upper()}]"
                        modified_count += 1
                else:
                    status_icon = "[UPCOMING]" if status == "upcoming" else "[UNADDRESSED]"
                    unaddressed_count += 1

            importance_marker = "**" if canon_event.get("importance") == "major" else ""
            report += f"{status_icon} [{canon_event.get('date', '?')}] {importance_marker}{canon_event.get('event', 'Unknown')}{importance_marker}\n"

            if match_result:
                story_event, score, match_type = match_result
                report += f"   → Story: {story_event.get('event', '?')} (Match: {score:.0%})\n"

            report += "\n"

        # Summary
        total = matched_count + modified_count + prevented_count + unaddressed_count
        divergence_pct = ((modified_count + prevented_count) / total * 100) if total > 0 else 0

        report += f"""═══════════════════════════════════════════════════════════════════════════════
                              SUMMARY STATISTICS
═══════════════════════════════════════════════════════════════════════════════

Matched Events:     {matched_count}/{total}
Modified Events:    {modified_count}/{total}
Prevented Events:   {prevented_count}/{total}
Unaddressed:        {unaddressed_count}/{total}

**Divergence Score: {divergence_pct:.1f}%**
"""

        if divergences:
            report += "\n**Recent Divergences:**\n"
            for div in divergences[-3:]:
                report += f"• {div.get('canon_event', '?')} → {div.get('what_changed', '?')}\n"

        return report
