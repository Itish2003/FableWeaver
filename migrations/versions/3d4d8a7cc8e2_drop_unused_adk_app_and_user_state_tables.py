"""drop unused adk_app_states and adk_user_states tables

Revision ID: 3d4d8a7cc8e2
Revises: e5aa736879cf
Create Date: 2026-02-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d4d8a7cc8e2'
down_revision: Union[str, Sequence[str], None] = 'e5aa736879cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('adk_app_states', if_exists=True)
    op.drop_table('adk_user_states', if_exists=True)


def downgrade() -> None:
    op.create_table(
        'adk_app_states',
        sa.Column('app_name', sa.String(length=128), nullable=False),
        sa.Column('state', sa.JSON(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('app_name'),
    )
    op.create_table(
        'adk_user_states',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('app_name', sa.String(length=128), nullable=False),
        sa.Column('user_id', sa.String(length=128), nullable=False),
        sa.Column('state', sa.JSON(), nullable=False),
        sa.Column('update_time', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('app_name', 'user_id', name='uix_adk_user_state'),
    )
