"""Add version_number field for optimistic concurrency control."""
from alembic import op
import sqlalchemy as sa

revision = "d3e4f5g6h7i8"
down_revision = "c2d3e4f5g6h7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "world_bible",
        sa.Column(
            "version_number",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="Optimistic concurrency control: increment on each update",
        ),
    )


def downgrade() -> None:
    op.drop_column("world_bible", "version_number")
