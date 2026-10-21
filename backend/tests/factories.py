from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.auth import passwords
from app.models import (
    AppUser,
    AttemptQuestion,
    Branch,
    Certificate,
    ElmaRelease,
    JobRole,
    Lesson,
    LessonProgress,
    LessonVersion,
    Module,
    Question,
    QuestionOption,
    Region,
    VideoAsset,
    Wave,
    WaveBranch,
    WaveModuleRole,
)
from app.models.enums import (
    AccessRole,
    CertificateKind,
    Language,
    LessonVersionStatus,
    QuestionStatus,
    QuestionType,
    ReleaseStatus,
    VideoStatus,
)

PASSWORD = "Parol-2026!"
_ids = itertools.count(1)


@dataclass
class Reference:
    regions: dict[str, Region]
    roles: dict[str, JobRole]
    modules: dict[str, Module]
    tashkent: Branch  # 01-101, region 01
    samarqand: Branch  # 11-101, region 11

    @classmethod
    def load(cls, db: Session) -> Reference:
        regions = {r.code: r for r in db.scalars(select(Region))}
        tashkent = Branch(
            code="01-101", name_uz="Chilonzor BXM", name_ru="ЦБУ Чиланзар",
            region_id=regions["01"].id,
        )  # fmt: skip
        samarqand = Branch(
            code="11-101", name_uz="Samarqand BXM", name_ru="ЦБУ Самарканд",
            region_id=regions["11"].id,
        )  # fmt: skip
        db.add_all([tashkent, samarqand])
        db.flush()
        return cls(
            regions=regions,
            roles={r.code: r for r in db.scalars(select(JobRole))},
            modules={m.code: m for m in db.scalars(select(Module))},
            tashkent=tashkent,
            samarqand=samarqand,
        )


def make_user(
    db: Session,
    *,
    role: AccessRole = AccessRole.learner,
    employee_id: str | None = None,
    password: str = PASSWORD,
    must_change: bool = False,
    branch: Branch | None = None,
    job_role: JobRole | None = None,
    full_name: str = "Test Foydalanuvchi",
    is_active: bool = True,
) -> AppUser:
    user = AppUser(
        employee_id=employee_id or f"T-{next(_ids):06d}",
        full_name=full_name,
        access_role=role,
        preferred_language=Language.uz,
        password_hash=passwords.hash_password(password),
        must_change_password=must_change,
        branch_id=branch.id if branch else None,
        job_role_id=job_role.id if job_role else None,
        is_active=is_active,
    )
    db.add(user)
    db.flush()
    return user


def login(client, user_or_id, password: str = PASSWORD):
    employee_id = user_or_id if isinstance(user_or_id, str) else user_or_id.employee_id
    return client.post("/api/v1/auth/login", json={"username": employee_id, "password": password})


def error_code(response) -> str:
    return response.json()["error"]["code"]


# --- content -----------------------------------------------------------------------


def make_release(db: Session, code: str, status: ReleaseStatus = ReleaseStatus.published):
    release = ElmaRelease(code=code, status=status)
    if status == ReleaseStatus.published:
        release.published_at = clock.utcnow()
    db.add(release)
    db.flush()
    return release


def _staff(db: Session) -> AppUser:
    staff = db.scalar(select(AppUser).where(AppUser.employee_id == "STAFF-0001"))
    return staff or make_user(db, role=AccessRole.methodologist, employee_id="STAFF-0001")


def make_asset(
    db: Session, duration: float | None = 100.0, status=VideoStatus.ready
) -> VideoAsset:
    staff = _staff(db)
    asset = VideoAsset(
        id=uuid.uuid4(),
        original_filename="dars.mp4",
        size_bytes=1,
        status=status,
        duration_s=duration,
        synthetic_confirmed_by=staff.id,
        synthetic_confirmed_at=clock.utcnow(),
        uploaded_by=staff.id,
    )
    db.add(asset)
    db.flush()
    return asset


