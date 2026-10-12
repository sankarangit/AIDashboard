"""Cross-source comparison. Billed and estimated amounts stay in separate fields."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from backend.services.aggregation import load_costs, reconcile, resolve_window
from backend.services.settings_store import get_preferences


def build_reconciliation(
    db: Session,
    *,
    tz_name: str,
    start: date | None,
    end: date | None,
    include_demo: bool,
    provider: str | None = None,
) -> dict:
    start_day, end_day, start_utc, end_utc = resolve_window(tz_name, start, end)
    costs = load_costs(
        db,
        start_utc=start_utc,
        end_utc=end_utc,
        include_demo=include_demo,
        provider=provider,
    )
    payload = reconcile(costs, tz_name)
    flags = [record.is_demo for record, _name in costs]
    from backend.services.aggregation import classification

    payload.update(classification(flags))
    payload["range"] = {"start": start_day.isoformat(), "end": end_day.isoformat(), "timezone": tz_name}
    payload["preferences_timezone"] = get_preferences(db)["timezone"]
    return payload
