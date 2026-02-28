"""add source_text table

Revision ID: 91aa4ed0dae5
Revises: d3e4f5g6h7i8
Create Date: 2026-03-01 00:34:29.187861

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '91aa4ed0dae5'
down_revision: Union[str, Sequence[str], None] = 'd3e4f5g6h7i8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the source_text table for PDF ingestion storage."""
    # Use if_not_exists for idempotency (table may already exist from manual creation)
    op.create_table(
        'source_text',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('universe', sa.String(), nullable=False),
        sa.Column('volume', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('word_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source_url', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('universe', 'volume', name='uix_source_text_universe_volume'),
    )
    op.create_index(op.f('ix_source_text_universe'), 'source_text', ['universe'], unique=False)


def downgrade() -> None:
    """Drop the source_text table."""
    op.drop_index(op.f('ix_source_text_universe'), table_name='source_text')
    op.drop_table('source_text')
