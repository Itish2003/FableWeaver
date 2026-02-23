"""Story branching and family-tree REST endpoints."""

from __future__ import annotations

import copy
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models import Story, History, WorldBible

router = APIRouter()


@router.post("/stories/{story_id}/branch")
async def create_branch(story_id: str, branch_name: str = "New Branch", db: AsyncSession = Depends(get_db)):
    """
    Create a new branch from the current state of a story.
    Copies all history and World Bible to a new story.
    """
    # Get the source story
    result = await db.execute(select(Story).where(Story.id == story_id))
    source_story = result.scalar_one_or_none()
    if not source_story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Get source history
    history_result = await db.execute(
        select(History).where(History.story_id == story_id).order_by(History.sequence)
    )
    source_chapters = history_result.scalars().all()

    # Get source World Bible
    bible_result = await db.execute(select(WorldBible).where(WorldBible.story_id == story_id))
    source_bible = bible_result.scalar_one_or_none()

    # Create new branch story
    branch_id = str(uuid.uuid4())
    branch_story = Story(
        id=branch_id,
        title=f"{source_story.title} [{branch_name}]",
        parent_story_id=story_id,
        branch_name=branch_name,
        branch_point_chapter=len(source_chapters)
    )
    db.add(branch_story)

    # Copy history items
    for ch in source_chapters:
        new_chapter = History(
            id=str(uuid.uuid4()),
            story_id=branch_id,
            sequence=ch.sequence,
            text=ch.text,
            summary=ch.summary,
            choices=ch.choices,
            bible_snapshot=copy.deepcopy(ch.bible_snapshot) if ch.bible_snapshot else None
        )
        db.add(new_chapter)

    # Copy World Bible
    if source_bible:
        new_bible = WorldBible(
            id=str(uuid.uuid4()),
            story_id=branch_id,
            content=copy.deepcopy(source_bible.content) if source_bible.content else {}
        )
        db.add(new_bible)

    await db.commit()

    return {
        "status": "created",
        "branch_id": branch_id,
        "branch_name": branch_name,
        "parent_story_id": story_id,
        "chapters_copied": len(source_chapters)
    }


@router.get("/stories/{story_id}/branches")
async def list_branches(story_id: str, db: AsyncSession = Depends(get_db)):
    """
    List all branches of a story (including the story's own branch info).
    """
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Get all branches (stories with this as parent)
    branches_result = await db.execute(
        select(Story).where(Story.parent_story_id == story_id)
    )
    branches = branches_result.scalars().all()

    # Get chapter count for main story
    history_result = await db.execute(
        select(History).where(History.story_id == story_id)
    )
    main_chapters = len(history_result.scalars().all())

    return {
        "story_id": story_id,
        "title": story.title,
        "is_branch": story.parent_story_id is not None,
        "parent_story_id": story.parent_story_id,
        "branch_name": story.branch_name,
        "chapter_count": main_chapters,
        "branches": [
            {
                "id": b.id,
                "name": b.branch_name,
                "title": b.title,
                "branch_point_chapter": b.branch_point_chapter,
                "created_at": b.created_at.isoformat() if b.created_at else None
            }
            for b in branches
        ]
    }


@router.get("/stories/{story_id}/family-tree")
async def get_story_family_tree(story_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get the full family tree of a story - parent, siblings, and children.
    """
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Find the root story (original, no parent)
    root_id = story_id
    if story.parent_story_id:
        current = story
        while current.parent_story_id:
            parent_result = await db.execute(select(Story).where(Story.id == current.parent_story_id))
            parent = parent_result.scalar_one_or_none()
            if parent:
                current = parent
                root_id = current.id
            else:
                break

    # Get all stories in the family (all descendants of root)
    async def get_descendants(parent_id):
        result = await db.execute(select(Story).where(Story.parent_story_id == parent_id))
        children = result.scalars().all()
        tree = []
        for child in children:
            tree.append({
                "id": child.id,
                "title": child.title,
                "branch_name": child.branch_name,
                "branch_point_chapter": child.branch_point_chapter,
                "children": await get_descendants(child.id)
            })
        return tree

    # Get root story info
    root_result = await db.execute(select(Story).where(Story.id == root_id))
    root = root_result.scalar_one_or_none()

    return {
        "root": {
            "id": root.id,
            "title": root.title,
            "children": await get_descendants(root.id)
        },
        "current_story_id": story_id
    }
