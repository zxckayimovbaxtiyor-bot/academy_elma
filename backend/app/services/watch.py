"""The 90 % rule, as pure functions over watched time ranges in seconds.

A heartbeat reports what the player actually played since the previous heartbeat.
The server decides what counts:

* ranges are clipped to the video;
* before the lesson is complete, nothing that starts beyond the furthest point
  reached so far (plus a few seconds) counts. This is the seek block;
* one heartbeat can't credit more play than the wall-clock time since the previous
  one allows (at most 30 s of it, at 1x before completion and 2x after, plus 15 %
  for network jitter). The tolerance is proportional, so sending heartbeats more
  often never earns extra credit, and two tabs share one clock;
* replaying a part adds no coverage.

The browser never sends a "completed" flag; completion is computed here.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

COMPLETION_RATIO = 0.9
SEEK_TOLERANCE_S = 5.0
MAX_HEARTBEAT_GAP_S = 30.0
SPEED_CAP_FIRST_VIEW = 1.0
SPEED_CAP_AFTER_COMPLETION = 2.0
TIMING_TOLERANCE = 0.15
_TOUCH = 1e-3  # ranges this close are one range (float noise between heartbeats)

Range = tuple[float, float]


def clean(ranges: Iterable[Sequence[float]], duration: float) -> list[Range]:
    """Clip to [0, duration], drop empty ranges, sort by start."""
    out = []
    for start, end in ranges:
        a, b = max(0.0, float(start)), min(float(duration), float(end))
        if b - a > 0:
            out.append((a, b))
    return sorted(out)


def merge(ranges: Iterable[Sequence[float]]) -> list[Range]:
    merged: list[list[float]] = []
    for a, b in sorted((float(s), float(e)) for s, e in ranges):
        if merged and a <= merged[-1][1] + _TOUCH:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def total(ranges: Iterable[Sequence[float]]) -> float:
    return sum(b - a for a, b in merge(ranges))


def intersect(ranges: Iterable[Sequence[float]], lo: float, hi: float) -> list[Range]:
    return [(max(a, lo), min(b, hi)) for a, b in ranges if min(b, hi) > max(a, lo)]


def is_complete(watched_s: float, duration: float) -> bool:
    return duration > 0 and watched_s >= COMPLETION_RATIO * duration - 1e-6


@dataclass(frozen=True)
class Credit:
    accepted: list[Range]  # what this heartbeat actually counted
    watched: list[Range]  # merged coverage after it
    watched_s: float
    max_position_s: float


def credit(
    *,
    watched: Iterable[Sequence[float]],
    incoming: Iterable[Sequence[float]],
    duration: float,
    max_position_s: float,
    completed: bool,
    elapsed_s: float,
) -> Credit:
    cap = SPEED_CAP_AFTER_COMPLETION if completed else SPEED_CAP_FIRST_VIEW
    budget = min(max(elapsed_s, 0.0), MAX_HEARTBEAT_GAP_S) * cap * (1 + TIMING_TOLERANCE)
    frontier = max_position_s
    accepted: list[Range] = []
    for a, b in clean(incoming, duration):
        if budget <= 0:
            break
        if not completed and a > frontier + SEEK_TOLERANCE_S:
            continue  # jumped ahead on the first viewing: not counted
        b = min(b, a + budget)
        accepted.append((a, b))
        budget -= b - a
        frontier = max(frontier, b)
    new_watched = merge([*watched, *accepted])
    return Credit(
        accepted=accepted,
        watched=new_watched,
        watched_s=round(total(new_watched), 3),
        max_position_s=max([max_position_s, *(b for _, b in accepted)]),
    )
