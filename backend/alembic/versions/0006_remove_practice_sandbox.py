"""Retire the free-practice mode, preserving original data in an archive."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "practice_retired_archive",
        sa.Column("source_table", sa.String(40), primary_key=True),
        sa.Column("source_id", sa.BigInteger(), primary_key=True),
        sa.Column("original", JSONB(), nullable=False),
    )
    # Preserve complete original rows, including workspace records and cached
    # responses, before changing the supported mode. No employee results are deleted.
    for table, condition in (
        ("practice_session", "mode = 'sandbox'"),
        (
            "practice_scenario_version",
            "definition #>> '{metadata,default_mode}' = 'sandbox'",
        ),
        ("practice_action", "response ->> 'mode' = 'sandbox'"),
    ):
        op.execute(
            sa.text(
                f"INSERT INTO practice_retired_archive (source_table, source_id, original) "
                f"SELECT '{table}', id, to_jsonb(source) FROM {table} source WHERE {condition}"
            )
        )
    # Retired active sessions must not collide with an existing guided attempt.
    op.execute("""
        UPDATE practice_session
        SET mode = 'guided',
            status = CASE WHEN status = 'active' THEN 'abandoned' ELSE status END,
            finished_at = CASE WHEN status = 'active' THEN now() ELSE finished_at END,
            state = state - 'records' - 'record_id' - 'next_record'
        WHERE mode = 'sandbox'
    """)
    # This one-time compatibility change includes published default-mode metadata;
    # its complete original definition is archived. Restore the normal protection
    # immediately within the same transactional migration.
    op.execute(
        "ALTER TABLE practice_scenario_version DISABLE TRIGGER practice_version_immutable"
    )
    op.execute("""
        UPDATE practice_scenario_version
        SET definition = jsonb_set(definition, '{metadata,default_mode}', '"guided"'),
            preview_revision = NULL
        WHERE definition #>> '{metadata,default_mode}' = 'sandbox'
    """)
    op.execute(
        "ALTER TABLE practice_scenario_version ENABLE TRIGGER practice_version_immutable"
    )
    op.execute("""
        UPDATE practice_action
        SET response = jsonb_set(response - 'records' - 'record_id', '{mode}', '"guided"')
        WHERE response ->> 'mode' = 'sandbox'
    """)
    op.drop_constraint(
        op.f("ck_practice_session_mode"), "practice_session", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_practice_session_mode"),
        "practice_session",
        "mode IN ('guided','exam')",
    )


def downgrade():
    op.drop_constraint(
        op.f("ck_practice_session_mode"), "practice_session", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_practice_session_mode"),
        "practice_session",
        "mode IN ('guided','sandbox','exam')",
    )
    # Restore only fields changed by this migration; preserve later author edits.
    op.execute("""
        UPDATE practice_session s
        SET mode = a.original ->> 'mode',
            status = a.original ->> 'status',
            finished_at = (a.original ->> 'finished_at')::timestamptz,
            state = a.original -> 'state'
        FROM practice_retired_archive a
        WHERE a.source_table = 'practice_session' AND a.source_id = s.id
    """)
    op.execute(
        "ALTER TABLE practice_scenario_version DISABLE TRIGGER practice_version_immutable"
    )
    op.execute("""
        UPDATE practice_scenario_version v
        SET definition = jsonb_set(v.definition, '{metadata,default_mode}',
                                  a.original #> '{definition,metadata,default_mode}')
        FROM practice_retired_archive a
        WHERE a.source_table = 'practice_scenario_version' AND a.source_id = v.id
    """)
    op.execute(
        "ALTER TABLE practice_scenario_version ENABLE TRIGGER practice_version_immutable"
    )
    op.execute("""
        UPDATE practice_action r SET response = a.original -> 'response'
        FROM practice_retired_archive a
        WHERE a.source_table = 'practice_action' AND a.source_id = r.id
    """)
    op.drop_table("practice_retired_archive")
