"""AI drafts (rule 11): build the request, call the generator in the worker, keep what is valid.

Every item the model returns is checked on the server before it becomes a draft:
an allowed type, a difficulty of 1-3, the option count, exactly one correct answer
for single choice (two or more, and one wrong, for multiple choice), a source span
inside the video, and both languages throughout. Invalid items are dropped and
counted by reason. Saved drafts carry origin=ai, the job id and the source span and
excerpt, and go through the same review as any other question.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai import (
    DraftQuestion,
    GenerationError,
    GenerationInput,
    QuestionGenerator,
    ReferencePdf,
    TranscriptLine,
)
from app.ai.base import TYPES
from app.errors import AppError
from app.models import Job, Lesson, LessonVersion, Module, Question
from app.models.enums import (
    JobKind,
    JobLane,
    JobStatus,
    LessonVersionStatus,
    ModuleType,
    QuestionOrigin,
    QuestionType,
)
from app.services import audit, content, media, questions, vtt
from app.worker import runner

MAX_COUNT = 30
# The API takes 32 MB per request and base64 adds a third: keep the PDFs well under it.
MAX_REFERENCE_PDF_BYTES = 20 * 1024 * 1024
TIMESTAMP_SLACK_S = 1.0
MAX_TEXT, MAX_OPTION, MAX_EXCERPT = 2000, 1000, 1000


def _version(db: Session, version_id: int) -> LessonVersion:
    version = db.scalar(
        select(LessonVersion)
        .options(selectinload(LessonVersion.video_asset), selectinload(LessonVersion.lesson))
        .where(LessonVersion.id == version_id)
    )
    if version is None:
        raise AppError(404, "lesson_version.not_found")
    return version


def _pdf_paths(version: LessonVersion) -> list[str]:
    return [p for p in (version.pdf_uz_path, version.pdf_ru_path) if p]


def enqueue(
    db: Session, version_id: int, request: dict[str, Any], generator: QuestionGenerator,
    actor_id: int,
) -> Job:  # fmt: skip
    """Check everything that can be checked now, then hand the call to the worker."""
    if not generator.enabled:
        raise AppError(409, "ai.disabled")
    version = _version(db, version_id)
    if version.status == LessonVersionStatus.superseded:
        raise AppError(409, "lesson_version.superseded")
    module = db.get(Module, version.lesson.module_id)
    if module.type == ModuleType.faq:
        raise AppError(400, "module.no_test")
    if request["source"] == "transcript" and not (version.vtt_uz_path or version.vtt_ru_path):
        raise AppError(400, "ai.transcript_missing")
    if request["source"] == "text" and not (request.get("text") or "").strip():
        raise AppError(400, "ai.text_missing")
    if request.get("include_lesson_pdf"):
        paths = _pdf_paths(version)
        if not paths:
            raise AppError(400, "ai.pdf_missing")
        size = sum(media.abs_path(p).stat().st_size for p in paths)
        if size > MAX_REFERENCE_PDF_BYTES:
            raise AppError(400, "ai.reference_too_large", {"max_mb": MAX_REFERENCE_PDF_BYTES >> 20})
    busy = db.scalar(
        select(Job.id).where(
            Job.kind == JobKind.ai_draft,
            Job.status.in_([JobStatus.queued, JobStatus.running]),
            Job.payload["lesson_version_id"].as_integer() == version.id,
        )
    )
    if busy is not None:
        raise AppError(409, "ai.job_in_progress", {"job_id": busy})
    job = runner.enqueue(
        db, JobKind.ai_draft, JobLane.general,
        {"lesson_version_id": version.id, "actor_id": actor_id, "request": request}, actor_id,
    )  # fmt: skip
    audit.record(
        db, "ai.drafts_requested", actor_id=actor_id, entity="lesson_version",
        entity_id=version.id, data={"job_id": job.id, "count": request["count"]},
    )  # fmt: skip
    return job


def _transcript(version: LessonVersion, lang: str) -> tuple[TranscriptLine, ...]:
    path = getattr(version, f"vtt_{lang}_path")
    if not path:
        return ()
    cues = vtt.parse(media.abs_path(path).read_text(encoding="utf-8-sig"))
    return tuple(TranscriptLine(c.start, c.end, c.text) for c in cues)


def build_input(db: Session, version: LessonVersion, request: dict[str, Any]) -> GenerationInput:
    lesson: Lesson = version.lesson
    module = db.get(Module, lesson.module_id)
    from_transcript = request["source"] == "transcript"
    pdfs: tuple[ReferencePdf, ...] = ()
    if request.get("include_lesson_pdf"):
        pdfs = tuple(
            ReferencePdf(f"{lesson.title_uz} ({lang})", media.abs_path(path).read_bytes())
            for lang, path in (("uz", version.pdf_uz_path), ("ru", version.pdf_ru_path))
            if path
        )
    return GenerationInput(
        module_title=f"{module.title_uz} / {module.title_ru}",
        lesson_title_uz=lesson.title_uz,
        lesson_title_ru=lesson.title_ru,
        duration_s=content.duration_of(version),
        count=request["count"],
        types=tuple(t for t in TYPES if t in request["types"]),
        transcript_uz=_transcript(version, "uz") if from_transcript else (),
        transcript_ru=_transcript(version, "ru") if from_transcript else (),
        source_text=None if from_transcript else request["text"],
        reference_text=request.get("reference_text") or None,
        reference_pdfs=pdfs,
    )


def _options(item: DraftQuestion) -> list[questions.OptionData]:
    """An ordering question's answer is the order itself: no option is marked correct."""
    ordering = item.type == QuestionType.ordering
    return [
        questions.OptionData(o.text_uz, o.text_ru, o.is_correct and not ordering)
        for o in item.options
    ]


