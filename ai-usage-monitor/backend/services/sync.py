"""Read-only provider sync. One provider failing does not stop the others."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.connectors.base import ConnectorError, Page, ProviderConnector
from backend.connectors.registry import PROVIDER_NAMES, build_connector
from backend.models import Provider, SyncRun
from backend.services.ingest import insert_cost_record, insert_usage_event
from backend.services.security import redact
from backend.services.timeutils import as_utc


def sync_all(db: Session, *, include_litellm: bool = True) -> list[dict]:
    names = list(PROVIDER_NAMES)
    if include_litellm and build_connector("litellm").validate_config().ok:
        names.append("litellm")
    results = []
    for name in names:
        try:
            results.append(sync_provider(db, name))
            db.commit()
        except Exception as exc:  # noqa: BLE001 — isolation between providers
            db.rollback()
            results.append({"provider": name, "status": "failed", "message": redact(str(exc)), "inserted": 0})
    return results


def sync_provider(db: Session, name: str, connector: ProviderConnector | None = None) -> dict:
    provider = _provider(db, name)
    connector = connector or build_connector(name)
    started = datetime.now(UTC)
    run = SyncRun(
        provider_id=provider.id,
        started_at=started,
        status="running",
        records_inserted=0,
    )
    db.add(run)
    db.flush()
    if not provider.enabled:
        return _finish(db, provider, run, "unsupported", "Provider sync is disabled.", 0, None)
    check = connector.validate_config()
    if not check.ok:
        provider.connection_status = check.status
        provider.last_error = check.message
        return _finish(db, provider, run, check.status, check.message, 0, None)
    settings = get_settings()
    end = datetime.now(UTC)
    start = end - timedelta(days=settings.sync_lookback_days)
    if provider.last_sync_at is not None:
        overlap_start = as_utc(provider.last_sync_at) - timedelta(days=settings.sync_overlap_days)
        if overlap_start > start:
            start = overlap_start
    inserted = 0
    notices: list[str] = []
    cursor = None
    try:
        usage_pages = _collect(lambda page_cursor: connector.fetch_usage(start, end, page_cursor))
        cost_pages = _collect(lambda page_cursor: connector.fetch_costs(start, end, page_cursor))
        if usage_pages[-1].unrecognized or cost_pages[-1].unrecognized:
            notice = usage_pages[-1].notice or cost_pages[-1].notice or "Unrecognized provider payload."
            provider.connection_status = "failed"
            provider.last_error = notice
            return _finish(db, provider, run, "failed", notice, 0, None)
        for page in usage_pages + cost_pages:
            if page.notice:
                notices.append(page.notice)
            cursor = page.next_cursor or cursor
        for page in usage_pages:
            for record in page.records:
                target = _provider(db, getattr(record, "provider_name", None) or name)
                if insert_usage_event(db, provider_id=target.id, row=record.as_row()):
                    inserted += 1
        for page in cost_pages:
            for record in page.records:
                target = _provider(db, getattr(record, "provider_name", None) or name)
                if insert_cost_record(db, provider_id=target.id, row=record.as_row()):
                    inserted += 1
    except ConnectorError as exc:
        provider.connection_status = exc.status
        provider.last_error = exc.message
        return _finish(db, provider, run, exc.status, exc.message, inserted, cursor)
    provider.connection_status = "connected"
    provider.last_sync_at = datetime.now(UTC)
    provider.last_error = "; ".join(notices) if notices else None
    message = "Sync stored provider-reported rows." if inserted else "Sync completed. The provider returned no new rows."
    if notices:
        message = message + " " + " ".join(notices)
    return _finish(db, provider, run, "connected", message, inserted, cursor)


def _collect(fetch) -> list[Page]:
    pages: list[Page] = []
    cursor = None
    for _ in range(20):
        page = fetch(cursor)
        pages.append(page)
        if page.unrecognized or not page.next_cursor:
            break
        cursor = page.next_cursor
    return pages


def _provider(db: Session, name: str) -> Provider:
    provider = db.scalar(select(Provider).where(Provider.name == name))
    if provider is None:
        if name == "litellm":
            provider = Provider(name="litellm", enabled=True, connection_status="not_configured")
            db.add(provider)
            db.flush()
            return provider
        raise KeyError(name)
    return provider


def _finish(db: Session, provider: Provider, run: SyncRun, status: str, message: str, inserted: int, cursor: str | None) -> dict:
    run.completed_at = datetime.now(UTC)
    run.status = status
    run.records_inserted = inserted
    run.error_summary = None if status == "connected" else message
    run.next_cursor = cursor
    db.flush()
    return {
        "provider": provider.name,
        "status": status,
        "message": message,
        "inserted": inserted,
    }
