"""Track active practice time and estimate historical sessions from their action log.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "practice_session",
        sa.Column(
            "timing",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    # Old clients never reported page visibility. Keep the original wall duration
    # for reversibility and explicitly mark the reconstructed duration approximate.
    op.execute("""
        WITH events AS (
            SELECT id AS session_id, started_at AS at FROM practice_session
            UNION ALL
            SELECT a.session_id, a.created_at FROM practice_action a
            JOIN practice_session s ON s.id = a.session_id
            WHERE a.created_at >= s.started_at
              AND (s.finished_at IS NULL OR a.created_at <= s.finished_at)
            UNION ALL
            SELECT id, finished_at FROM practice_session WHERE finished_at IS NOT NULL
        ), gaps AS (
            SELECT session_id, EXTRACT(EPOCH FROM at - LAG(at) OVER (
                PARTITION BY session_id ORDER BY at
            )) AS seconds FROM events
        ), elapsed AS (
            SELECT session_id, COALESCE(SUM(LEAST(GREATEST(seconds, 0), 45)), 0) AS seconds
            FROM gaps GROUP BY session_id
        )
        UPDATE practice_session s SET timing = jsonb_build_object(
            'elapsed_s', e.seconds, 'last_at', NULL, 'clients', '{}'::jsonb,
            'presence', true, 'estimated', true,
            'legacy_wall_seconds', (SELECT duration_s FROM practice_result r WHERE r.session_id = s.id)
        ) FROM elapsed e WHERE e.session_id = s.id
    """)
    op.execute("""
        UPDATE practice_result r SET duration_s = FLOOR((s.timing->>'elapsed_s')::numeric)::integer
        FROM practice_session s WHERE r.session_id = s.id
    """)


def downgrade():
    op.execute("""
        UPDATE practice_result r SET duration_s = (s.timing->>'legacy_wall_seconds')::integer
        FROM practice_session s WHERE r.session_id = s.id
          AND s.timing->>'legacy_wall_seconds' IS NOT NULL
    """)
    op.drop_column("practice_session", "timing")
