"""Optional single-process scheduler. It does not start unless enabled."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import delete

from backend.database import session_scope
from backend.models import CostRecord, UsageEvent
from backend.services.alerts import evaluate_alerts
from backend.services.settings_store import get_preferences
from backend.services.sync import sync_all


def apply_retention(days: int) -> int:
    if days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=days)
    with session_scope() as db:
        usage = db.execute(
            delete(UsageEvent).where(
                UsageEvent.is_demo.is_(False),
                UsageEvent.occurred_at_utc < cutoff,
            )
        ).rowcount or 0
        costs = db.execute(
            delete(CostRecord).where(
                CostRecord.is_demo.is_(False),
                CostRecord.period_start_utc < cutoff,
            )
        ).rowcount or 0
        return int(usage + costs)


def scheduled_sync() -> None:
    with session_scope() as db:
        sync_all(db)
        prefs = get_preferences(db)
        evaluate_alerts(db, include_demo=prefs["include_demo"], tz_name=prefs["timezone"])
    apply_retention(get_preferences_days())


def get_preferences_days() -> int:
    with session_scope() as db:
        return int(get_preferences(db)["retention_days"])


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(scheduled_sync, "interval", hours=6, id="usage_sync", max_instances=1)
    scheduler.start()
    return scheduler
