"""Drawing a test from the pool (rule 6).

N questions, balanced across difficulty 1–3, in random order. Options are
shuffled, except for screenshot questions, whose letters A–D are drawn on the
image and stay in letter order. An ordering question never starts in the correct
order.
"""

from __future__ import annotations

import random
from collections.abc import Sequence

from app.errors import AppError
from app.models.enums import QuestionType

# Where a shortfall at one difficulty is filled from, nearest first.
_NEIGHBOURS = {1: (2, 3), 2: (1, 3), 3: (2, 1)}


def difficulty_targets(n: int) -> dict[int, int]:
    """Split N as evenly as possible; the remainder goes to difficulty 2, then 1."""
    base, rest = divmod(n, 3)
    targets = {1: base, 2: base, 3: base}
    if rest >= 1:
        targets[2] += 1
    if rest == 2:
        targets[1] += 1
    return targets


def draw(pool: dict[int, list[int]], n: int, rng: random.Random) -> list[int]:
    """Question ids for one attempt, already in display order."""
    if sum(len(ids) for ids in pool.values()) < n:
        raise AppError(409, "test.pool_too_small")
    targets = difficulty_targets(n)
    picked: dict[int, list[int]] = {}
    for d in (1, 2, 3):
        available = list(pool.get(d, []))
        picked[d] = rng.sample(available, min(targets[d], len(available)))
    for d in (1, 2, 3):
        missing = targets[d] - len(picked[d])
        for alt in _NEIGHBOURS[d]:
            if missing <= 0:
                break
            spare = [q for q in pool.get(alt, []) if q not in picked[alt]]
            extra = rng.sample(spare, min(missing, len(spare)))
            picked[alt] += extra
            missing -= len(extra)
    chosen = [q for d in (1, 2, 3) for q in picked[d]]
    rng.shuffle(chosen)
    return chosen


def option_order(q_type: QuestionType, option_ids: Sequence[int], rng: random.Random) -> list[int]:
    """Display order of a question's options; ``option_ids`` is the authored order."""
    authored = list(option_ids)
    if q_type == QuestionType.screenshot:
        return authored
    order = authored[:]
    rng.shuffle(order)
    if q_type == QuestionType.ordering and len(order) > 1:
        while order == authored:  # the authored order is the answer
            rng.shuffle(order)
    return order
