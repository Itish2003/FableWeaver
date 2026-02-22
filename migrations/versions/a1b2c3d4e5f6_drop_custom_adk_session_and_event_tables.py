"""drop custom adk_sessions and adk_events tables

ADK's DatabaseSessionService auto-creates its own tables (sessions, events,
app_states, user_states) on first instantiation.  The hand-rolled tables are
no longer needed.

Revision ID: a1b2c3d4e5f6
Revises: 3d4d8a7cc8e2
Create Date: 2026-02-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '3d4d8a7cc8e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("adk_events")
    op.drop_table("adk_sessions")


def downgrade() -> None:
    op.create_table(
        "adk_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("app_name", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("adk_session_id", sa.String(length=128), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("update_time", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_name", "user_id", "adk_session_id", name="uix_adk_session"),
    )
    op.create_index(op.f("ix_adk_sessions_id"), "adk_sessions", ["id"], unique=False)

    op.create_table(
        "adk_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("adk_event_id", sa.String(length=128), nullable=False),
        sa.Column("app_name", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("adk_session_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("invocation_id", sa.String(length=256), nullable=False),
        sa.Column("author", sa.String(length=256), nullable=False),
        sa.Column("actions", sa.LargeBinary(), nullable=False),
        sa.Column("long_running_tool_ids_json", sa.Text(), nullable=True),
        sa.Column("branch", sa.String(length=256), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("content", sa.JSON(), nullable=True),
        sa.Column("grounding_metadata", sa.JSON(), nullable=True),
        sa.Column("custom_metadata", sa.JSON(), nullable=True),
        sa.Column("partial", sa.Boolean(), nullable=True),
        sa.Column("turn_complete", sa.Boolean(), nullable=True),
        sa.Column("error_code", sa.String(length=256), nullable=True),
        sa.Column("error_message", sa.String(length=1024), nullable=True),
        sa.Column("interrupted", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["adk_sessions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("adk_event_id", "app_name", "user_id", "adk_session_id", name="uix_adk_event"),
    )
    op.create_index(op.f("ix_adk_events_id"), "adk_events", ["id"], unique=False)
