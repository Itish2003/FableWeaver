from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, DateTime, ForeignKey, Text, JSON, Integer, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func

class Base(DeclarativeBase):
    pass

class Story(Base):
    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(String, primary_key=True, index=True) # Using UUID strings
    title: Mapped[str] = mapped_column(String, index=True, default="Untitled Story")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    active_node_id: Mapped[Optional[int]] = mapped_column(String, nullable=True) # Track current active history node if needed

    # Branching support
    parent_story_id: Mapped[Optional[str]] = mapped_column(ForeignKey("stories.id"), nullable=True)  # If this is a branch, points to parent
    branch_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Name of this branch (e.g., "What if I chose option B?")
    branch_point_chapter: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Chapter number where this branched

    # Per-story chapter length overrides (from setup wizard)
    chapter_min_words_override: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chapter_max_words_override: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    history_items: Mapped[List["History"]] = relationship("History", back_populates="story", cascade="all, delete-orphan", order_by="History.sequence")
    world_bible: Mapped["WorldBible"] = relationship("WorldBible", back_populates="story", uselist=False, cascade="all, delete-orphan")
    branches: Mapped[List["Story"]] = relationship("Story", back_populates="parent_story", remote_side=[id])
    parent_story: Mapped[Optional["Story"]] = relationship("Story", back_populates="branches", remote_side=[parent_story_id])

class History(Base):
    __tablename__ = "history"

    id: Mapped[str] = mapped_column(String, primary_key=True) # Using Frontend timestamp IDs or UUIDs
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"))
    sequence: Mapped[int] = mapped_column(Integer, index=True) # For ordering

    text: Mapped[str] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    choices: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Bible snapshot BEFORE this chapter was generated (for rollback on undo)
    bible_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    story: Mapped["Story"] = relationship("Story", back_populates="history_items")


class BibleSnapshot(Base):
    """Named snapshots of World Bible state for manual save/restore."""
    __tablename__ = "bible_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"))
    name: Mapped[str] = mapped_column(String(128))  # User-provided snapshot name
    content: Mapped[dict] = mapped_column(JSON)  # Full Bible content at snapshot time
    chapter_number: Mapped[int] = mapped_column(Integer)  # Chapter when snapshot was taken
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("story_id", "name", name="uix_bible_snapshot_name"),
    )

class WorldBible(Base):
    __tablename__ = "world_bible"

    id: Mapped[str] = mapped_column(String, primary_key=True) # Usually just one per story, match story_id or separate UUID
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"), unique=True)

    content: Mapped[dict] = mapped_column(JSON, default=dict) # The actual JSON content of the bible
    version_number: Mapped[int] = mapped_column(Integer, default=1) # Optimistic concurrency control: increment on each update
    server_log_mirror: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # Store recent logs or full log dump? keeping it simple for now.

    story: Mapped["Story"] = relationship("Story", back_populates="world_bible")

class SourceText(Base):
    """Stores extracted text from PDFs (light novels, web novels) as a universe-level resource.

    Keyed by (universe, volume) so the same text is reusable across stories.
    """
    __tablename__ = "source_text"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    universe: Mapped[str] = mapped_column(String, index=True)
    volume: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    source_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("universe", "volume", name="uix_source_text_universe_volume"),
    )


# ADK session/event tables are now managed by google.adk.sessions.DatabaseSessionService.

