from __future__ import annotations

from enum import StrEnum


class AccessRole(StrEnum):
    learner = "learner"
    branch_head = "branch_head"
    methodologist = "methodologist"
    admin = "admin"


class Language(StrEnum):
    uz = "uz"
    ru = "ru"


class ModuleType(StrEnum):
    core = "core"
    product = "product"
    faq = "faq"


class ReleaseStatus(StrEnum):
    draft = "draft"
    published = "published"


class LessonVersionStatus(StrEnum):
    draft = "draft"
    published = "published"
    superseded = "superseded"


class VideoStatus(StrEnum):
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class QuestionType(StrEnum):
    single = "single"
    multiple = "multiple"
    ordering = "ordering"
    screenshot = "screenshot"


class QuestionStatus(StrEnum):
    draft = "draft"
    approved = "approved"
    retired = "retired"


class RetiredReason(StrEnum):
    rejected = "rejected"
    manual = "manual"
    lesson_changed = "lesson_changed"


class QuestionOrigin(StrEnum):
    manual = "manual"
    ai = "ai"


class AttemptStatus(StrEnum):
    in_progress = "in_progress"
    submitted = "submitted"
    expired = "expired"


class RemediationResolution(StrEnum):
    watched = "watched"
    superseded = "superseded"


class CertificateKind(StrEnum):
    module = "module"
    operator = "operator"


class JobKind(StrEnum):
    transcode = "transcode"
    ai_draft = "ai_draft"
    operator_cert_eval = "operator_cert_eval"


class JobLane(StrEnum):
    media = "media"
    general = "general"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
