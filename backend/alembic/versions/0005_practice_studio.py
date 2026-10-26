"""Archive practice lessons and type protected studio media."""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "practice_scenario",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "practice_asset",
        sa.Column(
            "content_type", sa.String(40), nullable=False, server_default="image/png"
        ),
    )

    from sqlalchemy.dialects.postgresql import JSONB

    op.add_column(
        "practice_action",
        sa.Column(
            "details", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.create_table(
        "practice_upload",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "session_id",
            sa.BigInteger(),
            sa.ForeignKey("practice_session.id"),
            nullable=False,
        ),
        sa.Column("component_id", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("content_type", sa.String(40), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_practice_upload_session_id", "practice_upload", ["session_id"])


def downgrade():
    op.drop_table("practice_upload")
    op.drop_column("practice_action", "details")
    op.drop_column("practice_asset", "content_type")
    op.drop_column("practice_scenario", "archived_at")
