"""World Bible helper functions.

Contains:
- ``compute_bible_diff`` — human-readable diff between Bible snapshots
- ``format_question_answers`` — format player answers for prompt injection
- ``auto_update_bible_from_chapter`` — deterministic Bible updates from chapter metadata
- ``verify_bible_integrity`` — validates and auto-fixes Bible schema issues
"""

from __future__ import annotations

import copy
import json

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from src.database import AsyncSessionLocal
from src.models import WorldBible
from src.utils.legacy_logger import logger


def compute_bible_diff(before: dict, after: dict, chapter_num: int) -> str:
    """
    Compute a human-readable diff between Bible snapshots.
    Shows what the Archivist changed during chapter generation.
    """
    lines = [f"[System] **World Bible Changes (Chapter {chapter_num}):**\n\n"]

    def diff_section(path: str, old_val, new_val, indent=0):
        """Recursively diff sections."""
        prefix = "  " * indent
        changes = []

        if old_val == new_val:
            return []

        if old_val is None and new_val is not None:
            changes.append(f"{prefix}**+ Added {path}**")
            if isinstance(new_val, str) and len(new_val) < 100:
                changes.append(f"{prefix}  → {new_val}")
            elif isinstance(new_val, list) and len(new_val) <= 3:
                changes.append(f"{prefix}  → {new_val}")
        elif old_val is not None and new_val is None:
            changes.append(f"{prefix}**- Removed {path}**")
        elif isinstance(old_val, dict) and isinstance(new_val, dict):
            all_keys = set(old_val.keys()) | set(new_val.keys())
            for key in all_keys:
                sub_path = f"{path}.{key}" if path else key
                sub_changes = diff_section(sub_path, old_val.get(key), new_val.get(key), indent)
                changes.extend(sub_changes)
        elif isinstance(old_val, list) and isinstance(new_val, list):
            if old_val != new_val:
                added = [x for x in new_val if x not in old_val]
                removed = [x for x in old_val if x not in new_val]
                if added:
                    changes.append(f"{prefix}**{path}** added: {added[:3]}{'...' if len(added) > 3 else ''}")
                if removed:
                    changes.append(f"{prefix}**{path}** removed: {removed[:3]}{'...' if len(removed) > 3 else ''}")
        else:
            # Simple value change
            old_str = str(old_val)[:50] if old_val else "(empty)"
            new_str = str(new_val)[:50] if new_val else "(empty)"
            if old_str != new_str:
                changes.append(f"{prefix}**{path}**: {old_str} → {new_str}")

        return changes

    # Key sections to diff
    sections_to_check = [
        'meta',
        'character_sheet',
        'stakes_and_consequences',
        'story_timeline',
        'divergences',
        'character_voices',
        'knowledge_boundaries',
        'power_origins'
    ]

    total_changes = []
    for section in sections_to_check:
        old_section = before.get(section)
        new_section = after.get(section)
        if old_section != new_section:
            changes = diff_section(section, old_section, new_section, indent=0)
            if changes:
                total_changes.extend(changes)

    if not total_changes:
        lines.append("No changes detected in World Bible.\n")
    else:
        lines.extend([f"{c}\n" for c in total_changes[:20]])  # Limit to 20 changes
        if len(total_changes) > 20:
            lines.append(f"... and {len(total_changes) - 20} more changes.\n")

    return "".join(lines)


def format_question_answers(answers: dict) -> str:
    """
    Format user's answers to clarifying questions for inclusion in the prompt.
    The answers dict has question indices as keys and answers as values.
    """
    if not answers:
        return ""

    lines = ["""
═══════════════════════════════════════════════════════════════════════════════
                     PLAYER'S CLARIFYING ANSWERS
═══════════════════════════════════════════════════════════════════════════════
**The player answered optional clarifying questions to help shape this chapter:**
"""]

    for idx, answer in sorted(answers.items(), key=lambda x: int(x[0])):
        lines.append(f"- **Q{int(idx)+1}:** {answer}")

    lines.append("""
**Use these answers to guide the tone, pacing, and direction of the chapter.**
""")

    return "\n".join(lines)


