"""Claude drafts the questions, through the official Anthropic SDK.

* The SDK is imported only here, and only once a key is configured.
* Structured outputs fix the reply's JSON shape; the server still validates each item.
* Reference PDFs go in as document blocks, so no PDF-parsing library is needed.
* Streaming keeps long replies clear of HTTP timeouts.
* A policy decline is retried server-side on Anthropic's recommended fallback model
  (``fallbacks="default"``); if the whole chain declines, the job reports it.
"""

from __future__ import annotations

import base64
from typing import Any

from app.ai import prompt, schema
from app.ai.base import GenerationError, GenerationInput, GenerationResult

MAX_TOKENS = 64000  # room for the thinking as well as up to 30 bilingual questions
EFFORT = "medium"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    enabled = True

    def __init__(self, api_key: str, model: str, client: Any = None) -> None:
        self.model = model
        self._api_key = api_key
        self._client = client  # tests pass a stand-in

    def _get_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def request(self, inp: GenerationInput) -> dict[str, Any]:
        content: list[dict[str, Any]] = [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.b64encode(pdf.data).decode("ascii"),
                },
                "title": pdf.title,
            }
            for pdf in inp.reference_pdfs
        ]
        content.append({"type": "text", "text": prompt.user_text(inp)})
        return {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": prompt.SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": content}],
            "output_config": {
                "effort": EFFORT,
                "format": {"type": "json_schema", "schema": schema.OUTPUT_SCHEMA},
            },
            "betas": [FALLBACK_BETA],
            "fallbacks": "default",
        }

    def generate(self, inp: GenerationInput) -> GenerationResult:
        import anthropic

        client = self._get_client()
        try:
            with client.beta.messages.stream(**self.request(inp)) as stream:
                message = stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise GenerationError("ai.auth_failed") from exc
        except anthropic.PermissionDeniedError as exc:
            raise GenerationError("ai.permission_denied") from exc
        except anthropic.RateLimitError as exc:
            raise GenerationError("ai.rate_limited") from exc
        except anthropic.BadRequestError as exc:
            raise GenerationError("ai.request_rejected", {"message": exc.message[:300]}) from exc
        except anthropic.APIStatusError as exc:
            raise GenerationError("ai.api_error", {"status": exc.status_code}) from exc
        except anthropic.APIConnectionError as exc:  # also timeouts; egress may be blocked
            raise GenerationError("ai.unreachable") from exc

        if message.stop_reason == "refusal":  # every model in the chain declined
            details = message.stop_details
            raise GenerationError("ai.refused", {"category": details.category if details else None})
        if message.stop_reason == "max_tokens":
            raise GenerationError("ai.truncated")
        # After a mid-answer fallback the reply continues in a later text block.
        text = "".join(block.text for block in message.content if block.type == "text")
        questions, malformed = schema.parse(text)
        iterations = getattr(message.usage, "iterations", None) or []
        return GenerationResult(
            questions=questions,
            malformed=malformed,
            model=message.model,
            fell_back=any(getattr(i, "type", None) == "fallback_message" for i in iterations),
        )
