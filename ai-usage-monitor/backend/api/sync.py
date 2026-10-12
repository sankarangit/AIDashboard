"""Sync entry points."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.services.security import require_mutation_auth
from backend.services.sync import sync_all

router = APIRouter()


@router.post("/sync")
def sync_every(request: Request, db: Session = Depends(get_db)) -> dict:
    require_mutation_auth(request)
    results = sync_all(db)
    db.commit()
    return {"results": results}
