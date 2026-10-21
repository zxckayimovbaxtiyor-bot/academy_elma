"""Learner side of content: assigned modules, lessons, the player and heartbeats."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, selectinload

from app import clock
from app.auth.deps import current_user
from app.db import get_db
from app.errors import AppError, not_found
from app.models import (
    AppUser,
    Branch,
    ElmaRelease,
    JobRole,
    Lesson,
    LessonProgress,
    LessonVersion,
    Module,
    VideoAsset,
)
from app.models.enums import LessonVersionStatus, ModuleType
from app.schemas.common import Ref
from app.schemas.learner import (
    DashboardCert,
    DashboardOut,
    DashboardWave,
    FragmentOut,
    HeartbeatIn,
    HeartbeatOut,
    LearnerLesson,
    LearnerModule,
    LearnerModuleDetail,
    PlayerOut,
    ProgressOut,
    ReasonOut,
    ResumeOut,
    TestInfo,
    TestStatus,
)
from app.services import (
    access,
    attempts,
    certificates,
    content,
    media,
    progress,
    remediation,
    reports,
)
from app.services.certificates import CertStatus

router = APIRouter(prefix="/me", tags=["learner"])


def _pct(watched_s: float, duration: float) -> int:
    return min(100, int(watched_s / duration * 100)) if duration > 0 else 0


def _release_code(db: Session, release_id: int | None) -> str | None:
    if release_id is None:
        return None
    return db.scalar(select(ElmaRelease.code).where(ElmaRelease.id == release_id))


def _lesson_rows(db: Session, user: AppUser, module_ids: list[int]):
    """(module_id, lesson, duration, progress or None) for every live lesson, in order."""
    return db.execute(
        select(Lesson, VideoAsset.duration_s, LessonProgress)
        .join(
            LessonVersion,
            and_(
                LessonVersion.lesson_id == Lesson.id,
                LessonVersion.status == LessonVersionStatus.published,
            ),
        )
        .join(VideoAsset, VideoAsset.id == LessonVersion.video_asset_id)
        .outerjoin(
            LessonProgress,
            and_(
                LessonProgress.lesson_version_id == LessonVersion.id,
                LessonProgress.user_id == user.id,
            ),
        )
        .where(Lesson.module_id.in_(module_ids))
        .order_by(Lesson.sort, Lesson.id)
    ).all()


@dataclass
class _Standing:
    """What the learner has achieved, loaded once per request."""

    certs: dict
    active: set
    core_certified: bool
    now: datetime

    @classmethod
    def load(cls, db: Session, user: AppUser) -> _Standing:
        return cls(
            certs=certificates.current_module_certs(db, [user.id]),
            active=reports.activity(db, [user.id]),
            core_certified=access.holds_core_certificate(db, user.id),
            now=clock.utcnow(),
        )


def _module_out(db: Session, user: AppUser, module: Module, rows: list, st: _Standing):
    cert = st.certs.get((user.id, module.id))
    state = reports.module_state(
        certificates.module_status(cert, st.now), (user.id, module.id) in st.active
    )
    return LearnerModule(
        id=module.id,
        code=module.code,
        type=module.type,
        title_uz=module.title_uz,
        title_ru=module.title_ru,
        sort=module.sort,
        locked=access.is_locked(module, st.core_certified),
        release_code=_release_code(db, module.current_release_id),
        lessons_total=len(rows),
        lessons_completed=sum(1 for _, _, p in rows if p is not None and p.completed_at),
        duration_s=round(sum(d or 0 for _, d, _ in rows), 1),
        status=state,
        score_pct=cert.score_pct if cert else None,
        recert_due_at=cert.recert_due_at if cert else None,
    )


def _lesson_items(rows: list) -> list[LearnerLesson]:
    return [
        LearnerLesson(
            id=lesson.id,
            sort=lesson.sort,
            title_uz=lesson.title_uz,
            title_ru=lesson.title_ru,
            duration_s=duration or 0.0,
            completed=bool(p and p.completed_at),
            watched_pct=_pct(p.watched_s, duration or 0) if p else 0,
        )
        for lesson, duration, p in rows
    ]


def _path(db: Session, user: AppUser, st: _Standing) -> list[LearnerModule]:
    modules = access.assigned_modules(db, user)
    rows_by_module: dict[int, list] = {m.id: [] for m in modules}
    for lesson, duration, p in _lesson_rows(db, user, list(rows_by_module)):
        rows_by_module[lesson.module_id].append((lesson, duration, p))
    return [
        _module_out(db, user, m, rows_by_module[m.id], st)
        for m in modules
        if rows_by_module[m.id]  # modules without live lessons stay hidden
    ]


@router.get("/modules", response_model=list[LearnerModule])
def my_modules(user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    return _path(db, user, _Standing.load(db, user))


@router.get("/modules/{module_id}", response_model=LearnerModuleDetail)
def my_module(module_id: int, user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    module = db.get(Module, module_id)
    assigned = {m.id for m in access.assigned_modules(db, user)}
    if module is None or (module.type != ModuleType.faq and module.id not in assigned):
        raise not_found("module")
    rows = [tuple(r) for r in _lesson_rows(db, user, [module.id])]
    if not rows:
        raise not_found("module")
    # First: grading an abandoned attempt may issue a certificate and change the rest.
    status = _test_status(db, user, module) if module.type != ModuleType.faq else None
    base = _module_out(db, user, module, rows, _Standing.load(db, user))
    test = None
    if status is not None:
        test = TestInfo(
            question_count=module.test_question_count,
            pass_pct=module.test_pass_pct,
            time_limit_min=module.test_time_limit_min,
            max_attempts=module.test_max_attempts,
            published=module.test_published_at is not None,
            lessons_complete=base.lessons_completed == base.lessons_total,
            status=status,
        )
    return LearnerModuleDetail(**base.model_dump(), lessons=_lesson_items(rows), test=test)


def _test_status(db: Session, user: AppUser, module: Module) -> TestStatus:
    now = clock.utcnow()
    if attempts.expire_overdue_for(db, user.id, module.id, now):
        db.commit()  # an abandoned attempt is graded before anything is decided
    elig = attempts.eligibility(db, user, module, now)
    last = elig.last_attempt
    return TestStatus(
        can_start=elig.can_start,
        reasons=[ReasonOut(code=r.code, params=r.params) for r in elig.reasons],
        attempts_used=elig.attempts_used,
        attempts_max=elig.attempts_max,
        cooldown_until=elig.cooldown_until,
        open_attempt_id=elig.open_attempt_id,
        last_attempt_id=last.id if last else None,
        last_score_pct=last.score_pct if last else None,
        last_passed=last.passed if last else None,
    )


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    """Home page: wave banner, x/y certified, learning path, resume card, certificates."""
    st = _Standing.load(db, user)
    wave = access.user_wave(db, user)
    path = _path(db, user, st)
    assigned = access.assigned_modules(db, user)
    certified = sum(
        1
        for m in assigned
        if certificates.module_status(st.certs.get((user.id, m.id)), st.now) == CertStatus.valid
    )
    operator = certificates.current_operator_certs(db, [user.id], st.now).get(user.id)
    titles = {m.id: m for m in assigned}
    current = sorted(
        (c for (_, mid), c in st.certs.items() if mid in titles),
        key=lambda c: (titles[c.module_id].sort, c.module_id),
    )
    branch = db.get(Branch, user.branch_id) if user.branch_id else None
    role = db.get(JobRole, user.job_role_id) if user.job_role_id else None
    return DashboardOut(
        full_name=user.full_name,
        branch=Ref.model_validate(branch) if branch else None,
        job_role=Ref.model_validate(role) if role else None,
        wave=DashboardWave(
            id=wave.id, name_uz=wave.name_uz, name_ru=wave.name_ru,
            training_start=wave.training_start, deadline=wave.deadline, go_live=wave.go_live,
            days_left=(wave.deadline - clock.today()).days,
        ) if wave else None,  # fmt: skip
        modules_certified=certified,
        modules_assigned=len(assigned),
        overdue=wave is not None
        and certified < len(assigned)
        and st.now >= clock.end_of_day(wave.deadline),
        path=path,
        resume=_resume(db, user, path),
        operator_status=operator[1] if operator else CertStatus.missing,
        certificates=[
            DashboardCert(
                number=c.number, kind=c.kind, module_id=c.module_id,
                title_uz=titles[c.module_id].title_uz, title_ru=titles[c.module_id].title_ru,
                status=certificates.module_status(c, st.now), recert_due_at=c.recert_due_at,
            )  # fmt: skip
            for c in current
        ],
    )


def _resume(db: Session, user: AppUser, path: list[LearnerModule]) -> ResumeOut | None:
    """The lesson watched most recently and not finished; else the first unfinished one."""
    open_modules = [m for m in path if not m.locked]
    rows = db.execute(
        select(Lesson, LessonVersion, LessonProgress)
        .join(
            LessonVersion,
            and_(
                LessonVersion.lesson_id == Lesson.id,
                LessonVersion.status == LessonVersionStatus.published,
            ),
        )
        .outerjoin(
            LessonProgress,
            and_(
                LessonProgress.lesson_version_id == LessonVersion.id,
                LessonProgress.user_id == user.id,
            ),
        )
        .options(selectinload(LessonVersion.video_asset))
        .where(Lesson.module_id.in_([m.id for m in open_modules] or [0]))
    ).all()
    unfinished = [(lsn, v, p) for lsn, v, p in rows if p is None or p.completed_at is None]
    if not unfinished:
        return None
    order = {m.id: i for i, m in enumerate(open_modules)}
    started = [r for r in unfinished if r[2] is not None and r[2].last_heartbeat_at]
    if started:
        lesson, version, progress = max(started, key=lambda r: r[2].last_heartbeat_at)
    else:
        lesson, version, progress = min(
            unfinished, key=lambda r: (order[r[0].module_id], r[0].sort, r[0].id)
        )
    module = next(m for m in open_modules if m.id == lesson.module_id)
    duration = content.duration_of(version) or 0.0
    siblings = [lsn.id for lsn, _ in content.published_lessons(db, module.id)]
    return ResumeOut(
        lesson_id=lesson.id, module_id=module.id, module_title_uz=module.title_uz,
        module_title_ru=module.title_ru, lesson_number=siblings.index(lesson.id) + 1,
        title_uz=lesson.title_uz, title_ru=lesson.title_ru, duration_s=duration,
        watched_pct=_pct(progress.watched_s, duration) if progress else 0,
    )  # fmt: skip


@router.get("/faq", response_model=list[LearnerLesson])
def faq(user: AppUser = Depends(current_user), db: Session = Depends(get_db)):
    faq_ids = list(db.scalars(select(Module.id).where(Module.type == ModuleType.faq)))
    return _lesson_items([tuple(r) for r in _lesson_rows(db, user, faq_ids)])


@router.get("/faq/{lesson_id}", response_model=PlayerOut)
def faq_lesson(
    lesson_id: int, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
):
    """FAQ player payload: untracked, free seeking (same shape as a lesson)."""
    lesson = db.get(Lesson, lesson_id)
    module = db.get(Module, lesson.module_id) if lesson else None
    if module is None or module.type != ModuleType.faq:
        raise not_found("lesson")
    return open_lesson(lesson_id, user, db)


def _open_lesson(db: Session, user: AppUser, lesson_id: int):
    """Lesson, module, live version and whether watching is tracked; enforces access."""
    lesson = db.get(Lesson, lesson_id)
    version = content.published_version(db, lesson_id) if lesson else None
    if lesson is None or version is None:
        raise not_found("lesson")
    module = db.get(Module, lesson.module_id)
    if module.type == ModuleType.faq:
        return lesson, module, version, False
    if module.id not in {m.id for m in access.assigned_modules(db, user)}:
        raise not_found("lesson")
    if access.is_locked(module, access.holds_core_certificate(db, user.id)):
        raise AppError(403, "module.locked")
    return lesson, module, version, True


def _progress_out(p: LessonProgress | None, duration: float) -> ProgressOut:
    if p is None:
        return ProgressOut(
            watched_s=0, watched_pct=0, max_position_s=0, last_position_s=0, completed=False
        )
    return ProgressOut(
        watched_s=p.watched_s,
        watched_pct=_pct(p.watched_s, duration),
        max_position_s=p.max_position_s,
        last_position_s=p.last_position_s,
        completed=p.completed_at is not None,
    )


@router.get("/lessons/{lesson_id}", response_model=PlayerOut)
def open_lesson(
    lesson_id: int, user: AppUser = Depends(current_user), db: Session = Depends(get_db)
):
    lesson, module, version, tracking = _open_lesson(db, user, lesson_id)
    duration = content.duration_of(version) or 0.0
    record = (
        db.scalar(
            select(LessonProgress).where(
                LessonProgress.user_id == user.id, LessonProgress.lesson_version_id == version.id
            )
        )
        if tracking
        else None
    )
    prog = _progress_out(record, duration) if tracking else None
    completed = bool(prog and prog.completed)
    fragments = []
    failed = attempts.open_remediation_attempt(db, user.id, module.id) if tracking else None
    if failed is not None:
        fragments = [
            FragmentOut(
                span_start_s=i.span_start_s,
                span_end_s=i.span_end_s,
                watched_pct=int(remediation.watched_ratio(i) * 100),
                satisfied=i.satisfied_at is not None,
            )
            for i in remediation.items_for(db, failed.id)
            if i.lesson_version_id == version.id
        ]
    siblings = [lsn.id for lsn, _ in content.published_lessons(db, module.id)]
    index = siblings.index(lesson.id)
    pdf = (
        {"uz": media.url(version.pdf_uz_path), "ru": media.url(version.pdf_ru_path)}
        if version.pdf_uz_path and version.pdf_ru_path
        else None
    )
    return PlayerOut(
        lesson_id=lesson.id,
        module_id=module.id,
        module_type=module.type,
        title_uz=lesson.title_uz,
        title_ru=lesson.title_ru,
        version_id=version.id,
        release_code=_release_code(db, version.release_id) or "",
        duration_s=duration,
        hls_url=media.hls_url(version.video_asset_id),
        subtitles={"uz": media.url(version.vtt_uz_path), "ru": media.url(version.vtt_ru_path)},
        pdf=pdf,
        tracking=tracking,
        progress=prog,
        seek_limit_s=None if (not tracking or completed) else prog.max_position_s,
        speed_change_allowed=not tracking or completed,
        prev_lesson_id=siblings[index - 1] if index > 0 else None,
        next_lesson_id=siblings[index + 1] if index + 1 < len(siblings) else None,
        remediation=fragments,
    )


@router.post("/lessons/{lesson_id}/heartbeat", response_model=HeartbeatOut)
def heartbeat(
    lesson_id: int,
    body: HeartbeatIn,
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    _, _, version, tracking = _open_lesson(db, user, lesson_id)
    if not tracking:
        raise AppError(400, "lesson.not_tracked")
    if body.version_id != version.id:  # a release replaced the video meanwhile
        raise AppError(409, "lesson.version_changed", {"current_version_id": version.id})
    duration = content.duration_of(version) or 0.0
    record, accepted = progress.record_heartbeat(
        db,
        user_id=user.id,
        lesson_version_id=version.id,
        duration=duration,
        ranges=body.ranges,
        position_s=body.position_s,
    )
    remediation.apply_heartbeat(db, user.id, version.id, accepted)
    db.commit()
    return HeartbeatOut(**_progress_out(record, duration).model_dump(), duration_s=duration)