def make_live_lesson(
    db: Session,
    module: Module,
    *,
    duration: float = 100.0,
    release: ElmaRelease | None = None,
    title: str = "Dars",
    pdf: bool = False,
) -> tuple[Lesson, LessonVersion]:
    """A published lesson with a ready (fake) video; no files on disk."""
    release = release or db.scalar(select(ElmaRelease).where(ElmaRelease.code == "T-LIVE"))
    release = release or make_release(db, "T-LIVE")
    last = db.scalar(select(func.max(Lesson.sort)).where(Lesson.module_id == module.id)) or 0
    lesson = Lesson(module_id=module.id, sort=last + 1, title_uz=title, title_ru=f"{title} (ru)")
    db.add(lesson)
    db.flush()
    asset = make_asset(db, duration)
    version = LessonVersion(
        lesson_id=lesson.id,
        release_id=release.id,
        status=LessonVersionStatus.published,
        video_asset_id=asset.id,
        vtt_uz_path=f"vtt/{lesson.id}-uz.vtt",
        vtt_ru_path=f"vtt/{lesson.id}-ru.vtt",
        pdf_uz_path=f"pdf/{lesson.id}-uz.pdf" if pdf else None,
        pdf_ru_path=f"pdf/{lesson.id}-ru.pdf" if pdf else None,
        published_at=clock.utcnow(),
    )
    db.add(version)
    module.current_release_id = release.id
    db.flush()
    return lesson, version


def make_wave(
    db: Session, branches: list[Branch], assignments: dict[JobRole, list[Module]]
) -> Wave:
    today = clock.utcnow().date()
    wave = Wave(
        name_uz="Sinov toʻlqini", name_ru="Тестовая волна",
        training_start=today, deadline=today, go_live=today,
    )  # fmt: skip
    db.add(wave)
    db.flush()
    for branch in branches:
        db.add(WaveBranch(wave_id=wave.id, branch_id=branch.id))
    for role, modules in assignments.items():
        for module in modules:
            db.add(WaveModuleRole(wave_id=wave.id, module_id=module.id, job_role_id=role.id))
    db.flush()
    return wave


def make_learner(db: Session, ref: Reference, role_code: str = "menejer", branch=None) -> AppUser:
    return make_user(db, branch=branch or ref.tashkent, job_role=ref.roles[role_code])


def give_certificate(
    db: Session, user: AppUser, module: Module, *, recert_due_at=None, superseded: bool = False
) -> Certificate:
    now = clock.utcnow()
    cert = Certificate(
        number=f"YO-TEST-{next(_ids):06d}",
        verify_code="TESTCODE",
        kind=CertificateKind.module,
        user_id=user.id,
        module_id=module.id,
        issued_at=now,
        recert_due_at=recert_due_at,
        superseded_at=now if superseded else None,
        snapshot={
            "holder": {"full_name": user.full_name, "employee_id": user.employee_id},
            "modules": [{"code": module.code, "title_uz": module.title_uz,
                         "title_ru": module.title_ru, "release": None}],
        },  # fmt: skip
    )
    db.add(cert)
    db.flush()
    return cert


# --- questions and attempts ------------------------------------------------------------


def make_question(
    db: Session,
    module: Module,
    version: LessonVersion,
    *,
    q_type: QuestionType = QuestionType.single,
    difficulty: int = 2,
    ts: int = 0,
    status: QuestionStatus = QuestionStatus.approved,
    options: int = 4,
    correct: tuple[int, ...] = (0,),
) -> Question:
    """A complete question (both languages, explanations); options are A, B, C ... in order."""
    last = db.scalar(select(func.max(Question.seq)).where(Question.module_id == module.id))
    seq = (last or 0) + 1
    q = Question(
        module_id=module.id, seq=seq, lesson_version_id=version.id, video_ts_s=ts, type=q_type,
        text_uz=f"Savol {seq}", text_ru=f"Вопрос {seq}", explanation_uz="Izoh",
        explanation_ru="Пояснение", difficulty=difficulty, status=status,
        approved_at=clock.utcnow() if status == QuestionStatus.approved else None,
    )  # fmt: skip
    q.options = [
        QuestionOption(
            sort=i + 1, text_uz=f"Variant {i + 1}", text_ru=f"Вариант {i + 1}",
            is_correct=q_type != QuestionType.ordering and i in correct,
        )  # fmt: skip
        for i in range(options)
    ]
    db.add(q)
    db.flush()
    return q


def make_pool(
    db: Session, module: Module, version: LessonVersion, per_difficulty: int, ts: int = 0
) -> list[Question]:
    return [
        make_question(db, module, version, difficulty=d, ts=ts)
        for d in (1, 2, 3)
        for _ in range(per_difficulty)
    ]


