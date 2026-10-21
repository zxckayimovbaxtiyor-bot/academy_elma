from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AttemptStatus, CertificateKind, ModuleType, QuestionType
from app.schemas.common import Ref
from app.services.certificates import CertStatus
from app.services.reports import ModuleState

Seconds = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class LearnerLesson(BaseModel):
    id: int
    sort: int
    title_uz: str
    title_ru: str
    duration_s: float
    completed: bool
    watched_pct: int


class LearnerModule(BaseModel):
    id: int
    code: str
    type: ModuleType
    title_uz: str
    title_ru: str
    sort: int
    locked: bool  # product module before the Core certificate
    release_code: str | None
    lessons_total: int
    lessons_completed: int
    duration_s: float
    status: ModuleState  # certified · recert_required · in_progress · not_started
    score_pct: float | None  # of the current certificate
    recert_due_at: datetime | None  # "recertify by" once a release changed the module


class TestInfo(BaseModel):
    question_count: int
    pass_pct: int
    time_limit_min: int
    max_attempts: int
    published: bool
    lessons_complete: bool
    status: TestStatus


class LearnerModuleDetail(LearnerModule):
    lessons: list[LearnerLesson]
    test: TestInfo | None  # None for FAQ


class ProgressOut(BaseModel):
    watched_s: float
    watched_pct: int
    max_position_s: float
    last_position_s: float
    completed: bool


class FragmentOut(BaseModel):
    span_start_s: float
    span_end_s: float
    watched_pct: int
    satisfied: bool


class PlayerOut(BaseModel):
    lesson_id: int
    module_id: int
    module_type: ModuleType
    title_uz: str
    title_ru: str
    version_id: int
    release_code: str
    duration_s: float
    hls_url: str
    subtitles: dict[str, str]  # {"uz": url, "ru": url}
    pdf: dict[str, str] | None  # shown only when it exists in both languages
    tracking: bool  # False for FAQ: no heartbeats, free seeking
    progress: ProgressOut | None
    seek_limit_s: float | None  # first viewing: no seeking past this point
    speed_change_allowed: bool
    prev_lesson_id: int | None
    next_lesson_id: int | None
    remediation: list[FragmentOut]  # fragments to re-watch after a failed test


class HeartbeatIn(BaseModel):
    """What the player actually played since the last heartbeat. No completion flag exists."""

    model_config = ConfigDict(extra="forbid")

    version_id: int
    ranges: list[tuple[Seconds, Seconds]] = Field(default_factory=list, max_length=50)
    position_s: Seconds = 0.0


class HeartbeatOut(ProgressOut):
    duration_s: float


# --- tests and attempts ---------------------------------------------------------------------


class ReasonOut(BaseModel):
    code: str
    params: dict[str, Any]


class TestStatus(BaseModel):
    can_start: bool
    reasons: list[ReasonOut]  # every reason it can't start now
    attempts_used: int
    attempts_max: int
    cooldown_until: datetime | None
    open_attempt_id: int | None
    last_attempt_id: int | None
    last_score_pct: float | None
    last_passed: bool | None


class AttemptStarted(BaseModel):
    attempt_id: int
    created: bool  # False: an attempt already in progress was resumed


class AttemptOption(BaseModel):
    # Position in this attempt's display order. Option ids are never sent: they follow the
    # authored order, which is the answer of an ordering question.
    index: int
    text_uz: str
    text_ru: str


class AttemptQuestionOut(BaseModel):
    position: int
    type: QuestionType
    text_uz: str
    text_ru: str
    image_url: str | None
    options: list[AttemptOption]  # display order; no answer key
    answer: list[int] | None  # display indices
    flagged: bool


class AttemptOut(BaseModel):
    id: int
    module_id: int
    module_title_uz: str
    module_title_ru: str
    status: AttemptStatus
    number: int
    max_attempts: int
    question_count: int
    pass_pct: int
    started_at: datetime
    expires_at: datetime
    server_now: datetime  # the browser derives its countdown from this, not its own clock
    answered: int
    questions: list[AttemptQuestionOut]  # empty once the attempt is finished


class AnswerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Display indices of the chosen options (ordering: all of them, in the chosen order).
    # Omit to keep the saved answer; null or [] clears it.
    answer: list[Annotated[int, Field(ge=0)]] | None = Field(None, max_length=8)
    flagged: bool | None = None


class AnswerOut(BaseModel):
    position: int
    answered: bool
    flagged: bool


class RemediationOut(BaseModel):
    lesson_id: int
    lesson_title_uz: str
    lesson_title_ru: str
    missed_count: int
    span_start_s: float
    span_end_s: float
    watched_pct: int
    satisfied: bool


class HistoryRow(BaseModel):
    attempt_id: int
    number: int
    status: AttemptStatus
    started_at: datetime
    score_pct: float | None
    passed: bool | None
    time_spent_s: int | None


class ResultOut(BaseModel):
    """What a learner sees after a test: never the correct answers or explanations."""

    attempt_id: int
    module_id: int
    status: AttemptStatus
    number: int
    score_pct: float
    correct_count: int
    question_count: int
    pass_pct: int
    passed: bool
    time_spent_s: int | None
    attempts_used: int
    attempts_max: int
    attempts_left: int
    next_attempt_at: datetime | None
    remediation: list[RemediationOut]
    remediation_complete: bool
    history: list[HistoryRow]


# --- home page (mockup 1) ------------------------------------------------------------------


class DashboardWave(BaseModel):
    id: int
    name_uz: str
    name_ru: str
    training_start: date
    deadline: date
    go_live: date
    days_left: int  # until the end of the deadline day; negative once overdue


class ResumeOut(BaseModel):
    lesson_id: int
    module_id: int
    module_title_uz: str
    module_title_ru: str
    lesson_number: int
    title_uz: str
    title_ru: str
    duration_s: float
    watched_pct: int


class DashboardCert(BaseModel):
    number: str
    kind: CertificateKind
    module_id: int | None
    title_uz: str | None  # module certificates; the operator one has no module
    title_ru: str | None
    status: CertStatus
    recert_due_at: datetime | None


class DashboardOut(BaseModel):
    full_name: str
    branch: Ref | None
    job_role: Ref | None
    wave: DashboardWave | None  # None: the branch is in no wave yet (FAQ only)
    modules_certified: int
    modules_assigned: int
    overdue: bool
    path: list[LearnerModule]
    resume: ResumeOut | None
    operator_status: CertStatus
    certificates: list[DashboardCert]  # current ones
