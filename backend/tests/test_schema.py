"""The migration builds the full planned schema and its integrity rules hold."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.models import (
    AttemptReset,
    Base,
    Certificate,
    Course,
    ElmaRelease,
    Lesson,
    LessonVersion,
    Module,
    Wave,
    WaveBranch,
)
from app.models.enums import CertificateKind, LessonVersionStatus, ModuleType, ReleaseStatus
from tests.factories import make_user


def _fails(db, *objects) -> None:
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add_all(objects)
            db.flush()


def test_migration_creates_every_planned_table(db):
    tables = set(inspect(db.connection()).get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)
    assert len(tables) == 25


def test_certificate_number_sequence_exists(db):
    first = db.scalar(text("SELECT nextval('certificate_number_seq')"))
    assert db.scalar(text("SELECT nextval('certificate_number_seq')")) == first + 1


def test_only_one_core_module(db, reference):
    course = db.scalar(select(Course))
    _fails(
        db,
        Module(course_id=course.id, code="CORE2", qprefix="Z", type=ModuleType.core,
               title_uz="x", title_ru="x"),
    )  # fmt: skip


def test_only_one_draft_release(db):
    db.add(ElmaRelease(code="2026.11", status=ReleaseStatus.draft))
    db.flush()
    _fails(db, ElmaRelease(code="2026.12", status=ReleaseStatus.draft))


def test_lesson_has_at_most_one_published_and_one_draft_version(db, reference):
    module = reference.modules["FAROVON"]
    lesson = Lesson(module_id=module.id, sort=1, title_uz="Dars", title_ru="Урок")
    r1 = ElmaRelease(code="2026.10", status=ReleaseStatus.published)
    r2 = ElmaRelease(code="2026.11", status=ReleaseStatus.published)
    r3 = ElmaRelease(code="2026.12", status=ReleaseStatus.draft)
    db.add_all([lesson, r1, r2, r3])
    db.flush()
    published, draft = LessonVersionStatus.published, LessonVersionStatus.draft
    db.add(LessonVersion(lesson_id=lesson.id, release_id=r1.id, status=published))
    db.flush()
    _fails(db, LessonVersion(lesson_id=lesson.id, release_id=r2.id, status=published))
    db.add(LessonVersion(lesson_id=lesson.id, release_id=r3.id, status=draft))
    db.flush()
    _fails(db, LessonVersion(lesson_id=lesson.id, release_id=r2.id, status=draft))


def test_branch_belongs_to_at_most_one_wave(db, reference):
    waves = [
        Wave(name_uz=f"W{i}", name_ru=f"W{i}", training_start=date(2026, 11, 1),
             deadline=date(2026, 12, 1), go_live=date(2026, 12, 15))
        for i in (1, 2)
    ]  # fmt: skip
    db.add_all(waves)
    db.flush()
    db.add(WaveBranch(wave_id=waves[0].id, branch_id=reference.tashkent.id))
    db.flush()
    _fails(db, WaveBranch(wave_id=waves[1].id, branch_id=reference.tashkent.id))


def test_certificate_module_id_matches_kind(db, reference):
    user = make_user(db)
    _fails(
        db,
        Certificate(number="YO-2026-000001", verify_code="X", kind=CertificateKind.operator,
                    user_id=user.id, module_id=reference.modules["CORE"].id,
                    issued_at=db.scalar(text("SELECT now()")), snapshot={}),
    )  # fmt: skip


def test_attempt_reset_requires_a_reason(db, reference):
    admin = make_user(db)
    learner = make_user(db)
    _fails(
        db,
        AttemptReset(user_id=learner.id, module_id=reference.modules["CORE"].id,
                     reset_by=admin.id, reason="   ", created_at=db.scalar(text("SELECT now()"))),
    )  # fmt: skip
