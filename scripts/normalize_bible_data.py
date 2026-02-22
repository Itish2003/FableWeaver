#!/usr/bin/env python3
"""
Migration script to normalize World Bible data formats.

This script fixes:
1. character_voices: Converts string fields to arrays where schema expects arrays
2. character_voices: Renames legacy field names to match schema
3. character_sheet: Maps legacy status fields to expected format

Run with: python scripts/normalize_bible_data.py
"""

import asyncio
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from src.database import AsyncSessionLocal
from src.models import WorldBible


# Fields that should be arrays in character_voices
ARRAY_FIELDS = [
    'speech_patterns',
    'verbal_tics',
    'topics_they_discuss',
    'topics_they_avoid',
    'dialogue_examples',
]

# Field name mappings (old -> new)
FIELD_RENAMES = {
    'example_quotes': 'dialogue_examples',
    'topics_to_discuss': 'topics_they_discuss',
    'topics_to_avoid': 'topics_they_avoid',
    'example_dialogue': 'dialogue_examples',  # Merge into dialogue_examples
}

# Status field mappings for character_sheet
STATUS_MAPPINGS = {
    'health': 'condition',  # health -> condition
}


def convert_to_array(value):
    """Convert a string value to an array."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        # Try to split by common delimiters
        if '. ' in value and not value.endswith('.'):
            # Sentence-style: "Formal. Mocking. Playful."
            return [s.strip() for s in value.split('. ') if s.strip()]
        elif ', ' in value:
            # Comma-separated: "Formal, mocking, playful"
            return [s.strip() for s in value.split(', ') if s.strip()]
        else:
            # Single item
            return [value] if value.strip() else []
    return [str(value)]


def normalize_character_voices(voices: dict) -> tuple[dict, list[str]]:
    """Normalize character_voices data. Returns (normalized_data, changes_made)."""
    changes = []
    normalized = {}

    for char_name, voice_data in voices.items():
        if not isinstance(voice_data, dict):
            normalized[char_name] = voice_data
            continue

        new_voice = {}

        for field, value in voice_data.items():
            new_field = field
            new_value = value

            # Check for field renames
            if field in FIELD_RENAMES:
                new_field = FIELD_RENAMES[field]
                changes.append(f"  {char_name}: Renamed '{field}' -> '{new_field}'")

            # Convert to array if needed
            if new_field in ARRAY_FIELDS and not isinstance(value, list):
                new_value = convert_to_array(value)
                if new_value != value:
                    changes.append(f"  {char_name}.{new_field}: Converted string to array ({len(new_value)} items)")

            # Handle merging (e.g., example_dialogue into dialogue_examples)
            if new_field in new_voice and isinstance(new_voice[new_field], list):
                if isinstance(new_value, list):
                    new_voice[new_field].extend(new_value)
                else:
                    new_voice[new_field].append(new_value)
                changes.append(f"  {char_name}.{new_field}: Merged from '{field}'")
            else:
                new_voice[new_field] = new_value

        normalized[char_name] = new_voice

    return normalized, changes


def normalize_character_sheet(sheet: dict) -> tuple[dict, list[str]]:
    """Normalize character_sheet data. Returns (normalized_data, changes_made)."""
    changes = []

    if not isinstance(sheet, dict):
        return sheet, changes

    # Normalize status fields
    if 'status' in sheet and isinstance(sheet['status'], dict):
        status = sheet['status']

        # Map health -> condition if condition doesn't exist
        if 'health' in status and 'condition' not in status:
            status['condition'] = status['health']
            changes.append(f"  status: Copied 'health' -> 'condition'")

        # Ensure knowledge array exists
        if 'knowledge' not in sheet:
            sheet['knowledge'] = []
            changes.append(f"  Added empty 'knowledge' array")

    return sheet, changes


async def migrate_story(story_id: str, dry_run: bool = True) -> list[str]:
    """Migrate a single story's World Bible. Returns list of changes."""
    all_changes = []

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WorldBible).where(WorldBible.story_id == story_id)
        )
        bible = result.scalar_one_or_none()

        if not bible:
            return [f"Story {story_id}: No World Bible found"]

        content = bible.content
        if not content:
            return [f"Story {story_id}: Empty content"]

        all_changes.append(f"\n=== Story: {story_id} ===")

        # Normalize character_voices
        if 'character_voices' in content and isinstance(content['character_voices'], dict):
            normalized_voices, voice_changes = normalize_character_voices(content['character_voices'])
            if voice_changes:
                all_changes.append("character_voices:")
                all_changes.extend(voice_changes)
                if not dry_run:
                    content['character_voices'] = normalized_voices

        # Normalize character_sheet
        if 'character_sheet' in content and isinstance(content['character_sheet'], dict):
            normalized_sheet, sheet_changes = normalize_character_sheet(content['character_sheet'])
            if sheet_changes:
                all_changes.append("character_sheet:")
                all_changes.extend(sheet_changes)
                if not dry_run:
                    content['character_sheet'] = normalized_sheet

        if not dry_run and len(all_changes) > 1:  # More than just the header
            bible.content = content
            flag_modified(bible, "content")
            await session.commit()
            all_changes.append("  [COMMITTED]")
        elif dry_run and len(all_changes) > 1:
            all_changes.append("  [DRY RUN - No changes made]")
        else:
            all_changes.append("  No changes needed")

    return all_changes


async def migrate_all(dry_run: bool = True):
    """Migrate all World Bibles."""
    print(f"\n{'='*60}")
    print(f"World Bible Data Normalization {'(DRY RUN)' if dry_run else '(LIVE)'}")
    print(f"{'='*60}\n")

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(WorldBible.story_id))
        story_ids = [row[0] for row in result.fetchall()]

    print(f"Found {len(story_ids)} stories to process.\n")

    all_changes = []
    for story_id in story_ids:
        changes = await migrate_story(story_id, dry_run)
        all_changes.extend(changes)

    print("\n".join(all_changes))

    if dry_run:
        print(f"\n{'='*60}")
        print("This was a DRY RUN. To apply changes, run with --apply")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv

    if not dry_run:
        print("\n⚠️  APPLYING CHANGES TO DATABASE ⚠️\n")
        confirm = input("Are you sure? (type 'yes' to confirm): ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            sys.exit(0)

    asyncio.run(migrate_all(dry_run))
