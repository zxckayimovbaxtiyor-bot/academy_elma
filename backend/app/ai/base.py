"""What a generator receives and returns. Providers know nothing about the database."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

TYPES = ("single", "multiple", "ordering")  # screenshot questions are written by hand


@dataclass(frozen=True)
class TranscriptLine:
    start_s: float
    end_s: float
    text: str


@dataclass(frozen=True)
class ReferencePdf:
    title: str
    data: bytes


@dataclass(frozen=True)
class GenerationInput:
    module_title: str
    lesson_title_uz: str
    lesson_title_ru: str
    duration_s: float | None
    count: int
    types: tuple[str, ...] = TYPES
    transcript_uz: tuple[TranscriptLine, ...] = ()
    transcript_ru: tuple[TranscriptLine, ...] = ()
    source_text: str | None = None  # pasted by the methodologist instead of the transcript
    reference_text: str | None = None
    reference_pdfs: tuple[ReferencePdf, ...] = ()


@dataclass(frozen=True)
class DraftOption:
    text_uz: str
    text_ru: str
    is_correct: bool


@dataclass(frozen=True)
class DraftQuestion:
    """One item as the model wrote it. Not yet checked: the server validates it."""

    type: str
    difficulty: int
    text_uz: str
    text_ru: str
    explanation_uz: str
    explanation_ru: str
    options: tuple[DraftOption, ...]
    source_start_s: float | None
    source_end_s: float | None
    source_excerpt: str


@dataclass(frozen=True)
class GenerationResult:
    questions: list[DraftQuestion]
    malformed: int = 0  # items without the expected shape
    model: str = ""
    fell_back: bool = False  # a fallback model answered after a policy decline
    extra: dict[str, Any] = field(default_factory=dict)


class GenerationError(Exception):
    """A stable code (shown translated in the admin UI) plus parameters."""

    def __init__(self, code: str, params: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.params = params or {}


class QuestionGenerator(Protocol):
    enabled: bool
    model: str | None

    def generate(self, inp: GenerationInput) -> GenerationResult: ...
