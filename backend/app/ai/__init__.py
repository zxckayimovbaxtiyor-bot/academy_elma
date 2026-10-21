"""AI question drafting (rule 11): an authoring aid, never called from learner routes.

It is the only outbound call in the system. It runs in the worker, and only when
ANTHROPIC_API_KEY is set; otherwise NoopProvider is used and the feature is hidden.
A methodologist reviews every draft before it can reach a test.
"""

from __future__ import annotations

from app.ai.base import (
    DraftOption,
    DraftQuestion,
    GenerationError,
    GenerationInput,
    GenerationResult,
    QuestionGenerator,
    ReferencePdf,
    TranscriptLine,
)
from app.ai.noop import NoopProvider

__all__ = [
    "DraftOption",
    "DraftQuestion",
    "GenerationError",
    "GenerationInput",
    "GenerationResult",
    "NoopProvider",
    "QuestionGenerator",
    "ReferencePdf",
    "TranscriptLine",
    "get_generator",
]


def get_generator() -> QuestionGenerator:
    from app.config import settings

    if not settings.anthropic_api_key:
        return NoopProvider()
    from app.ai.anthropic_provider import AnthropicProvider

    return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
