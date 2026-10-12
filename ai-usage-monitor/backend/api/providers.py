"""Provider status, read-only connection tests, and sync."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.connectors.registry import PROVIDER_NAMES, build_connector
from backend.database import get_db
from backend.models import Provider
from backend.schemas import ProviderUpdate
from backend.services.demo_data import ensure_providers
from backend.services.security import mask_secret, require_mutation_auth
from backend.services.sync import sync_provider

router = APIRouter()

_LABELS = {"openai": "OpenAI", "anthropic": "Anthropic", "xai": "xAI", "litellm": "LiteLLM"}


def _credential(name: str) -> tuple[str, str]:
    from backend.config import get_settings

    settings = get_settings()
    if name == "openai":
        return settings.openai_admin_key, "OPENAI_ADMIN_KEY"
    if name == "anthropic":
        return settings.anthropic_admin_key, "ANTHROPIC_ADMIN_KEY"
    if name == "xai":
        present = settings.xai_management_api_key and settings.xai_team_id
        return (settings.xai_management_api_key if present else ""), "XAI_MANAGEMENT_API_KEY"
    return (settings.litellm_api_key if settings.litellm_base_url else ""), "LITELLM_API_KEY"


def provider_views(db: Session) -> list[dict]:
    ensure_providers(db)
    db.commit()
    stored = {row.name: row for row in db.scalars(select(Provider)).all()}
    views = []
    for name in list(PROVIDER_NAMES) + ["litellm"]:
        connector = build_connector(name)
        check = connector.validate_config()
        row = stored.get(name)
        status = check.status if not check.ok else (row.connection_status if row else "configured")
        if check.ok and status == "not_configured":
            status = "configured"
        secret, env_name = _credential(name)
        views.append(
            {
                "name": name,
                "label": _LABELS[name],
                "enabled": True if row is None else row.enabled,
                "connection_status": status,
                "last_sync_at": row.last_sync_at.isoformat() if row and row.last_sync_at else None,
                "last_error": None if check.ok and status == "connected" else (row.last_error if row and check.ok else check.message),
                "credential": mask_secret(secret),
                "env_var": env_name,
                "capabilities": connector.capabilities(),
            }
        )
    return views


@router.get("/providers")
def list_providers(db: Session = Depends(get_db)) -> dict:
    return {"providers": provider_views(db)}


@router.put("/providers/{provider}")
def update_provider(
    provider: str,
    body: ProviderUpdate,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    require_mutation_auth(request)
    if provider not in set(PROVIDER_NAMES) | {"litellm"}:
        raise HTTPException(status_code=404, detail={"error_code": "not_found", "message": "Unknown provider."})
    ensure_providers(db)
    row = db.scalar(select(Provider).where(Provider.name == provider))
    if row is None:
        row = Provider(name=provider, enabled=body.enabled, connection_status="not_configured")
        db.add(row)
    else:
        row.enabled = body.enabled
    db.commit()
    return {"name": provider, "enabled": row.enabled}


@router.post("/providers/{provider}/test-connection")
def test_connection(provider: str, request: Request, db: Session = Depends(get_db)) -> dict:
    require_mutation_auth(request)
    if provider not in set(PROVIDER_NAMES) | {"litellm"}:
        raise HTTPException(status_code=404, detail={"error_code": "not_found", "message": "Unknown provider."})
    ensure_providers(db)
    connector = build_connector(provider)
    result = connector.test_connection()
    row = db.scalar(select(Provider).where(Provider.name == provider))
    if row is None:
        row = Provider(name=provider, enabled=True, connection_status=result.status)
        db.add(row)
    row.connection_status = result.status
    row.last_error = None if result.status == "connected" else result.message
    db.commit()
    return {
        "provider": provider,
        "status": result.status,
        "message": result.message,
        "reported_balance": result.reported_balance,
    }


@router.post("/providers/{provider}/sync")
def sync_one(provider: str, request: Request, db: Session = Depends(get_db)) -> dict:
    require_mutation_auth(request)
    if provider not in set(PROVIDER_NAMES) | {"litellm"}:
        raise HTTPException(status_code=404, detail={"error_code": "not_found", "message": "Unknown provider."})
    ensure_providers(db)
    result = sync_provider(db, provider)
    db.commit()
    return result
