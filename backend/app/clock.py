"""Single source of "now" so tests can move time (lockouts, cooldowns, deadlines).

Call it as ``clock.utcnow()`` after ``from app import clock``; importing the
function directly would bind it before a test can replace it.

Times are stored in UTC and shown in the bank's time zone (Asia/Tashkent). A
deadline is a date that ends at midnight after that day, local time.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from functools import cache
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(UTC)


@cache
def local_tz() -> ZoneInfo:
    from app.config import settings

    return ZoneInfo(settings.timezone)


def local_date(moment: datetime) -> date:
    return moment.astimezone(local_tz()).date()


def today() -> date:
    return local_date(utcnow())


def end_of_day(day: date) -> datetime:
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=local_tz())
