from __future__ import annotations

from app.ai.base import GenerationError, GenerationInput, GenerationResult


class NoopProvider:
    """No API key configured: the feature is hidden and nothing leaves the network."""

    enabled = False
    model = None

    def generate(self, inp: GenerationInput) -> GenerationResult:
        raise GenerationError("ai.disabled")