def problems(
    item: DraftQuestion, allowed: set[str], duration: float | None, timestamped: bool
) -> list[str]:
    """Why an item can't become a draft (empty: it can)."""
    out: list[str] = []
    if item.type not in allowed:
        return ["type_not_allowed"]
    if item.difficulty not in (1, 2, 3):
        out.append("difficulty_invalid")
    if not (item.text_uz and item.text_ru):
        out.append("text_missing")
    if not (item.explanation_uz and item.explanation_ru):
        out.append("explanation_missing")
    if not all(o.text_uz and o.text_ru for o in item.options):
        out.append("option_text_missing")
    texts = (item.text_uz, item.text_ru, item.explanation_uz, item.explanation_ru)
    option_texts = [t for o in item.options for t in (o.text_uz, o.text_ru)]
    if any(len(t) > MAX_TEXT for t in texts) or any(len(t) > MAX_OPTION for t in option_texts):
        out.append("too_long")
    out += questions.structure_problems(QuestionType(item.type), _options(item))
    start, end = item.source_start_s, item.source_end_s
    if start is None or end is None:
        if timestamped:
            out.append("timestamp_missing")
    elif start < 0 or end < start or (duration is not None and end > duration + TIMESTAMP_SLACK_S):
        out.append("timestamp_outside_video")
    return out


def run(db: Session, job: Job, generator: QuestionGenerator) -> dict[str, Any]:
    """Worker side: call the model, validate every item, save the valid ones as drafts."""
    payload = job.payload
    request = payload["request"]
    version = _version(db, payload["lesson_version_id"])
    if version.status == LessonVersionStatus.superseded:
        raise runner.JobError("lesson_version.superseded")
    try:
        result = generator.generate(build_input(db, version, request))
    except GenerationError as exc:
        raise runner.JobError(exc.code, exc.params) from exc

    module = db.get(Module, version.lesson.module_id)
    duration = content.duration_of(version)
    timestamped = request["source"] == "transcript"
    allowed = set(request["types"])
    seen = {
        t.casefold()
        for t in db.scalars(select(Question.text_uz).where(Question.module_id == module.id))
    }
    dropped: Counter[str] = Counter()
    created: list[int] = []
    for item in result.questions:
        found = problems(item, allowed, duration, timestamped)
        if not found and item.text_uz.casefold() in seen:
            found = ["duplicate"]
        if not found and len(created) >= request["count"]:
            found = ["over_count"]
        if found:
            dropped.update(found[:1])  # counted once, by its first problem
            continue
        seen.add(item.text_uz.casefold())
        start = item.source_start_s
        ts = int(start) if start is not None else 0  # where remediation sends the learner
        if duration:
            ts = min(ts, int(duration))
        q = questions.create_draft(
            db, module=module, lesson=version.lesson, q_type=QuestionType(item.type),
            text_uz=item.text_uz, text_ru=item.text_ru, explanation_uz=item.explanation_uz,
            explanation_ru=item.explanation_ru, difficulty=item.difficulty, video_ts_s=ts,
            options=_options(item), actor_id=payload["actor_id"], origin=QuestionOrigin.ai,
            version=version,
            extra={
                "ai_job_id": job.id, "ai_source_start_s": start,
                "ai_source_end_s": item.source_end_s,
                "ai_source_excerpt": item.source_excerpt[:MAX_EXCERPT] or None,
            },
        )  # fmt: skip
        created.append(q.id)
    if result.malformed:
        dropped["malformed"] = result.malformed
    summary = {
        "created": len(created),
        "dropped": sum(dropped.values()),
        "problems": dict(sorted(dropped.items())),
        "question_ids": created,
        "model": result.model,
        "fell_back": result.fell_back,
    }
    logged = {k: summary[k] for k in ("created", "dropped", "problems", "model")}
    audit.record(
        db, "ai.drafts_created", actor_id=payload["actor_id"], entity="lesson_version",
        entity_id=version.id, data={"job_id": job.id, **logged},
    )  # fmt: skip
    return summary
