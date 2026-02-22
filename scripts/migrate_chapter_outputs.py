#!/usr/bin/env python3
"""
Migration script to apply chapter outputs (1-12) to the world bible.

This script:
1. Extracts chapter metadata from server.log
2. Consolidates stakes_tracking into stakes_and_consequences
3. Consolidates timeline data into story_timeline
4. Updates the world bible in the database

Run with: python scripts/migrate_chapter_outputs.py
"""

import json
import re
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from src.database import AsyncSessionLocal
from src.models import WorldBible

STORY_ID = "d41bbcb6-b9ba-4696-ad25-fc075e6a58dc"
SERVER_LOG_PATH = Path(__file__).parent.parent / "server.log"
BIBLE_DISK_PATH = Path(__file__).parent.parent / "src" / "world_bible.json"


def extract_chapter_outputs(log_path: Path) -> list[dict]:
    """Extract all chapter outputs from server.log"""
    with open(log_path, 'r') as f:
        lines = f.readlines()

    # Find lines with stakes_tracking (chapter outputs)
    chapter_outputs = []

    for line_num, line in enumerate(lines, 1):
        if 'stakes_tracking' not in line:
            continue

        try:
            data = json.loads(line)
            message = data.get('message', '')

            # Find the JSON block in the message
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', message, re.DOTALL)
            if not json_match:
                # Try to find raw JSON with summary and character_voices_used
                json_match = re.search(r'(\{"summary".*?"character_voices_used".*?\].*?\})', message, re.DOTALL)

            if json_match:
                chapter_json = json_match.group(1)
                chapter_data = json.loads(chapter_json)
                chapter_num = len(chapter_outputs) + 1
                chapter_outputs.append({
                    'line': line_num,
                    'chapter': chapter_num,
                    'data': chapter_data
                })
                print(f"  [OK] Chapter {chapter_num}: {chapter_data.get('summary', 'N/A')[:60]}...")
        except Exception as e:
            print(f"  [WARN] Line {line_num}: Parse error - {e}")

    return chapter_outputs


def build_consolidated_data(chapter_outputs: list[dict]) -> dict:
    """Build consolidated world bible updates from chapter outputs"""

    # Initialize structures
    stakes = {
        "costs_paid": [],
        "near_misses": [],
        "pending_consequences": [],
        "power_usage_debt": {}
    }

    story_timeline = {
        "events": [],
        "chapter_dates": []
    }

    divergences = {
        "list": [],
        "butterfly_effects": [],
        "stats": {"total": 0, "major": 0, "minor": 0}
    }

    # Process each chapter
    for ch in chapter_outputs:
        chapter_num = ch['chapter']
        data = ch['data']

        # Extract stakes_tracking
        stakes_data = data.get('stakes_tracking', {})

        # Costs paid
        for cost in stakes_data.get('costs_paid', []):
            if isinstance(cost, str):
                stakes["costs_paid"].append({
                    "chapter": chapter_num,
                    "cost": cost,
                    "severity": "moderate"  # Default
                })
            elif isinstance(cost, dict):
                cost["chapter"] = cost.get("chapter", chapter_num)
                stakes["costs_paid"].append(cost)

        # Near misses
        for near_miss in stakes_data.get('near_misses', []):
            if isinstance(near_miss, str):
                stakes["near_misses"].append({
                    "chapter": chapter_num,
                    "what_almost_happened": near_miss,
                    "saved_by": "Unknown"
                })
            elif isinstance(near_miss, dict):
                near_miss["chapter"] = near_miss.get("chapter", chapter_num)
                stakes["near_misses"].append(near_miss)

        # Power debt - merge (keep highest strain)
        power_debt = stakes_data.get('power_debt_incurred', {})
        for power, strain in power_debt.items():
            if isinstance(strain, str):
                strain_obj = {"uses_this_chapter": 1, "strain_level": strain}
            else:
                strain_obj = strain
            # Keep track of highest strain level seen
            if power not in stakes["power_usage_debt"]:
                stakes["power_usage_debt"][power] = strain_obj

        # Consequences triggered -> pending_consequences
        for consequence in stakes_data.get('consequences_triggered', []):
            if isinstance(consequence, str):
                stakes["pending_consequences"].append({
                    "action": f"Chapter {chapter_num} actions",
                    "predicted_consequence": consequence,
                    "due_by": "Ongoing"
                })

        # Extract timeline data
        timeline_data = data.get('timeline', {})

        chapter_start = timeline_data.get('chapter_start_date', '')
        chapter_end = timeline_data.get('chapter_end_date', '')

        if chapter_end:
            story_timeline["chapter_dates"].append({
                "chapter": chapter_num,
                "date": chapter_end
            })

        # Canon events addressed
        for event in timeline_data.get('canon_events_addressed', []):
            story_timeline["events"].append({
                "chapter": chapter_num,
                "date": chapter_end or chapter_start,
                "event": event,
                "source": "story"
            })

        # Divergences created
        for div in timeline_data.get('divergences_created', []):
            divergence_entry = {
                "id": f"div_{len(divergences['list']) + 1:03d}",
                "chapter": chapter_num,
                "severity": "minor",
                "status": "active",
                "canon_event": "Canon divergence",
                "what_changed": div,
                "cause": f"Player choices in Chapter {chapter_num}",
                "ripple_effects": [],
                "affected_canon_events": []
            }
            divergences["list"].append(divergence_entry)
            divergences["stats"]["total"] += 1
            divergences["stats"]["minor"] += 1

    return {
        "stakes_and_consequences": stakes,
        "story_timeline": story_timeline,
        "divergences": divergences
    }


