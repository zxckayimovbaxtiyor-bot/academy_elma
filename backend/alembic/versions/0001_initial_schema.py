"""initial schema: all 25 tables from docs/PLAN.md section 4

Revision ID: 0001
Revises: 
Create Date: 2026-10-19 06:03:22.743057
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


ENUM_TYPES = (
    'access_role', 'language', 'module_type', 'release_status', 'lesson_version_status',
    'video_status', 'question_type', 'question_status', 'retired_reason', 'question_origin',
    'attempt_status', 'remediation_resolution', 'certificate_kind', 'job_kind', 'job_lane',
    'job_status',
)


def upgrade() -> None:
    # Running part of certificate numbers (YO-2026-000123); not picked up by autogenerate.
    op.execute(sa.schema.CreateSequence(sa.Sequence('certificate_number_seq')))
    op.create_table('course',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('code', sa.String(length=48), nullable=False),
    sa.Column('title_uz', sa.String(length=200), nullable=False),
    sa.Column('title_ru', sa.String(length=200), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_course')),
    sa.UniqueConstraint('code', name=op.f('uq_course_code'))
    )
    op.create_table('job_role',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('code', sa.String(length=48), nullable=False),
    sa.Column('name_uz', sa.String(length=120), nullable=False),
    sa.Column('name_ru', sa.String(length=120), nullable=False),
    sa.Column('is_branch_head', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('sort', sa.Integer(), server_default='0', nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_job_role')),
    sa.UniqueConstraint('code', name=op.f('uq_job_role_code'))
    )
    op.create_table('region',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('code', sa.String(length=16), nullable=False),
    sa.Column('name_uz', sa.String(length=120), nullable=False),
    sa.Column('name_ru', sa.String(length=120), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_region')),
    sa.UniqueConstraint('code', name=op.f('uq_region_code'))
    )
    op.create_table('wave',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('name_uz', sa.String(length=200), nullable=False),
    sa.Column('name_ru', sa.String(length=200), nullable=False),
    sa.Column('training_start', sa.Date(), nullable=False),
    sa.Column('deadline', sa.Date(), nullable=False),
    sa.Column('go_live', sa.Date(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wave'))
    )
    op.create_table('branch',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('name_uz', sa.String(length=200), nullable=False),
    sa.Column('name_ru', sa.String(length=200), nullable=False),
    sa.Column('region_id', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['region_id'], ['region.id'], name=op.f('fk_branch_region_id_region')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_branch')),
    sa.UniqueConstraint('code', name=op.f('uq_branch_code'))
    )
    op.create_index(op.f('ix_branch_region_id'), 'branch', ['region_id'], unique=False)
    op.create_table('app_user',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('employee_id', sa.String(length=32), nullable=False),
    sa.Column('full_name', sa.String(length=200), nullable=False),
    sa.Column('branch_id', sa.BigInteger(), nullable=True),
    sa.Column('job_role_id', sa.BigInteger(), nullable=True),
    sa.Column('access_role', sa.Enum('learner', 'branch_head', 'methodologist', 'admin', name='access_role'), nullable=False),
    sa.Column('preferred_language', sa.Enum('uz', 'ru', name='language'), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('must_change_password', sa.Boolean(), nullable=False),
    sa.Column('failed_logins', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], name=op.f('fk_app_user_branch_id_branch')),
    sa.ForeignKeyConstraint(['job_role_id'], ['job_role.id'], name=op.f('fk_app_user_job_role_id_job_role')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_app_user')),
    sa.UniqueConstraint('employee_id', name=op.f('uq_app_user_employee_id'))
    )
    op.create_index(op.f('ix_app_user_branch_id'), 'app_user', ['branch_id'], unique=False)
    op.create_index(op.f('ix_app_user_job_role_id'), 'app_user', ['job_role_id'], unique=False)
    op.create_table('wave_branch',
    sa.Column('branch_id', sa.BigInteger(), nullable=False),
    sa.Column('wave_id', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['branch_id'], ['branch.id'], name=op.f('fk_wave_branch_branch_id_branch')),
    sa.ForeignKeyConstraint(['wave_id'], ['wave.id'], name=op.f('fk_wave_branch_wave_id_wave'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('branch_id', name=op.f('pk_wave_branch'))
    )
    op.create_index(op.f('ix_wave_branch_wave_id'), 'wave_branch', ['wave_id'], unique=False)
    op.create_table('audit_event',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('actor_id', sa.BigInteger(), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('target_user_id', sa.BigInteger(), nullable=True),
    sa.Column('entity', sa.String(length=48), nullable=True),
    sa.Column('entity_id', sa.String(length=64), nullable=True),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['app_user.id'], name=op.f('fk_audit_event_actor_id_app_user')),
    sa.ForeignKeyConstraint(['target_user_id'], ['app_user.id'], name=op.f('fk_audit_event_target_user_id_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_event'))
    )
    op.create_index('ix_audit_event_entity', 'audit_event', ['entity', 'entity_id'], unique=False)
    op.create_index('ix_audit_event_target_at', 'audit_event', ['target_user_id', 'at'], unique=False)
    op.create_table('elma_release',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('notes', sa.Text(), server_default='', nullable=False),
    sa.Column('status', sa.Enum('draft', 'published', name='release_status'), nullable=False),
    sa.Column('transition_days', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_by', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('published_by', sa.BigInteger(), nullable=True),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('transition_days BETWEEN 0 AND 365', name=op.f('ck_elma_release_transition_days')),
    sa.ForeignKeyConstraint(['created_by'], ['app_user.id'], name=op.f('fk_elma_release_created_by_app_user')),
    sa.ForeignKeyConstraint(['published_by'], ['app_user.id'], name=op.f('fk_elma_release_published_by_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_elma_release')),
    sa.UniqueConstraint('code', name=op.f('uq_elma_release_code'))
    )
    op.create_index('uq_elma_release_single_draft', 'elma_release', ['status'], unique=True, postgresql_where=sa.text("status = 'draft'"))
    op.create_table('job',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('kind', sa.Enum('transcode', 'ai_draft', 'operator_cert_eval', name='job_kind'), nullable=False),
    sa.Column('lane', sa.Enum('media', 'general', name='job_lane'), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('status', sa.Enum('queued', 'running', 'done', 'failed', name='job_status'), nullable=False),
    sa.Column('attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_by', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['app_user.id'], name=op.f('fk_job_created_by_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_job'))
    )
    op.create_index('ix_job_queue', 'job', ['lane', 'created_at'], unique=False, postgresql_where=sa.text("status = 'queued'"))
    op.create_table('user_import',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('uploaded_by', sa.BigInteger(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('total_rows', sa.Integer(), nullable=False),
    sa.Column('valid_rows', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('committed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_count', sa.Integer(), nullable=True),
    sa.Column('updated_count', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['uploaded_by'], ['app_user.id'], name=op.f('fk_user_import_uploaded_by_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_import'))
    )
    op.create_table('user_session',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], name=op.f('fk_user_session_user_id_app_user'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_session')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_user_session_token_hash'))
    )
    op.create_index(op.f('ix_user_session_user_id'), 'user_session', ['user_id'], unique=False)
    op.create_table('video_asset',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('status', sa.Enum('uploaded', 'processing', 'ready', 'failed', name='video_status'), nullable=False),
    sa.Column('progress_pct', sa.SmallInteger(), server_default='0', nullable=False),
    sa.Column('duration_s', sa.Float(), nullable=True),
    sa.Column('width', sa.Integer(), nullable=True),
    sa.Column('height', sa.Integer(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('synthetic_confirmed_by', sa.BigInteger(), nullable=False),
    sa.Column('synthetic_confirmed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('uploaded_by', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['synthetic_confirmed_by'], ['app_user.id'], name=op.f('fk_video_asset_synthetic_confirmed_by_app_user')),
    sa.ForeignKeyConstraint(['uploaded_by'], ['app_user.id'], name=op.f('fk_video_asset_uploaded_by_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_video_asset'))
    )
    op.create_table('module',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('course_id', sa.BigInteger(), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('qprefix', sa.String(length=8), nullable=False),
    sa.Column('type', sa.Enum('core', 'product', 'faq', name='module_type'), nullable=False),
    sa.Column('title_uz', sa.String(length=200), nullable=False),
    sa.Column('title_ru', sa.String(length=200), nullable=False),
    sa.Column('sort', sa.Integer(), server_default='0', nullable=False),
    sa.Column('current_release_id', sa.BigInteger(), nullable=True),
    sa.Column('test_question_count', sa.Integer(), server_default='15', nullable=False),
    sa.Column('test_pass_pct', sa.Integer(), server_default='80', nullable=False),
    sa.Column('test_time_limit_min', sa.Integer(), server_default='20', nullable=False),
    sa.Column('test_max_attempts', sa.Integer(), server_default='3', nullable=False),
    sa.Column('test_cooldown_hours', sa.Integer(), server_default='24', nullable=False),
    sa.Column('test_published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('test_cooldown_hours BETWEEN 0 AND 720', name=op.f('ck_module_test_cooldown_hours')),
    sa.CheckConstraint('test_max_attempts BETWEEN 1 AND 20', name=op.f('ck_module_test_max_attempts')),
    sa.CheckConstraint('test_pass_pct BETWEEN 1 AND 100', name=op.f('ck_module_test_pass_pct')),
    sa.CheckConstraint('test_question_count BETWEEN 1 AND 100', name=op.f('ck_module_test_question_count')),
    sa.CheckConstraint('test_time_limit_min BETWEEN 1 AND 240', name=op.f('ck_module_test_time_limit_min')),
    sa.ForeignKeyConstraint(['course_id'], ['course.id'], name=op.f('fk_module_course_id_course')),
    sa.ForeignKeyConstraint(['current_release_id'], ['elma_release.id'], name=op.f('fk_module_current_release_id_elma_release')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_module')),
    sa.UniqueConstraint('code', name=op.f('uq_module_code')),
    sa.UniqueConstraint('qprefix', name=op.f('uq_module_qprefix'))
    )
    op.create_index('uq_module_single_core', 'module', ['type'], unique=True, postgresql_where=sa.text("type = 'core'"))
    op.create_table('attempt_reset',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('module_id', sa.BigInteger(), nullable=False),
    sa.Column('reset_by', sa.BigInteger(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('length(btrim(reason)) > 0', name=op.f('ck_attempt_reset_reason_not_blank')),
    sa.ForeignKeyConstraint(['module_id'], ['module.id'], name=op.f('fk_attempt_reset_module_id_module')),
    sa.ForeignKeyConstraint(['reset_by'], ['app_user.id'], name=op.f('fk_attempt_reset_reset_by_app_user')),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], name=op.f('fk_attempt_reset_user_id_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_attempt_reset'))
    )
    op.create_index('ix_attempt_reset_user_module', 'attempt_reset', ['user_id', 'module_id'], unique=False)
    op.create_table('lesson',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('module_id', sa.BigInteger(), nullable=False),
    sa.Column('sort', sa.Integer(), nullable=False),
    sa.Column('title_uz', sa.String(length=300), nullable=False),
    sa.Column('title_ru', sa.String(length=300), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['module_id'], ['module.id'], name=op.f('fk_lesson_module_id_module')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lesson'))
    )
    op.create_index(op.f('ix_lesson_module_id'), 'lesson', ['module_id'], unique=False)
    op.create_table('test_attempt',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('module_id', sa.BigInteger(), nullable=False),
    sa.Column('release_id', sa.BigInteger(), nullable=False),
    sa.Column('status', sa.Enum('in_progress', 'submitted', 'expired', name='attempt_status'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('question_count', sa.Integer(), nullable=False),
    sa.Column('pass_pct', sa.Integer(), nullable=False),
    sa.Column('correct_count', sa.Integer(), nullable=True),
    sa.Column('score_pct', sa.Float(), nullable=True),
    sa.Column('passed', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['module_id'], ['module.id'], name=op.f('fk_test_attempt_module_id_module')),
    sa.ForeignKeyConstraint(['release_id'], ['elma_release.id'], name=op.f('fk_test_attempt_release_id_elma_release')),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], name=op.f('fk_test_attempt_user_id_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_test_attempt'))
    )
    op.create_index('ix_test_attempt_user_module', 'test_attempt', ['user_id', 'module_id'], unique=False)
    op.create_index('uq_test_attempt_open', 'test_attempt', ['user_id', 'module_id'], unique=True, postgresql_where=sa.text("status = 'in_progress'"))
    op.create_table('wave_module_role',
    sa.Column('wave_id', sa.BigInteger(), nullable=False),
    sa.Column('module_id', sa.BigInteger(), nullable=False),
    sa.Column('job_role_id', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['job_role_id'], ['job_role.id'], name=op.f('fk_wave_module_role_job_role_id_job_role')),
    sa.ForeignKeyConstraint(['module_id'], ['module.id'], name=op.f('fk_wave_module_role_module_id_module')),
    sa.ForeignKeyConstraint(['wave_id'], ['wave.id'], name=op.f('fk_wave_module_role_wave_id_wave'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('wave_id', 'module_id', 'job_role_id', name=op.f('pk_wave_module_role'))
    )
    op.create_table('certificate',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('number', sa.String(length=32), nullable=False),
    sa.Column('verify_code', sa.String(length=16), nullable=False),
    sa.Column('kind', sa.Enum('module', 'operator', name='certificate_kind'), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('module_id', sa.BigInteger(), nullable=True),
    sa.Column('release_id', sa.BigInteger(), nullable=True),
    sa.Column('attempt_id', sa.BigInteger(), nullable=True),
    sa.Column('score_pct', sa.Float(), nullable=True),
    sa.Column('issued_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('recert_due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('superseded_by_id', sa.BigInteger(), nullable=True),
    sa.Column('covers', postgresql.ARRAY(sa.BigInteger()), server_default='{}', nullable=False),
    sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('pdf_path', sa.String(length=255), nullable=True),
    sa.CheckConstraint("(kind = 'module') = (module_id IS NOT NULL)", name=op.f('ck_certificate_module_matches_kind')),
    sa.ForeignKeyConstraint(['attempt_id'], ['test_attempt.id'], name=op.f('fk_certificate_attempt_id_test_attempt')),
    sa.ForeignKeyConstraint(['module_id'], ['module.id'], name=op.f('fk_certificate_module_id_module')),
    sa.ForeignKeyConstraint(['release_id'], ['elma_release.id'], name=op.f('fk_certificate_release_id_elma_release')),
    sa.ForeignKeyConstraint(['superseded_by_id'], ['certificate.id'], name=op.f('fk_certificate_superseded_by_id_certificate')),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], name=op.f('fk_certificate_user_id_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_certificate')),
    sa.UniqueConstraint('number', name=op.f('uq_certificate_number'))
    )
    op.create_index('ix_certificate_current', 'certificate', ['user_id', 'module_id'], unique=False, postgresql_where=sa.text('superseded_at IS NULL'))
    op.create_index(op.f('ix_certificate_user_id'), 'certificate', ['user_id'], unique=False)
    op.create_table('lesson_version',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('lesson_id', sa.BigInteger(), nullable=False),
    sa.Column('release_id', sa.BigInteger(), nullable=False),
    sa.Column('status', sa.Enum('draft', 'published', 'superseded', name='lesson_version_status'), nullable=False),
    sa.Column('video_asset_id', sa.Uuid(), nullable=True),
    sa.Column('vtt_uz_path', sa.String(length=255), nullable=True),
    sa.Column('vtt_ru_path', sa.String(length=255), nullable=True),
    sa.Column('pdf_uz_path', sa.String(length=255), nullable=True),
    sa.Column('pdf_ru_path', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['lesson_id'], ['lesson.id'], name=op.f('fk_lesson_version_lesson_id_lesson'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['release_id'], ['elma_release.id'], name=op.f('fk_lesson_version_release_id_elma_release')),
    sa.ForeignKeyConstraint(['video_asset_id'], ['video_asset.id'], name=op.f('fk_lesson_version_video_asset_id_video_asset')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lesson_version')),
    sa.UniqueConstraint('lesson_id', 'release_id', name='uq_lesson_version_lesson_release')
    )
    op.create_index(op.f('ix_lesson_version_lesson_id'), 'lesson_version', ['lesson_id'], unique=False)
    op.create_index(op.f('ix_lesson_version_release_id'), 'lesson_version', ['release_id'], unique=False)
    op.create_index('uq_lesson_version_draft', 'lesson_version', ['lesson_id'], unique=True, postgresql_where=sa.text("status = 'draft'"))
    op.create_index('uq_lesson_version_published', 'lesson_version', ['lesson_id'], unique=True, postgresql_where=sa.text("status = 'published'"))
    op.create_table('lesson_progress',
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('lesson_version_id', sa.BigInteger(), nullable=False),
    sa.Column('watched', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('watched_s', sa.Float(), server_default='0', nullable=False),
    sa.Column('max_position_s', sa.Float(), server_default='0', nullable=False),
    sa.Column('last_position_s', sa.Float(), server_default='0', nullable=False),
    sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['lesson_version_id'], ['lesson_version.id'], name=op.f('fk_lesson_progress_lesson_version_id_lesson_version')),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], name=op.f('fk_lesson_progress_user_id_app_user')),
    sa.PrimaryKeyConstraint('user_id', 'lesson_version_id', name=op.f('pk_lesson_progress'))
    )
    op.create_index(op.f('ix_lesson_progress_lesson_version_id'), 'lesson_progress', ['lesson_version_id'], unique=False)
    op.create_table('question',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('module_id', sa.BigInteger(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('lesson_version_id', sa.BigInteger(), nullable=False),
    sa.Column('video_ts_s', sa.Integer(), nullable=False),
    sa.Column('type', sa.Enum('single', 'multiple', 'ordering', 'screenshot', name='question_type'), nullable=False),
    sa.Column('text_uz', sa.Text(), nullable=False),
    sa.Column('text_ru', sa.Text(), nullable=False),
    sa.Column('explanation_uz', sa.Text(), server_default='', nullable=False),
    sa.Column('explanation_ru', sa.Text(), server_default='', nullable=False),
    sa.Column('difficulty', sa.SmallInteger(), nullable=False),
    sa.Column('status', sa.Enum('draft', 'approved', 'retired', name='question_status'), nullable=False),
    sa.Column('retired_reason', sa.Enum('rejected', 'manual', 'lesson_changed', name='retired_reason'), nullable=True),
    sa.Column('image_path', sa.String(length=255), nullable=True),
    sa.Column('origin', sa.Enum('manual', 'ai', name='question_origin'), nullable=False),
    sa.Column('ai_job_id', sa.BigInteger(), nullable=True),
    sa.Column('ai_source_start_s', sa.Float(), nullable=True),
    sa.Column('ai_source_end_s', sa.Float(), nullable=True),
    sa.Column('ai_source_excerpt', sa.Text(), nullable=True),
    sa.Column('stat_attempts', sa.Integer(), server_default='0', nullable=False),
    sa.Column('stat_correct', sa.Integer(), server_default='0', nullable=False),
    sa.Column('created_by', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('approved_by', sa.BigInteger(), nullable=True),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('retired_by', sa.BigInteger(), nullable=True),
    sa.Column('retired_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('difficulty BETWEEN 1 AND 3', name=op.f('ck_question_difficulty')),
    sa.ForeignKeyConstraint(['ai_job_id'], ['job.id'], name=op.f('fk_question_ai_job_id_job')),
    sa.ForeignKeyConstraint(['approved_by'], ['app_user.id'], name=op.f('fk_question_approved_by_app_user')),
    sa.ForeignKeyConstraint(['created_by'], ['app_user.id'], name=op.f('fk_question_created_by_app_user')),
    sa.ForeignKeyConstraint(['lesson_version_id'], ['lesson_version.id'], name=op.f('fk_question_lesson_version_id_lesson_version')),
    sa.ForeignKeyConstraint(['module_id'], ['module.id'], name=op.f('fk_question_module_id_module')),
    sa.ForeignKeyConstraint(['retired_by'], ['app_user.id'], name=op.f('fk_question_retired_by_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_question')),
    sa.UniqueConstraint('module_id', 'seq', name='uq_question_module_seq')
    )
    op.create_index(op.f('ix_question_lesson_version_id'), 'question', ['lesson_version_id'], unique=False)
    op.create_index('ix_question_module_status', 'question', ['module_id', 'status'], unique=False)
    op.create_table('remediation_item',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('attempt_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('lesson_id', sa.BigInteger(), nullable=False),
    sa.Column('lesson_version_id', sa.BigInteger(), nullable=False),
    sa.Column('span_start_s', sa.Float(), nullable=False),
    sa.Column('span_end_s', sa.Float(), nullable=False),
    sa.Column('missed_count', sa.Integer(), nullable=False),
    sa.Column('watched', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('satisfied_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('satisfied_reason', sa.Enum('watched', 'superseded', name='remediation_resolution'), nullable=True),
    sa.ForeignKeyConstraint(['attempt_id'], ['test_attempt.id'], name=op.f('fk_remediation_item_attempt_id_test_attempt')),
    sa.ForeignKeyConstraint(['lesson_id'], ['lesson.id'], name=op.f('fk_remediation_item_lesson_id_lesson')),
    sa.ForeignKeyConstraint(['lesson_version_id'], ['lesson_version.id'], name=op.f('fk_remediation_item_lesson_version_id_lesson_version')),
    sa.ForeignKeyConstraint(['user_id'], ['app_user.id'], name=op.f('fk_remediation_item_user_id_app_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_remediation_item'))
    )
    op.create_index(op.f('ix_remediation_item_attempt_id'), 'remediation_item', ['attempt_id'], unique=False)
    op.create_index(op.f('ix_remediation_item_user_id'), 'remediation_item', ['user_id'], unique=False)
    op.create_table('attempt_question',
    sa.Column('attempt_id', sa.BigInteger(), nullable=False),
    sa.Column('position', sa.SmallInteger(), nullable=False),
    sa.Column('question_id', sa.BigInteger(), nullable=False),
    sa.Column('option_order', postgresql.ARRAY(sa.BigInteger()), nullable=False),
    sa.Column('answer', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('flagged', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('answered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_correct', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['attempt_id'], ['test_attempt.id'], name=op.f('fk_attempt_question_attempt_id_test_attempt'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['question_id'], ['question.id'], name=op.f('fk_attempt_question_question_id_question')),
    sa.PrimaryKeyConstraint('attempt_id', 'position', name=op.f('pk_attempt_question'))
    )
    op.create_index(op.f('ix_attempt_question_question_id'), 'attempt_question', ['question_id'], unique=False)
    op.create_table('question_option',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=False), nullable=False),
    sa.Column('question_id', sa.BigInteger(), nullable=False),
    sa.Column('sort', sa.Integer(), nullable=False),
    sa.Column('text_uz', sa.Text(), nullable=False),
    sa.Column('text_ru', sa.Text(), nullable=False),
    sa.Column('is_correct', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['question.id'], name=op.f('fk_question_option_question_id_question'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_question_option'))
    )
    op.create_index(op.f('ix_question_option_question_id'), 'question_option', ['question_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_question_option_question_id'), table_name='question_option')
    op.drop_table('question_option')
    op.drop_index(op.f('ix_attempt_question_question_id'), table_name='attempt_question')
    op.drop_table('attempt_question')
    op.drop_index(op.f('ix_remediation_item_user_id'), table_name='remediation_item')
    op.drop_index(op.f('ix_remediation_item_attempt_id'), table_name='remediation_item')
    op.drop_table('remediation_item')
    op.drop_index('ix_question_module_status', table_name='question')
    op.drop_index(op.f('ix_question_lesson_version_id'), table_name='question')
    op.drop_table('question')
    op.drop_index(op.f('ix_lesson_progress_lesson_version_id'), table_name='lesson_progress')
    op.drop_table('lesson_progress')
    op.drop_index('uq_lesson_version_published', table_name='lesson_version', postgresql_where=sa.text("status = 'published'"))
    op.drop_index('uq_lesson_version_draft', table_name='lesson_version', postgresql_where=sa.text("status = 'draft'"))
    op.drop_index(op.f('ix_lesson_version_release_id'), table_name='lesson_version')
    op.drop_index(op.f('ix_lesson_version_lesson_id'), table_name='lesson_version')
    op.drop_table('lesson_version')
    op.drop_index(op.f('ix_certificate_user_id'), table_name='certificate')
    op.drop_index('ix_certificate_current', table_name='certificate', postgresql_where=sa.text('superseded_at IS NULL'))
    op.drop_table('certificate')
    op.drop_table('wave_module_role')
    op.drop_index('uq_test_attempt_open', table_name='test_attempt', postgresql_where=sa.text("status = 'in_progress'"))
    op.drop_index('ix_test_attempt_user_module', table_name='test_attempt')
    op.drop_table('test_attempt')
    op.drop_index(op.f('ix_lesson_module_id'), table_name='lesson')
    op.drop_table('lesson')
    op.drop_index('ix_attempt_reset_user_module', table_name='attempt_reset')
    op.drop_table('attempt_reset')
    op.drop_index('uq_module_single_core', table_name='module', postgresql_where=sa.text("type = 'core'"))
    op.drop_table('module')
    op.drop_table('video_asset')
    op.drop_index(op.f('ix_user_session_user_id'), table_name='user_session')
    op.drop_table('user_session')
    op.drop_table('user_import')
    op.drop_index('ix_job_queue', table_name='job', postgresql_where=sa.text("status = 'queued'"))
    op.drop_table('job')
    op.drop_index('uq_elma_release_single_draft', table_name='elma_release', postgresql_where=sa.text("status = 'draft'"))
    op.drop_table('elma_release')
    op.drop_index('ix_audit_event_target_at', table_name='audit_event')
    op.drop_index('ix_audit_event_entity', table_name='audit_event')
    op.drop_table('audit_event')
    op.drop_index(op.f('ix_wave_branch_wave_id'), table_name='wave_branch')
    op.drop_table('wave_branch')
    op.drop_index(op.f('ix_app_user_job_role_id'), table_name='app_user')
    op.drop_index(op.f('ix_app_user_branch_id'), table_name='app_user')
    op.drop_table('app_user')
    op.drop_index(op.f('ix_branch_region_id'), table_name='branch')
    op.drop_table('branch')
    op.drop_table('wave')
    op.drop_table('region')
    op.drop_table('job_role')
    op.drop_table('course')
    op.execute(sa.schema.DropSequence(sa.Sequence('certificate_number_seq')))
    for name in ENUM_TYPES:
        op.execute(f'DROP TYPE IF EXISTS {name}')
