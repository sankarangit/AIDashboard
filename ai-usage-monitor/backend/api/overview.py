"""Overview, reconciliation, settings, and demo controls."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.api.deps import query_filters
from backend.database import get_db
from backend.schemas import SettingsUpdate
from backend.services.aggregation import build_overview
from backend.services.alerts import evaluate_alerts
from backend.services.demo_data import delete_demo, seed_demo
from backend.services.reconciliation import build_reconciliation
from backend.services.security import require_mutation_auth
from backend.services.settings_store import get_preferences, update_preferences

router = APIRouter()


@router.get("/overview")
def overview(filters: dict = Depends(query_filters)) -> dict:
    evaluate_alerts(filters["db"], include_demo=filters["include_demo"], tz_name=filters["timezone"])
    payload = build_overview(
        filters["db"],
        tz_name=filters["timezone"],
        start=filters["start"],
        end=filters["end"],
        include_demo=filters["include_demo"],
        provider=filters["provider"],
        model=filters["model"],
        source=filters["source"],
        project=filters["project"],
        agent=filters["agent"],
        fx_rates=filters["fx_rates"],
    )
    filters["db"].commit()
    return payload


@router.get("/reconciliation")
def reconciliation(filters: dict = Depends(query_filters)) -> dict:
    return build_reconciliation(
        filters["db"],
        tz_name=filters["timezone"],
        start=filters["start"],
        end=filters["end"],
        include_demo=filters["include_demo"],
        provider=filters["provider"],
    )


@router.get("/settings")
def read_settings(db: Session = Depends(get_db)) -> dict:
    prefs = get_preferences(db)
    prefs.pop("fx_rates", None)
    return prefs


@router.put("/settings")
def write_settings(body: SettingsUpdate, request: Request, db: Session = Depends(get_db)) -> dict:
    require_mutation_auth(request)
    prefs = update_preferences(db, body.model_dump(exclude_unset=True))
    db.commit()
    prefs.pop("fx_rates", None)
    return prefs


@router.post("/demo/seed")
def load_demo(request: Request, db: Session = Depends(get_db)) -> dict:
    require_mutation_auth(request)
    result = seed_demo(db)
    db.commit()
    return result


@router.delete("/demo")
def remove_demo(request: Request, db: Session = Depends(get_db)) -> dict:
    require_mutation_auth(request)
    result = delete_demo(db)
    db.commit()
    return result
