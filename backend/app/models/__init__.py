"""All tables (docs/PLAN.md §4). Importing this package registers every model on Base.metadata."""

from app.models.assessment import (
    AttemptQuestion,
    AttemptReset,
    Question,
    QuestionOption,
    RemediationItem,
    TestAttempt,
)
from app.models.base import Base
from app.models.certification import Certificate, certificate_number_seq
from app.models.content import Course, ElmaRelease, Lesson, LessonVersion, Module, VideoAsset
from app.models.jobs import Job
from app.models.org import Branch, JobRole, Region
from app.models.progress import LessonProgress
from app.models.users import AppUser, AuditEvent, UserImport, UserSession
from app.models.waves import Wave, WaveBranch, WaveModuleRole

__all__ = [
    "AppUser",
    "AttemptQuestion",
    "AttemptReset",
    "AuditEvent",
    "Base",
    "Branch",
    "Certificate",
    "Course",
    "ElmaRelease",
    "Job",
    "JobRole",
    "Lesson",
    "LessonProgress",
    "LessonVersion",
    "Module",
    "Question",
    "QuestionOption",
    "Region",
    "RemediationItem",
    "TestAttempt",
    "UserImport",
    "UserSession",
    "VideoAsset",
    "Wave",
    "WaveBranch",
    "WaveModuleRole",
    "certificate_number_seq",
]
