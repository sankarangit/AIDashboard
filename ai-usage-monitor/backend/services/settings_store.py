"""Stored UI preferences. Provider secrets are not kept here."""

from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import AppSetting
from backend.services.timeutils import timezone_or_raise


def _raw(db: Session) -> dict[str, str]:
    return {row.key: row.value for row in db.scalars(select(AppSetting)).all()}


def _put(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


def parse_fx(raw: str) -> dict[str, Decimal]:
    if not raw or not raw.strip():
        return {}
    loaded = json.loads(raw)
    if not isinstance(loaded, dict):
        raise ValueError("FX rates must be a JSON object of currency to USD rate.")
    rates = {}
    for key, value in loaded.items():
        rates[str(key).upper()] = Decimal(str(value))
    return rates


def get_preferences(db: Session) -> dict:
    stored = _raw(db)
    settings = get_settings()
    timezone = stored.get("timezone") or settings.default_timezone
    timezone_or_raise(timezone)
    include_demo = stored.get("include_demo", "true").lower() == "true"
    retention = int(stored.get("retention_days", "365"))
    fx_raw = stored.get("fx_usd_rates") or settings.fx_usd_rates
    try:
        parsed_rates = parse_fx(fx_raw) if fx_raw else {}
    except (ValueError, json.JSONDecodeError):
        parsed_rates = {}
        fx_raw = ""
    email_enabled = stored.get("alert_email_enabled")
    if email_enabled is None:
        email_flag = settings.alert_email_enabled
    else:
        email_flag = email_enabled.lower() == "true"
    return {
        "timezone": timezone,
        "include_demo": include_demo,
        "retention_days": retention,
        "alert_email_enabled": email_flag and settings.alert_email_enabled,
        "alert_email_to": stored.get("alert_email_to") or settings.alert_email_to,
        "fx_usd_rates": fx_raw,
        "fx_rates": {key: str(value) for key, value in parsed_rates.items()},
    }


def update_preferences(db: Session, updates: dict) -> dict:
    if "timezone" in updates and updates["timezone"]:
        timezone_or_raise(updates["timezone"])
        _put(db, "timezone", updates["timezone"])
    if "include_demo" in updates and updates["include_demo"] is not None:
        _put(db, "include_demo", "true" if updates["include_demo"] else "false")
    if "retention_days" in updates and updates["retention_days"] is not None:
        _put(db, "retention_days", str(int(updates["retention_days"])))
    if "alert_email_enabled" in updates and updates["alert_email_enabled"] is not None:
        _put(db, "alert_email_enabled", "true" if updates["alert_email_enabled"] else "false")
    if "alert_email_to" in updates and updates["alert_email_to"] is not None:
        _put(db, "alert_email_to", updates["alert_email_to"])
    if "fx_usd_rates" in updates and updates["fx_usd_rates"] is not None:
        parse_fx(updates["fx_usd_rates"])
        _put(db, "fx_usd_rates", updates["fx_usd_rates"])
    db.flush()
    return get_preferences(db)
