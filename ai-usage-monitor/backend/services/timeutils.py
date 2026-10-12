"""UTC storage helpers and Asia/Singapore day boundaries."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_timestamp(value: object, assume_tz: str = "UTC") -> datetime:
    if isinstance(value, datetime):
        return as_utc(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), UTC)
    text = str(value).strip()
    if not text:
        raise ValueError("missing timestamp")
    if text.isdigit():
        return datetime.fromtimestamp(int(text), UTC)
    normalized = text.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(assume_tz))
    return parsed.astimezone(UTC)


def timezone_or_raise(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {name}") from exc


def to_local_date(value: datetime, tz_name: str) -> date:
    return as_utc(value).astimezone(timezone_or_raise(tz_name)).date()


def local_day_bounds(day: date, tz_name: str) -> tuple[datetime, datetime]:
    tz = timezone_or_raise(tz_name)
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    end = start + timedelta(days=1)
    return start.astimezone(UTC), end.astimezone(UTC)


def inclusive_range_bounds(start: date, end: date, tz_name: str) -> tuple[datetime, datetime]:
    if end < start:
        raise ValueError("end date is before start date")
    start_utc, _ = local_day_bounds(start, tz_name)
    _, end_utc = local_day_bounds(end, tz_name)
    return start_utc, end_utc


def default_range(tz_name: str, days: int = 30) -> tuple[date, date]:
    today = datetime.now(UTC).astimezone(timezone_or_raise(tz_name)).date()
    return today - timedelta(days=days - 1), today


def month_bounds(tz_name: str, moment: datetime | None = None) -> tuple[datetime, datetime, str]:
    current = as_utc(moment or datetime.now(UTC)).astimezone(timezone_or_raise(tz_name))
    start_day = date(current.year, current.month, 1)
    if current.month == 12:
        next_month = date(current.year + 1, 1, 1)
    else:
        next_month = date(current.year, current.month + 1, 1)
    start_utc, _ = local_day_bounds(start_day, tz_name)
    end_utc, _ = local_day_bounds(next_month, tz_name)
    return start_utc, end_utc, f"{current.year:04d}-{current.month:02d}"