def complete_lesson(db: Session, user: AppUser, version: LessonVersion) -> LessonProgress:
    """Mark a lesson as fully watched (as if the 90 % rule had been met long ago)."""
    duration = version.video_asset.duration_s if version.video_asset else 100.0
    now = clock.utcnow()
    progress = LessonProgress(
        user_id=user.id, lesson_version_id=version.id, watched=[[0.0, duration]],
        watched_s=duration, max_position_s=duration, last_position_s=0.0, started_at=now,
        completed_at=now,
    )  # fmt: skip
    db.add(progress)
    db.flush()
    return progress


def _served(db: Session, attempt_id: int):
    return db.execute(
        select(AttemptQuestion, Question)
        .join(Question, Question.id == AttemptQuestion.question_id)
        .where(AttemptQuestion.attempt_id == attempt_id)
    ).all()


def answer_key(db: Session, attempt_id: int) -> dict[int, list[int]]:
    """position → the right answer as the learner sends it (display indices)."""
    key = {}
    for aq, q in _served(db, attempt_id):
        ids = [o.id for o in q.options if o.is_correct or q.type == QuestionType.ordering]
        key[aq.position] = [aq.option_order.index(oid) for oid in ids]
    return key


def wrong_answer(db: Session, attempt_id: int, position: int) -> list[int]:
    aq, q = next((aq, q) for aq, q in _served(db, attempt_id) if aq.position == position)
    if q.type == QuestionType.ordering:
        return [aq.option_order.index(o.id) for o in reversed(q.options)]
    return [aq.option_order.index(next(o.id for o in q.options if not o.is_correct))]


VTT = "WEBVTT\n\n00:00.000 --> 00:04.000\nKirish\n"


def make_version_ready(db: Session, client, version_id: int, duration: float = 60.0) -> None:
    """Video transcoded + both subtitles uploaded (what the release checklist wants).

    ``client`` must be logged in as admin or methodologist.
    """
    version = db.get(LessonVersion, version_id)
    version.video_asset_id = make_asset(db, duration).id
    db.flush()
    for lang in ("uz", "ru"):
        url = f"/api/v1/admin/lesson-versions/{version_id}/subtitles/{lang}"
        resp = client.put(url, content=VTT)
        assert resp.status_code == 200, resp.text


def ready_module(
    db: Session, module: Module, *, lessons: int = 1, n: int = 3, duration: float = 600.0
) -> list[tuple[Lesson, LessonVersion]]:
    """Live lessons and a published test of N; the 3 x N pool sits on the last lesson."""
    made = [
        make_live_lesson(db, module, duration=duration, title=f"{module.code} {i + 1}")
        for i in range(lessons)
    ]
    module.test_question_count = n
    make_pool(db, module, made[-1][1], per_difficulty=n)
    module.test_published_at = clock.utcnow()
    db.flush()
    return made


def pass_test(db: Session, client, module_id: int, correct: int | None = None) -> dict:
    """Start an attempt, answer ``correct`` questions right (all by default), submit."""
    started = client.post(f"/api/v1/me/modules/{module_id}/attempts")
    assert started.status_code == 201, started.text
    attempt_id = started.json()["attempt_id"]
    key = answer_key(db, attempt_id)
    for i, position in enumerate(sorted(key)):
        answer = key[position] if correct is None or i < correct else (
            wrong_answer(db, attempt_id, position)
        )
        client.put(f"/api/v1/me/attempts/{attempt_id}/answers/{position}", json={"answer": answer})
    result = client.post(f"/api/v1/me/attempts/{attempt_id}/submit")
    assert result.status_code == 200, result.text
    return result.json()


def publish_release(
    db: Session, admin, lessons: list[Lesson], code: str, transition_days: int = 0
) -> dict[int, int]:
    """Release ``code`` replacing the videos of ``lessons``; returns lesson id → new version id."""
    releases_url = "/api/v1/admin/releases"
    release = admin.post(releases_url, json={"code": code})
    assert release.status_code == 201, release.text
    release_id = release.json()["id"]
    admin.patch(f"{releases_url}/{release_id}", json={"transition_days": transition_days})
    new = {}
    for lesson in lessons:
        marked = admin.post(f"{releases_url}/{release_id}/lessons/{lesson.id}")
        assert marked.status_code == 201, marked.text
        new[lesson.id] = marked.json()["draft"]["id"]
        make_version_ready(db, admin, new[lesson.id])
    published = admin.post(f"{releases_url}/{release_id}/publish")
    assert published.status_code == 200, published.text
    db.expire_all()
    return new