async def auto_update_bible_from_chapter(story_id: str, chapter_text: str, chapter_num: int):
    """
    Automatically apply chapter metadata to World Bible.
    This ensures core updates ALWAYS happen, regardless of Archivist LLM behavior.
    """
    # Extract JSON metadata from chapter text
    from src.utils.json_extractor import extract_chapter_json
    chapter_data = extract_chapter_json(chapter_text)
    if chapter_data is None:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WorldBible).where(WorldBible.story_id == story_id).with_for_update()
        )
        bible = result.scalar_one_or_none()
        if not bible or not bible.content:
            return

        content = copy.deepcopy(bible.content)
        updates_made = []

        # 1. Update stakes_and_consequences
        stakes_tracking = chapter_data.get('stakes_tracking', {})
        if stakes_tracking:
            if 'stakes_and_consequences' not in content:
                content['stakes_and_consequences'] = {}
            stakes = content['stakes_and_consequences']

            # Add costs_paid (schema: {cost, severity, chapter})
            costs = stakes_tracking.get('costs_paid', [])
            if costs:
                if 'costs_paid' not in stakes:
                    stakes['costs_paid'] = []
                for cost in costs:
                    cost_entry = {
                        'cost': cost if isinstance(cost, str) else cost.get('cost', str(cost)),
                        'severity': 'medium',  # Default; Archivist can refine
                        'chapter': chapter_num
                    }
                    stakes['costs_paid'].append(cost_entry)
                updates_made.append(f"costs_paid: +{len(costs)}")

            # Add near_misses (schema: {what_almost_happened, saved_by, chapter})
            near_misses = stakes_tracking.get('near_misses', [])
            if near_misses:
                if 'near_misses' not in stakes:
                    stakes['near_misses'] = []
                for miss in near_misses:
                    miss_entry = {
                        'what_almost_happened': miss if isinstance(miss, str) else miss.get('what_almost_happened', str(miss)),
                        'saved_by': 'Unknown',  # Default; Archivist should refine
                        'chapter': chapter_num
                    }
                    stakes['near_misses'].append(miss_entry)
                updates_made.append(f"near_misses: +{len(near_misses)}")

            # Add consequences_triggered (schema: {action, predicted_consequence, due_by})
            consequences = stakes_tracking.get('consequences_triggered', [])
            if consequences:
                if 'pending_consequences' not in stakes:
                    stakes['pending_consequences'] = []
                for cons in consequences:
                    cons_text = cons if isinstance(cons, str) else str(cons)
                    stakes['pending_consequences'].append({
                        'action': f'Chapter {chapter_num} events',
                        'predicted_consequence': cons_text,
                        'due_by': f'Chapter {chapter_num + 2}'  # Default: 2 chapters ahead
                    })
                updates_made.append(f"consequences: +{len(consequences)}")

        # 2. Update timeline
        timeline_data = chapter_data.get('timeline', {})
        if timeline_data:
            # Update current story date
            end_date = timeline_data.get('chapter_end_date')
            if end_date:
                if 'meta' not in content:
                    content['meta'] = {}
                content['meta']['current_story_date'] = end_date
                updates_made.append(f"story_date: {end_date}")

            # Add to story_timeline
            if 'story_timeline' not in content:
                content['story_timeline'] = {'events': [], 'chapter_dates': []}

            # Compute chapter date string (used for both chapter_dates and events)
            start_date = timeline_data.get('chapter_start_date')
            date_str = None
            if start_date or end_date:
                # Combine start/end into single date string
                if start_date == end_date or not end_date:
                    date_str = start_date
                elif not start_date:
                    date_str = end_date
                else:
                    date_str = f"{start_date} - {end_date}"

                # Add chapter date entry (schema: {chapter, date})
                content['story_timeline']['chapter_dates'].append({
                    'chapter': chapter_num,
                    'date': date_str
                })

            # Add canon events addressed (include date from chapter timeline)
            canon_events = timeline_data.get('canon_events_addressed', [])
            if canon_events:
                for event in canon_events:
                    content['story_timeline']['events'].append({
                        'chapter': chapter_num,
                        'event': event if isinstance(event, str) else str(event),
                        'type': 'canon_addressed',
                        'date': date_str or content.get('meta', {}).get('current_story_date', 'Unknown')
                    })
                updates_made.append(f"canon_events: +{len(canon_events)}")

                # Update canon_timeline.current_position with latest date + recent events
                if 'canon_timeline' not in content:
                    content['canon_timeline'] = {}
                current_date = content.get('meta', {}).get('current_story_date', date_str or 'Unknown')
                recent_canon = ', '.join(canon_events[-2:]) if len(canon_events) <= 2 else ', '.join(canon_events[-2:])
                content['canon_timeline']['current_position'] = f"{current_date} - {recent_canon}"

            # Add divergences (schema: {id, chapter, what_changed, severity, status, canon_event, cause, ripple_effects, affected_canon_events})
            divergences = timeline_data.get('divergences_created', [])
            if divergences:
                if 'divergences' not in content:
                    content['divergences'] = {'list': [], 'stats': {'total': 0, 'major': 0, 'minor': 0}}
                if 'list' not in content['divergences']:
                    content['divergences']['list'] = []
                existing_count = len(content['divergences']['list'])
                for i, div in enumerate(divergences):
                    div_text = div if isinstance(div, str) else str(div)
                    # Skip placeholder divergences
                    if div_text.lower() in ('none', 'none significant', 'none significant this chapter', 'none this chapter'):
                        continue
                    content['divergences']['list'].append({
                        'id': f'div_{existing_count + i + 1:03d}',
                        'chapter': chapter_num,
                        'what_changed': div_text,
                        'severity': 'minor',  # Default; Archivist can refine
                        'status': 'active',
                        'canon_event': '',  # Archivist should fill
                        'cause': 'OC intervention',
                        'ripple_effects': [],
                        'affected_canon_events': []
                    })
                # Update stats
                div_list = content['divergences']['list']
                major_count = sum(1 for d in div_list if d.get('severity') in ('major', 'critical'))
                content['divergences']['stats'] = {
                    'total': len(div_list),
                    'major': major_count,
                    'minor': len(div_list) - major_count
                }
                updates_made.append(f"divergences: +{len(divergences)}")

        # 3. Track power usage
        power_debt = stakes_tracking.get('power_debt_incurred', {}) if stakes_tracking else {}
        if power_debt:
            if 'power_origins' not in content:
                content['power_origins'] = {}
            if 'usage_tracking' not in content['power_origins']:
                content['power_origins']['usage_tracking'] = {}
            for power, level in power_debt.items():
                content['power_origins']['usage_tracking'][power] = {
                    'last_chapter': chapter_num,
                    'strain_level': level if isinstance(level, str) else str(level)
                }
            updates_made.append(f"power_debt: {list(power_debt.keys())}")

        # Save updates
        if updates_made:
            bible.content = content
            flag_modified(bible, 'content')
            await db.commit()
            logger.log("auto_bible_update", f"Chapter {chapter_num} auto-updates: {', '.join(updates_made)}")

            # Sync to disk for debugging
            try:
                with open("src/world_bible.json", 'w') as f:
                    json.dump(content, f, indent=2)
            except Exception:
                pass


