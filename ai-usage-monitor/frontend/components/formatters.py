"""Formatting that keeps missing measurements as N/A."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def fmt_money(value) -> str:
    if value is None:
        return "N/A"
    return f"${float(value):,.2f}"


def fmt_int(value, partial: bool = False) -> str:
    if value is None:
        return "N/A"
    text = f"{int(value):,}"
    return text + " (partial)" if partial else text


def fmt_percent(value) -> str:
    if value is None:
        return "N/A"
    return f"{float(value) * 100:.1f}%"


def fmt_number(value, digits: int = 1) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):,.{digits}f}"


def fmt_time(value: str | None, tz_name: str) -> str:
    if not value:
        return "N/A"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
    return parsed.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M %Z")
