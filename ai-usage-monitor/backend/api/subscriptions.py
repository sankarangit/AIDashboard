"""Manual subscription records."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import PROVIDERS
from backend.connectors.manual_subscription import OFFICIAL_PAGES
from backend.database import get_db
from backend.models import Provider, Subscription
from backend.schemas import SubscriptionIn, SubscriptionUpdate
from backend.services.demo_data import ensure_providers
from backend.services.security import require_mutation_auth
from backend.services.settings_store import get_preferences

router = APIRouter()


def _serialize(item: Subscription, provider_name: str) -> dict:
    return {
        "id": item.id,
        "provider": provider_name,
        "plan": item.plan,
        "monthly_fee": float(item.monthly_fee),
        "currency": item.currency.upper(),
        "billing_day": item.billing_day,
        "renewal_date": item.renewal_date.isoformat() if item.renewal_date else None,
        "manual_allowance": item.manual_allowance,
        "manually_recorded_usage": item.manually_recorded_usage,
        "last_verified_at": item.last_verified_at.isoformat() if item.last_verified_at else None,
        "usage_page_url": item.usage_page_url,
        "api_usage_url": OFFICIAL_PAGES.get(provider_name),
        "notes": item.notes,
        "is_demo": item.is_demo,
        "badge": "Demo" if item.is_demo else "Manual",
    }


@router.get("/subscriptions")
def list_subscriptions(include_demo: bool | None = None, db: Session = Depends(get_db)) -> dict:
    prefs = get_preferences(db)
    show_demo = prefs["include_demo"] if include_demo is None else include_demo
    stmt = select(Subscription, Provider.name).join(Provider, Provider.id == Subscription.provider_id)
    if not show_demo:
        stmt = stmt.where(Subscription.is_demo.is_(False))
    rows = [_serialize(item, name) for item, name in db.execute(stmt).all()]
    return {
        "subscriptions": rows,
        "includes_demo_data": any(row["is_demo"] for row in rows),
        "note": "Fees here are manual subscription records. They are not added to provider-billed API cost.",
    }


@router.post("/subscriptions")
def create_subscription(body: SubscriptionIn, request: Request, db: Session = Depends(get_db)) -> dict:
    require_mutation_auth(request)
    if body.provider not in PROVIDERS:
        raise HTTPException(status_code=422, detail={"error_code": "invalid_provider", "message": "Unknown provider."})
    ensure_providers(db)
    provider = db.scalar(select(Provider).where(Provider.name == body.provider))
    item = Subscription(
        provider_id=provider.id,
        plan=body.plan,
        monthly_fee=body.monthly_fee,
        currency=body.currency.upper(),
        billing_day=body.billing_day,
        renewal_date=body.renewal_date,
        manual_allowance=body.manual_allowance,
        manually_recorded_usage=body.manually_recorded_usage,
        last_verified_at=datetime.now(UTC) if body.manual_allowance or body.manually_recorded_usage else None,
        usage_page_url=body.usage_page_url or OFFICIAL_PAGES[body.provider],
        notes=body.notes,
        is_demo=False,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialize(item, body.provider)


@router.put("/subscriptions/{subscription_id}")
def update_subscription(
    subscription_id: int,
    body: SubscriptionUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    require_mutation_auth(request)
    item = db.get(Subscription, subscription_id)
    if item is None or item.is_demo:
        raise HTTPException(status_code=404, detail={"error_code": "not_found", "message": "Subscription was not found."})
    for field in (
        "plan",
        "monthly_fee",
        "billing_day",
        "renewal_date",
        "manual_allowance",
        "manually_recorded_usage",
        "usage_page_url",
        "notes",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(item, field, value)
    if body.currency:
        item.currency = body.currency.upper()
    if body.manual_allowance or body.manually_recorded_usage:
        item.last_verified_at = datetime.now(UTC)
    provider_name = db.scalar(select(Provider.name).where(Provider.id == item.provider_id))
    db.commit()
    return _serialize(item, provider_name)


@router.delete("/subscriptions/{subscription_id}")
def delete_subscription(subscription_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    require_mutation_auth(request)
    item = db.get(Subscription, subscription_id)
    if item is None or item.is_demo:
        raise HTTPException(status_code=404, detail={"error_code": "not_found", "message": "Subscription was not found."})
    db.delete(item)
    db.commit()
    return {"deleted": subscription_id}
