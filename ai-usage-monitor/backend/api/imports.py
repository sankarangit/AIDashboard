"""Explicit file import. Nothing is read from the user profile automatically."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from backend.connectors.agent_import import import_agent_bytes
from backend.database import get_db
from backend.services.security import require_mutation_auth
from backend.services.settings_store import get_preferences

router = APIRouter()


@router.post("/imports")
async def import_file(
    request: Request,
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    require_mutation_auth(request)
    filename = upload.filename or "upload.csv"
    lowered = filename.lower()
    if not lowered.endswith(".csv") and not lowered.endswith(".jsonl"):
        raise HTTPException(
            status_code=422,
            detail={"error_code": "invalid_format", "message": "Upload a .csv or .jsonl file."},
        )
    payload = await upload.read()
    prefs = get_preferences(db)
    try:
        result = import_agent_bytes(db, filename=filename, payload=payload, assume_tz=prefs["timezone"])
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "invalid_import", "message": str(exc)},
        ) from exc
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "invalid_import", "message": "The file must be UTF-8 text."},
        ) from exc
    db.commit()
    return result
