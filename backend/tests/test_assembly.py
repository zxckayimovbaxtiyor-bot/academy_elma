"""Drawing a test and scoring it: pure functions, no database."""

from __future__ import annotations

import random
from collections import Counter

import pytest

from app.errors import AppError
from app.models.enums import QuestionType
from app.services import assembly, grading


def _pool(per_difficulty: dict[int, int]) -> dict[int, list[int]]:
    """Ids encode the difficulty: 1xxx, 2xxx, 3xxx."""
    return {d: [d * 1000 + i for i in range(n)] for d, n in per_difficulty.items()}


@pytest.mark.parametrize(
    ("n", "targets"),
    [
        (15, {1: 5, 2: 5, 3: 5}),
        (16, {1: 5, 2: 6, 3: 5}),
        (17, {1: 6, 2: 6, 3: 5}),
        (1, {1: 0, 2: 1, 3: 0}),
    ],
)
def test_difficulty_targets_split_evenly_remainder_to_2_then_1(n, targets):
    assert assembly.difficulty_targets(n) == targets


def test_draw_is_balanced_unique_and_shuffled():
    pool = _pool({1: 15, 2: 15, 3: 15})
    orders = set()
    for seed in range(20):
        chosen = assembly.draw(pool, 15, random.Random(seed))
        assert len(chosen) == len(set(chosen)) == 15
        assert Counter(q // 1000 for q in chosen) == {1: 5, 2: 5, 3: 5}
        orders.add(tuple(chosen))
    assert len(orders) == 20  # random picks and random order


def test_draw_order_is_not_grouped_by_difficulty():
    pool = _pool({1: 5, 2: 5, 3: 5})
    grouped = 0
    for seed in range(50):
        chosen = assembly.draw(pool, 15, random.Random(seed))
        if [q // 1000 for q in chosen] == sorted(q // 1000 for q in chosen):
            grouped += 1
    assert grouped == 0


def test_short_bucket_is_filled_from_the_adjacent_difficulty():
    pool = _pool({1: 2, 2: 20, 3: 20})
    chosen = assembly.draw(pool, 15, random.Random(1))
    counts = Counter(q // 1000 for q in chosen)
    assert counts == {1: 2, 2: 8, 3: 5}  # difficulty 1 short by 3, taken from 2 first

    pool = _pool({1: 20, 2: 20, 3: 0})
    counts = Counter(q // 1000 for q in assembly.draw(pool, 15, random.Random(1)))
    assert counts == {1: 5, 2: 10}  # difficulty 3 falls back to 2

    pool = _pool({1: 0, 2: 1, 3: 20})
    counts = Counter(q // 1000 for q in assembly.draw(pool, 15, random.Random(1)))
    assert counts == {2: 1, 3: 14}


def test_draw_refuses_a_pool_smaller_than_n():
    with pytest.raises(AppError) as err:
        assembly.draw(_pool({1: 4, 2: 5, 3: 5}), 15, random.Random(1))
    assert err.value.code == "test.pool_too_small"


def test_screenshot_options_keep_the_letter_order():
    for seed in range(20):
        rng = random.Random(seed)
        assert assembly.option_order(QuestionType.screenshot, [11, 12, 13, 14], rng) == [
            11, 12, 13, 14,
        ]  # fmt: skip


def test_ordering_never_starts_in_the_correct_order():
    authored = [1, 2, 3]
    seen = set()
    for seed in range(200):
        order = assembly.option_order(QuestionType.ordering, authored, random.Random(seed))
        assert order != authored and sorted(order) == authored
        seen.add(tuple(order))
    assert len(seen) == 5  # every other permutation shows up
    assert assembly.option_order(QuestionType.ordering, [7, 8], random.Random(3)) == [8, 7]


def test_single_and_multiple_options_are_shuffled():
    orders = {
        tuple(assembly.option_order(QuestionType.single, [1, 2, 3, 4], random.Random(seed)))
        for seed in range(30)
    }
    assert len(orders) > 10 and all(sorted(o) == [1, 2, 3, 4] for o in orders)


# --- grading ----------------------------------------------------------------------------


def test_single_and_screenshot_need_exactly_the_correct_option():
    for q_type in (QuestionType.single, QuestionType.screenshot):
        assert grading.is_correct(q_type, [1, 2, 3], {2}, [2])
        assert not grading.is_correct(q_type, [1, 2, 3], {2}, [1])
        assert not grading.is_correct(q_type, [1, 2, 3], {2}, [2, 1])


def test_multiple_is_all_or_nothing():
    authored, correct = [1, 2, 3, 4], {1, 3}
    assert grading.is_correct(QuestionType.multiple, authored, correct, [3, 1])
    assert not grading.is_correct(QuestionType.multiple, authored, correct, [1])  # partial
    assert not grading.is_correct(QuestionType.multiple, authored, correct, [1, 3, 4])  # extra
    assert not grading.is_correct(QuestionType.multiple, authored, correct, [1, 1, 3])


def test_ordering_needs_the_authored_order():
    assert grading.is_correct(QuestionType.ordering, [5, 6, 7], set(), [5, 6, 7])
    assert not grading.is_correct(QuestionType.ordering, [5, 6, 7], set(), [5, 7, 6])


def test_unanswered_is_wrong():
    for q_type in QuestionType:
        assert not grading.is_correct(q_type, [1, 2], {1}, None)
        assert not grading.is_correct(q_type, [1, 2], {1}, [])


def test_pass_threshold_is_inclusive_and_exact():
    assert grading.passed(12, 15, 80)  # exactly 80 %
    assert not grading.passed(11, 15, 80)  # 73.3 %
    assert grading.score_pct(12, 15) == 80.0 and grading.score_pct(11, 15) == 73.33
    assert grading.passed(7, 10, 70) and not grading.passed(6, 10, 70)
    # 2/3 = 66.67 % must not pass a 67 % mark through rounding
    assert not grading.passed(2, 3, 67) and grading.passed(2, 3, 66)
    assert not grading.passed(0, 0, 80)
