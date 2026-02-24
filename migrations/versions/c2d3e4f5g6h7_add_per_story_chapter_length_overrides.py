"""add per-story chapter length overrides for setup wizard

Adds chapter_min_words_override and chapter_max_words_override columns to stories
table to support per-story chapter length preferences configured during conversational
setup wizard.

Revision ID: c2d3e4f5g6h7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5g6h7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('stories', sa.Column('chapter_min_words_override', sa.Integer(), nullable=True))
    op.add_column('stories', sa.Column('chapter_max_words_override', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('stories', 'chapter_max_words_override')
    op.drop_column('stories', 'chapter_min_words_override')
