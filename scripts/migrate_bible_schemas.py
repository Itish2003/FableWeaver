"""
World Bible Schema Migration Script

This script migrates existing World Bible entries to the new canonical schemas.
It fixes legacy field formats (e.g., {consequence} -> {predicted_consequence})
and ensures all entries have the required fields.

Usage:
    # Migrate a specific story
    python scripts/migrate_bible_schemas.py --story-id <uuid>

    # Migrate all stories
    python scripts/migrate_bible_schemas.py --all

    # Dry run (show what would be changed without modifying)
    python scripts/migrate_bible_schemas.py --story-id <uuid> --dry-run
"""
import asyncio
import argparse
import json
import sys
import os
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from src.database import AsyncSessionLocal
from src.models import WorldBible, Story
from src.utils.bible_validator import (
    validate_and_fix_bible_entry,
    validate_bible_integrity
)


async def migrate_story_bible(story_id: str, dry_run: bool = False) -> dict:
    """
    Migrate a single story's World Bible to the new schema.

    Args:
        story_id: The story UUID
        dry_run: If True, don't save changes, just report what would change

    Returns:
        dict with migration results
    """
    results = {
        "story_id": story_id,
        "sections_fixed": [],
        "issues_before": [],
        "issues_after": [],
        "success": False
    }

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WorldBible).where(WorldBible.story_id == story_id)
        )
        bible = result.scalar_one_or_none()

        if not bible or not bible.content:
            results["error"] = "World Bible not found"
            return results

        import copy
        content = copy.deepcopy(bible.content)

        # Check integrity before migration
        results["issues_before"] = validate_bible_integrity(content)

        # Migrate each section
        sections_to_migrate = [
            # Stakes sections (try both possible parent keys)
            ("stakes_and_consequences", "costs_paid"),
            ("stakes_and_consequences", "near_misses"),
            ("stakes_and_consequences", "pending_consequences"),
            ("stakes_tracking", "costs_paid"),
            ("stakes_tracking", "near_misses"),
            ("stakes_tracking", "pending_consequences"),
            # Divergences
            ("divergences", "list"),
            # Timeline
            ("story_timeline", "chapter_dates"),
            ("story_timeline", "events"),
        ]

        for parent, child in sections_to_migrate:
            if parent in content and child in content[parent]:
                path = f"{parent}.{child}"
                original = content[parent][child]
                fixed = validate_and_fix_bible_entry(path, original)

                # Check if anything changed
                if json.dumps(original, sort_keys=True) != json.dumps(fixed, sort_keys=True):
                    results["sections_fixed"].append(path)
                    if not dry_run:
                        content[parent][child] = fixed

        # Also fix full sections if they exist
        full_sections = [
            "stakes_and_consequences",
            "stakes_tracking",
            "divergences",
            "story_timeline"
        ]

        for section in full_sections:
            if section in content:
                original = content[section]
                fixed = validate_and_fix_bible_entry(section, original)
                if json.dumps(original, sort_keys=True) != json.dumps(fixed, sort_keys=True):
                    if section not in [s.split('.')[0] for s in results["sections_fixed"]]:
                        results["sections_fixed"].append(f"{section} (full)")
                    if not dry_run:
                        content[section] = fixed

        # Check integrity after migration
        results["issues_after"] = validate_bible_integrity(content)

        # Save if not dry run
        if not dry_run and results["sections_fixed"]:
            bible.content = content
            flag_modified(bible, 'content')
            await db.commit()

            # Also sync to disk for debugging
            try:
                with open("src/world_bible.json", 'w') as f:
                    json.dump(content, f, indent=2)
            except Exception:
                pass  # Non-critical

        results["success"] = True

    return results


async def migrate_all_stories(dry_run: bool = False) -> list:
    """Migrate all stories' World Bibles."""
    results = []

    async with AsyncSessionLocal() as db:
        stmt = select(Story)
        result = await db.execute(stmt)
        stories = result.scalars().all()

        for story in stories:
            print(f"Migrating story: {story.id} ({story.title or 'Untitled'})")
            migration_result = await migrate_story_bible(story.id, dry_run)
            results.append(migration_result)
            print(f"  Fixed sections: {migration_result['sections_fixed']}")
            print(f"  Issues before: {len(migration_result['issues_before'])}")
            print(f"  Issues after: {len(migration_result['issues_after'])}")

    return results


def print_results(results: dict):
    """Pretty print migration results."""
    print("\n" + "=" * 60)
    print("MIGRATION RESULTS")
    print("=" * 60)

    print(f"\nStory ID: {results['story_id']}")

    if "error" in results:
        print(f"ERROR: {results['error']}")
        return

    print(f"\nSections fixed ({len(results['sections_fixed'])}):")
    for section in results["sections_fixed"]:
        print(f"  - {section}")

    if results["issues_before"]:
        print(f"\nIssues BEFORE migration ({len(results['issues_before'])}):")
        for issue in results["issues_before"][:10]:  # Show first 10
            print(f"  - {issue}")
        if len(results["issues_before"]) > 10:
            print(f"  ... and {len(results['issues_before']) - 10} more")

    if results["issues_after"]:
        print(f"\nIssues AFTER migration ({len(results['issues_after'])}):")
        for issue in results["issues_after"][:10]:
            print(f"  - {issue}")
        if len(results["issues_after"]) > 10:
            print(f"  ... and {len(results['issues_after']) - 10} more")
    else:
        print("\nNo issues remaining after migration!")

    print(f"\nSuccess: {results['success']}")


async def main():
    parser = argparse.ArgumentParser(
        description="Migrate World Bible schemas to canonical format"
    )
    parser.add_argument(
        "--story-id",
        help="Specific story ID to migrate"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Migrate all stories"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without modifying"
    )

    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN MODE - No changes will be saved\n")

    if args.all:
        results = await migrate_all_stories(args.dry_run)
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        total_fixed = sum(len(r["sections_fixed"]) for r in results)
        total_issues_before = sum(len(r["issues_before"]) for r in results)
        total_issues_after = sum(len(r["issues_after"]) for r in results)
        print(f"Stories processed: {len(results)}")
        print(f"Total sections fixed: {total_fixed}")
        print(f"Total issues before: {total_issues_before}")
        print(f"Total issues after: {total_issues_after}")

    elif args.story_id:
        results = await migrate_story_bible(args.story_id, args.dry_run)
        print_results(results)

    else:
        # Default: use the known story ID from development
        default_id = "d41bbcb6-b9ba-4696-ad25-fc075e6a58dc"
        print(f"No story ID provided, using default: {default_id}")
        results = await migrate_story_bible(default_id, args.dry_run)
        print_results(results)


if __name__ == "__main__":
    asyncio.run(main())
