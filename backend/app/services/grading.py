"""Scoring. Each question is all-or-nothing; the pass mark is inclusive (12/15 at 80 % passes)."""

from __future__ import annotations

from collections.abc import Sequence

from app.models.enums import QuestionType


def is_correct(
    q_type: QuestionType,
    authored_ids: Sequence[int],
    correct_ids: set[int],
    answer: Sequence[int] | None,
) -> bool:
    if not answer:
        return False  # unanswered counts as wrong
    if q_type in (QuestionType.single, QuestionType.screenshot):
        return len(answer) == 1 and answer[0] in correct_ids
    if q_type == QuestionType.multiple:
        return len(set(answer)) == len(answer) and set(answer) == correct_ids
    return list(answer) == list(authored_ids)  # ordering: the authored order


def score_pct(correct: int, total: int) -> float:
    return round(correct / total * 100, 2) if total else 0.0


def passed(correct: int, total: int, pass_pct: int) -> bool:
    return total > 0 and correct * 100 >= pass_pct * total  # integers: no rounding at the edge
