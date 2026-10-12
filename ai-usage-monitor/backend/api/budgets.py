"""Budgets and threshold alerts."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import PROVIDERS, query_filters
from backend.database import get_db
from backend.models import Alert, Budget, Provider
from backend.schemas import BudgetIn, BudgetUpdate
from backend.services.aggregation import budget_utilization
from backend.services.alerts import evaluate_alerts
from backend.services.demo_data import ensure_providers
from backend.services.security import require_mutation_auth

router = APIRouter()


def _name_for(db: Session, provider_id: int | None) -> str | None:
    if provider_id is None:
        return None
    return db.scalar(select(Provider.name).where(Provider.id == provider_id))


@router.get("/budgets")
def list_budgets(filters: dict = Depends(query_filters)) -> dict:
    evaluate_alerts(filters["db"], include_demo=filters["include_demo"], tz_name=filters["timezone"])
    payload = budget_utilization(
        filters["db"],
        include_demo=filters["include_demo"],
        tz_name=filters["timezone"],
    )
    alerts = db_alerts(filters["db"], filters["include_demo"])
    filters["db"].commit()
    payload["alerts"] = alerts
    payload["thresholds"] = [50, 80, 100]
    payload["note"] = "Utilization uses provider-billed API cost for the calendar month. Estimated cost is excluded."
    return payload


def db_alerts(db: Session, include_demo: bool) -> list[dict]:
    stmt = select(Alert, Budget).join(Budget, Budget.id == Alert.budget_id)
    if not include_demo:
        stmt = stmt.where(Budget.is_demo.is_(False))
    rows = []
    for alert, budget in db.execute(stmt).all():
        rows.append(
            {
                "id": alert.id,
                "budget_id": budget.id,
                "provider": _name_for(db, budget.provider_id),
                "period": alert.period,
                "threshold": alert.threshold,
                "triggered_at": alert.triggered_at.isoformat(),
                "status": alert.status,
                "is_demo": budget.is_demo,
            }
        )
    return rows


@router.post("/budgets")
def create_budget(body: BudgetIn, request: Request, db: Session = Depends(get_db)) -> dict:
    require_mutation_auth(request)
    provider_id = None
    if body.provider:
        if body.provider not in PROVIDERS:
            raise HTTPException(status_code=422, detail={"error_code": "invalid_provider", "message": "Unknown provider."})
        ensure_providers(db)
        provider_id = db.scalar(select(Provider.id).where(Provider.name == body.provider))
    item = Budget(
        provider_id=provider_id,
        monthly_budget_usd=body.monthly_budget_usd,
        threshold_percent=body.threshold_percent,
        enabled=body.enabled,
        is_demo=False,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "provider": body.provider, "is_demo": False}


@router.put("/budgets/{budget_id}")
def update_budget(budget_id: int, body: BudgetUpdate, request: Request, db: Session = Depends(get_db)) -> dict:
    require_mutation_auth(request)
    item = db.get(Budget, budget_id)
    if item is None or item.is_demo:
        raise HTTPException(status_code=404, detail={"error_code": "not_found", "message": "Budget was not found."})
    if body.monthly_budget_usd is not None:
        item.monthly_budget_usd = body.monthly_budget_usd
    if body.threshold_percent is not None:
        item.threshold_percent = body.threshold_percent
    if body.enabled is not None:
        item.enabled = body.enabled
    db.commit()
    return {"id": item.id, "enabled": item.enabled}


@router.delete("/budgets/{budget_id}")
def delete_budget(budget_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    require_mutation_auth(request)
    item = db.get(Budget, budget_id)
    if item is None or item.is_demo:
        raise HTTPException(status_code=404, detail={"error_code": "not_found", "message": "Budget was not found."})
    db.query(Alert).filter(Alert.budget_id == item.id).delete()
    db.delete(item)
    db.commit()
    return {"deleted": budget_id}


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: int, request: Request, db: Session = Depends(get_db)) -> dict:
    require_mutation_auth(request)
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail={"error_code": "not_found", "message": "Alert was not found."})
    alert.status = "acknowledged"
    db.commit()
    return {"id": alert.id, "status": alert.status}
