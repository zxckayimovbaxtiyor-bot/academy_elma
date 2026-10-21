"""The JSON shape the model must return (structured outputs) and its tolerant reader.

The schema only fixes the shape. The rules a question must meet (option counts,
correct answers, timestamps, both languages) are checked on the server afterwards,
so one bad item is dropped instead of failing the whole batch.
"""

from __future__ import annotations

import json
from typing import Any

from app.ai.base import DraftOption, DraftQuestion, GenerationError

_TEXT = {"type": "string"}
_SECONDS = {"anyOf": [{"type": "number"}, {"type": "null"}]}  # null: pasted text has no times

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["single", "multiple", "ordering"]},
                    "difficulty": {"type": "integer", "enum": [1, 2, 3]},
                    "text_uz": _TEXT,
                    "text_ru": _TEXT,
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text_uz": _TEXT,
                                "text_ru": _TEXT,
                                "is_correct": {"type": "boolean"},
                            },
                            "required": ["text_uz", "text_ru", "is_correct"],
                            "additionalProperties": False,
                        },
                    },
                    "explanation_uz": _TEXT,
                    "explanation_ru": _TEXT,
                    "source_start_s": _SECONDS,
                    "source_end_s": _SECONDS,
                    "source_excerpt": _TEXT,
                },
                "required": [
                    "type", "difficulty", "text_uz", "text_ru", "options", "explanation_uz",
                    "explanation_ru", "source_start_s", "source_end_s", "source_excerpt",
                ],  # fmt: skip
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}


def _seconds(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("seconds")
    return float(value)


def _text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("text")
    return value.strip()


def _question(item: Any) -> DraftQuestion:
    if not isinstance(item, dict) or not isinstance(item.get("options"), list):
        raise ValueError("shape")
    difficulty = item.get("difficulty")
    if isinstance(difficulty, bool) or not isinstance(difficulty, int):
        raise ValueError("difficulty")
    options = []
    for o in item["options"]:
        if not isinstance(o, dict) or not isinstance(o.get("is_correct"), bool):
            raise ValueError("option")
        texts = _text(o.get("text_uz")), _text(o.get("text_ru"))
        options.append(DraftOption(*texts, o["is_correct"]))
    return DraftQuestion(
        type=_text(item.get("type")),
        difficulty=difficulty,
        text_uz=_text(item.get("text_uz")),
        text_ru=_text(item.get("text_ru")),
        explanation_uz=_text(item.get("explanation_uz")),
        explanation_ru=_text(item.get("explanation_ru")),
        options=tuple(options),
        source_start_s=_seconds(item.get("source_start_s")),
        source_end_s=_seconds(item.get("source_end_s")),
        source_excerpt=_text(item.get("source_excerpt")),
    )


def parse(text: str) -> tuple[list[DraftQuestion], int]:
    """(questions, malformed count). Raises only when the reply isn't the JSON object at all."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GenerationError("ai.output_invalid") from exc
    if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
        raise GenerationError("ai.output_invalid")
    questions, malformed = [], 0
    for item in data["questions"]:
        try:
            questions.append(_question(item))
        except ValueError:
            malformed += 1
    return questions, malformed
