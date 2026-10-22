"""Practice scenarios, immutable versions and isolated sessions.

Revision ID: 0002
Revises: 0001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def pk():
    return sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True)


def fk(name, target, nullable=False, primary_key=False):
    return sa.Column(
        name,
        sa.BigInteger(),
        sa.ForeignKey(target),
        nullable=nullable,
        primary_key=primary_key,
    )


def created():
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade():
    op.create_table(
        "practice_scenario",
        pk(),
        fk("module_id", "module.id"),
        fk("lesson_id", "lesson.id", True),
        fk("created_by", "app_user.id"),
        created(),
    )
    op.create_index(
        "ix_practice_scenario_module_id", "practice_scenario", ["module_id"]
    )
    op.create_index(
        "ix_practice_scenario_lesson_id", "practice_scenario", ["lesson_id"]
    )
    op.create_table(
        "practice_scenario_version",
        pk(),
        fk("scenario_id", "practice_scenario.id"),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("preview_revision", sa.Integer()),
        sa.Column("definition", JSONB, nullable=False),
        created(),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        fk("published_by", "app_user.id", True),
        sa.UniqueConstraint("scenario_id", "number"),
    )
    op.create_index(
        "ix_practice_scenario_version_scenario_id",
        "practice_scenario_version",
        ["scenario_id"],
    )
    op.create_index(
        "uq_practice_draft",
        "practice_scenario_version",
        ["scenario_id"],
        unique=True,
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_table(
        "practice_assignment",
        fk("scenario_id", "practice_scenario.id", primary_key=True),
        sa.Column("policy", JSONB, nullable=False),
    )
    op.create_table(
        "practice_session",
        pk(),
        fk("user_id", "app_user.id"),
        fk("scenario_id", "practice_scenario.id"),
        fk("version_id", "practice_scenario_version.id"),
        fk("release_id", "elma_release.id", True),
        sa.Column("mode", sa.String(12), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state", JSONB, nullable=False),
        sa.Column("policy", JSONB, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("mode IN ('guided','sandbox','exam')", name="mode"),
        sa.CheckConstraint(
            "status IN ('active','completed','abandoned')", name="status"
        ),
    )
    op.create_index("ix_practice_session_user_id", "practice_session", ["user_id"])
    op.create_index(
        "ix_practice_session_started_at", "practice_session", ["started_at"]
    )
    op.create_index(
        "ix_practice_session_user_scenario",
        "practice_session",
        ["user_id", "scenario_id"],
    )
    op.create_index(
        "uq_practice_session_open",
        "practice_session",
        ["user_id", "scenario_id", "mode"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_table(
        "practice_action",
        pk(),
        fk("session_id", "practice_session.id"),
        sa.Column("request_id", sa.String(80), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("screen_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("errors", JSONB, nullable=False),
        sa.Column("response", JSONB, nullable=False),
        created(),
        sa.UniqueConstraint("session_id", "request_id"),
    )
    op.create_index("ix_practice_action_session_id", "practice_action", ["session_id"])
    op.create_table(
        "practice_result",
        pk(),
        fk("session_id", "practice_session.id"),
        sa.Column("score_pct", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("duration_s", sa.Integer(), nullable=False),
        sa.Column("errors", JSONB, nullable=False),
        created(),
        sa.UniqueConstraint("session_id"),
    )
    op.create_table(
        "practice_asset",
        pk(),
        fk("scenario_id", "practice_scenario.id"),
        sa.Column("data", sa.String(), nullable=False),
        fk("created_by", "app_user.id"),
        created(),
    )
    op.create_index("ix_practice_asset_scenario_id", "practice_asset", ["scenario_id"])
    op.execute(
        """CREATE FUNCTION practice_version_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.published_at IS NOT NULL THEN
            RAISE EXCEPTION 'Published practice versions are immutable';
          END IF;
          RETURN NEW;
        END $$"""
    )
    op.execute(
        """CREATE TRIGGER practice_version_immutable BEFORE UPDATE OR DELETE ON practice_scenario_version
                  FOR EACH ROW EXECUTE FUNCTION practice_version_immutable()"""
    )


def downgrade():
    op.execute("DROP TRIGGER practice_version_immutable ON practice_scenario_version")
    op.execute("DROP FUNCTION practice_version_immutable()")
    for table in (
        "practice_asset",
        "practice_result",
        "practice_action",
        "practice_session",
        "practice_assignment",
        "practice_scenario_version",
        "practice_scenario",
    ):
        op.drop_table(table)
