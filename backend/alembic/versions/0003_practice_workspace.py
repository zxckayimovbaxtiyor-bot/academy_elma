"""Allow descriptive workspace command names in the practice audit log.

Revision ID: 0003
Revises: 0002
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "practice_action",
        "kind",
        existing_type=sa.String(12),
        type_=sa.String(32),
        existing_nullable=False,
    )


def downgrade():
    # Refuse destructive truncation if longer operation names have already been used.
    op.alter_column(
        "practice_action",
        "kind",
        existing_type=sa.String(32),
        type_=sa.String(12),
        existing_nullable=False,
    )