async def verify_bible_integrity(story_id: str) -> list[str]:
    """
    Verify Bible data integrity after chapter generation.
    Returns list of issues found. If issues found, auto-fixes them.
    """
    from src.utils.bible_validator import validate_bible_integrity, validate_and_fix_bible_entry

    issues = []

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WorldBible).where(WorldBible.story_id == story_id).with_for_update()
        )
        bible = result.scalar_one_or_none()
        if not bible or not bible.content:
            return ["World Bible not found"]

        content = copy.deepcopy(bible.content)

        # Run integrity check
        issues = validate_bible_integrity(content)

        if issues:
            # Auto-fix by running validator on problematic sections
            sections_to_fix = set()
            for issue in issues:
                if "pending_consequences" in issue:
                    sections_to_fix.add("stakes_and_consequences.pending_consequences")
                elif "near_misses" in issue:
                    sections_to_fix.add("stakes_and_consequences.near_misses")
                elif "costs_paid" in issue:
                    sections_to_fix.add("stakes_and_consequences.costs_paid")
                elif "divergences" in issue:
                    sections_to_fix.add("divergences.list")
                elif "chapter_dates" in issue:
                    sections_to_fix.add("story_timeline.chapter_dates")

            # Apply fixes
            for section in sections_to_fix:
                parts = section.split('.')
                if len(parts) == 2:
                    parent, child = parts
                    if parent in content and child in content[parent]:
                        content[parent][child] = validate_and_fix_bible_entry(
                            section, content[parent][child]
                        )

            bible.content = content
            flag_modified(bible, 'content')
            await db.commit()
            logger.log("bible_integrity_fix", f"Auto-fixed {len(issues)} Bible integrity issues")

    return issues
