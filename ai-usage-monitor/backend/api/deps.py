"""Shared query parsing."""

from __future__ import annotations

from datetime import date

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.settings_store import get_preferences, parse_fx

PROVIDERS = {"openai", "anthropic", "xai"}


def query_filters(
    db: Session = Depends(get_db),
    start: date | None = None,
    end: date | None = None,
    timezone: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    source: str | None = None,
    project: str | None = None,
    agent: str | None = None,
    include_demo: bool | None = None,
) -> dict:
    prefs = get_preferences(db)
    if provider and provider not in PROVIDERS:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "invalid_provider", "message": "Provider must be openai, anthropic, or xai."},
        )
    try:
        rates = parse_fx(prefs["fx_usd_rates"]) if prefs["fx_usd_rates"] else {}
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "invalid_fx", "message": str(exc)},
        ) from exc
    return {
        "db": db,
        "start": start,
        "end": end,
        "timezone": timezone or prefs["timezone"],
        "provider": provider,
        "model": model,
        "source": source,
        "project": project,
        "agent": agent,
        "include_demo": prefs["include_demo"] if include_demo is None else include_demo,
        "fx_rates": rates,
    }
