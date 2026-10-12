"""Budget threshold alerts. Mail is sent only when explicitly enabled."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import Alert
from backend.services.aggregation import budget_utilization
from backend.services.security import send_budget_email


def evaluate_alerts(db: Session, *, include_demo: bool, tz_name: str) -> list[dict]:
    snapshot = budget_utilization(db, include_demo=include_demo, tz_name=tz_name)
    settings = get_settings()
    created = []
    for item in snapshot["budgets"]:
        if not item["enabled"] or item["utilization"] is None:
            continue
        percent = item["utilization"] * 100
        for threshold in settings.standard_alert_thresholds:
            if percent + 1e-9 < threshold:
                continue
            existing = db.scalar(
                select(Alert).where(
                    Alert.budget_id == item["id"],
                    Alert.period == item["period"],
                    Alert.threshold == threshold,
                )
            )
            if existing is not None:
                continue
            alert = Alert(
                budget_id=item["id"],
                period=item["period"],
                threshold=threshold,
                triggered_at=datetime.now(UTC),
                status="open",
            )
            db.add(alert)
            db.flush()
            delivery = "skipped_demo" if item["is_demo"] else "disabled"
            if not item["is_demo"]:
                delivery = send_budget_email(
                    subject=f"AI usage budget reached {threshold}%",
                    body=(
                        f"Provider {item['provider'] or 'combined'} billed API spend "
                        f"reached {percent:.1f}% of the monthly budget for {item['period']}."
                    ),
                )
            created.append({"id": alert.id, "threshold": threshold, "delivery": delivery})
    return created