async def update_world_bible(consolidated_data: dict):
    """Update the world bible in the database"""
    async with AsyncSessionLocal() as session:
        # Use FOR UPDATE to prevent race conditions
        stmt = select(WorldBible).where(
            WorldBible.story_id == STORY_ID
        ).with_for_update()
        result = await session.execute(stmt)
        bible = result.scalar_one_or_none()

        if not bible:
            print("[ERROR] World Bible not found!")
            return False

        # Deep copy existing content
        import copy
        data = copy.deepcopy(bible.content) if bible.content else {}

        # Update stakes_and_consequences
        data["stakes_and_consequences"] = consolidated_data["stakes_and_consequences"]
        print(f"  [OK] stakes_and_consequences: {len(consolidated_data['stakes_and_consequences']['costs_paid'])} costs, {len(consolidated_data['stakes_and_consequences']['near_misses'])} near_misses")

        # Update story_timeline
        data["story_timeline"] = consolidated_data["story_timeline"]
        print(f"  [OK] story_timeline: {len(consolidated_data['story_timeline']['events'])} events")

        # Update divergences
        data["divergences"] = consolidated_data["divergences"]
        print(f"  [OK] divergences: {len(consolidated_data['divergences']['list'])} divergences")

        # Update meta with latest date
        if consolidated_data["story_timeline"]["chapter_dates"]:
            latest_date = consolidated_data["story_timeline"]["chapter_dates"][-1]
            if "meta" not in data:
                data["meta"] = {}
            data["meta"]["current_story_date"] = latest_date.get("date", "")
            print(f"  [OK] meta.current_story_date: {latest_date.get('date', 'N/A')}")

        # Commit to database
        bible.content = data
        flag_modified(bible, "content")
        await session.commit()

        # Sync to disk
        try:
            with open(BIBLE_DISK_PATH, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"  [OK] Synced to disk: {BIBLE_DISK_PATH}")
        except Exception as e:
            print(f"  [WARN] Failed to sync to disk: {e}")

        return True


async def main():
    print("=" * 60)
    print("WORLD BIBLE MIGRATION - Applying Chapter Outputs (1-12)")
    print("=" * 60)
    print()

    # Step 1: Extract chapter outputs
    print("[1/3] Extracting chapter outputs from server.log...")
    chapter_outputs = extract_chapter_outputs(SERVER_LOG_PATH)
    print(f"      Found {len(chapter_outputs)} chapters\n")

    if len(chapter_outputs) != 12:
        print(f"[WARN] Expected 12 chapters, found {len(chapter_outputs)}")

    # Step 2: Build consolidated data
    print("[2/3] Consolidating chapter data...")
    consolidated_data = build_consolidated_data(chapter_outputs)
    print()

    # Step 3: Update world bible
    print("[3/3] Updating world bible in database...")
    success = await update_world_bible(consolidated_data)
    print()

    if success:
        print("=" * 60)
        print("MIGRATION COMPLETE")
        print("=" * 60)
    else:
        print("=" * 60)
        print("MIGRATION FAILED")
        print("=" * 60)
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
