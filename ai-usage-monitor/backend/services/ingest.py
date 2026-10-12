"""Idempotent inserts. A repeated external id does not change stored totals."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import CostRecord, UsageEvent
from backend.services.timeutils import as_utc

COST_KINDS = {"provider_billed", "gateway_estimated", "manual"}


def stable_id(*parts: object) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def insert_usage_event(db: Session, *, provider_id: int, row: dict) -> bool:
    existing = db.scalar(
        select(UsageEvent.id).where(
            UsageEvent.provider_id == provider_id,
            UsageEvent.source_type == row["source_type"],
            UsageEvent.external_event_id == row["external_event_id"],
        )
    )
    if existing is not None:
        return False
    metadata = row.get("metadata")
    event = UsageEvent(
        provider_id=provider_id,
        source_type=row["source_type"],
        external_event_id=row["external_event_id"],
        occurred_at_utc=as_utc(row["occurred_at_utc"]),
        model=row.get("model"),
        project_id=row.get("project_id"),
        agent_name=row.get("agent_name"),
        input_tokens=row.get("input_tokens"),
        output_tokens=row.get("output_tokens"),
        cache_read_tokens=row.get("cache_read_tokens"),
        cache_write_tokens=row.get("cache_write_tokens"),
        request_count=row.get("request_count"),
        latency_ms=row.get("latency_ms"),
        success=row.get("success"),
        metadata_json=json.dumps(metadata) if metadata else None,
        is_demo=bool(row.get("is_demo", False)),
        created_at=as_utc(row.get("created_at") or datetime.now(UTC)),
    )
    try:
        with db.begin_nested():
            db.add(event)
            db.flush()
    except IntegrityError:
        return False
    return True


def insert_cost_record(db: Session, *, provider_id: int, row: dict) -> bool:
    kind = row["cost_kind"]
    if kind not in COST_KINDS:
        raise ValueError(f"Unsupported cost kind: {kind}")
    existing = db.scalar(
        select(CostRecord.id).where(
            CostRecord.provider_id == provider_id,
            CostRecord.source_type == row["source_type"],
            CostRecord.external_record_id == row["external_record_id"],
        )
    )
    if existing is not None:
        return False
    amount = row.get("cost_usd")
    if amount is None:
        return False
    record = CostRecord(
        provider_id=provider_id,
        source_type=row["source_type"],
        external_record_id=row["external_record_id"],
        period_start_utc=as_utc(row["period_start_utc"]),
        period_end_utc=as_utc(row["period_end_utc"]),
        model=row.get("model"),
        project_id=row.get("project_id"),
        agent_name=row.get("agent_name"),
        cost_usd=Decimal(str(amount)),
        cost_kind=kind,
        is_demo=bool(row.get("is_demo", False)),
        created_at=as_utc(row.get("created_at") or datetime.now(UTC)),
    )
    try:
        with db.begin_nested():
            db.add(record)
            db.flush()
    except IntegrityError:
        return False
    return True
