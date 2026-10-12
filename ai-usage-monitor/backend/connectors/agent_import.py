"""User-approved agent log import.

The file path or upload must be explicit. Home-directory logs are never scanned.
Prompt and response columns are dropped and are not stored.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.connectors.litellm_import import map_provider
from backend.models import ImportBatch, Provider
from backend.services.ingest import insert_cost_record, insert_usage_event, stable_id
from backend.services.timeutils import parse_timestamp

DROPPED_COLUMNS = {
    "prompt",
    "prompts",
    "response",
    "responses",
    "completion",
    "messages",
    "message",
    "content",
    "input",
    "output",
    "body",
    "request_body",
    "response_body",
}

REQUIRED_HINT = (
    "Each row needs timestamp, provider, and model. "
    "Optional columns: agent, input_tokens, output_tokens, cache_tokens, "
    "estimated_cost_usd, latency_ms, request_id, result, source."
)


def import_agent_bytes(
    db: Session,
    *,
    filename: str,
    payload: bytes,
    source_type: str = "agent_import",
    assume_tz: str = "UTC",
) -> dict:
    settings = get_settings()
    if len(payload) > settings.max_import_bytes:
        raise ValueError(f"File exceeds the {settings.max_import_bytes} byte limit.")
    digest = hashlib.sha256(payload).hexdigest()
    existing = db.scalar(select(ImportBatch).where(ImportBatch.sha256 == digest))
    if existing is not None:
        return {
            "import_id": existing.id,
            "filename": existing.filename,
            "row_count": existing.row_count,
            "rejected_count": existing.rejected_count,
            "inserted": 0,
            "duplicate_file": True,
        }
    text = payload.decode("utf-8-sig")
    if filename.lower().endswith(".jsonl") or source_type == "jsonl":
        raw_rows = _jsonl_rows(text)
    else:
        raw_rows = _csv_rows(text)
    if len(raw_rows) > settings.max_import_rows:
        raise ValueError(f"File exceeds the {settings.max_import_rows} row limit.")
    inserted = 0
    rejected = 0
    reasons: list[str] = []
    providers = {row.name: row for row in db.scalars(select(Provider)).all()}
    for index, raw in enumerate(raw_rows, start=1):
        try:
            inserted += _store_row(db, raw, providers, assume_tz)
        except ValueError as exc:
            rejected += 1
            if len(reasons) < 20:
                reasons.append(f"row {index}: {exc}")
    batch = ImportBatch(
        filename=filename[:240],
        sha256=digest,
        source_type="agent_import",
        imported_at=datetime.now(UTC),
        row_count=inserted,
        rejected_count=rejected,
    )
    db.add(batch)
    db.flush()
    return {
        "import_id": batch.id,
        "filename": batch.filename,
        "row_count": inserted,
        "rejected_count": rejected,
        "inserted": inserted,
        "duplicate_file": False,
        "rejected_reasons": reasons,
        "schema_hint": REQUIRED_HINT,
    }


def _csv_rows(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV file has no header row.")
    return [dict(row) for row in reader]


def _jsonl_rows(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError("JSONL rows must be objects.")
        rows.append(item)
    return rows


def _clean(row: dict) -> dict:
    cleaned = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized = key.strip()
        if normalized.lower() in DROPPED_COLUMNS:
            continue
        cleaned[normalized] = value
    return cleaned


def _blank(value: object) -> bool:
    return value is None or str(value).strip() == ""


def _optional_int(value: object, label: str) -> int | None:
    if _blank(value):
        return None
    try:
        return int(float(str(value)))
    except ValueError as exc:
        raise ValueError(f"{label} is not an integer") from exc


def _success(value: object) -> bool | None:
    if _blank(value):
        return None
    text = str(value).strip().lower()
    if text in {"success", "ok", "true", "succeeded"}:
        return True
    if text in {"error", "failed", "false", "failure"}:
        return False
    return None


def _store_row(db: Session, raw: dict, providers: dict[str, Provider], assume_tz: str) -> int:
    row = _clean(raw)
    lowered = {key.lower(): value for key, value in row.items()}
    stamp = None
    for key in ("timestamp", "occurred_at", "time", "starttime"):
        if key in lowered and not _blank(lowered[key]):
            stamp = lowered[key]
            break
    if stamp is None:
        raise ValueError("missing timestamp")
    provider_name = map_provider(str(lowered.get("provider") or ""))
    if provider_name is None:
        raise ValueError("provider must be openai, anthropic, or xai")
    provider = providers.get(provider_name)
    if provider is None:
        raise ValueError("provider is not available")
    occurred = parse_timestamp(stamp, assume_tz=assume_tz)
    model = None if _blank(lowered.get("model")) else str(lowered.get("model"))
    agent = None if _blank(lowered.get("agent")) else str(lowered.get("agent"))
    request_id = None if _blank(lowered.get("request_id")) else str(lowered.get("request_id"))
    identity = stable_id(
        "agent",
        provider_name,
        request_id or "",
        occurred.isoformat(),
        model,
        agent,
        lowered.get("input_tokens"),
        lowered.get("output_tokens"),
    )
    stored = insert_usage_event(
        db,
        provider_id=provider.id,
        row={
            "external_event_id": identity,
            "occurred_at_utc": occurred,
            "source_type": "agent_import",
            "model": model,
            "agent_name": agent,
            "input_tokens": _optional_int(lowered.get("input_tokens"), "input_tokens"),
            "output_tokens": _optional_int(lowered.get("output_tokens"), "output_tokens"),
            "cache_read_tokens": _optional_int(lowered.get("cache_tokens"), "cache_tokens"),
            "request_count": 1,
            "latency_ms": _optional_int(lowered.get("latency_ms"), "latency_ms"),
            "success": _success(lowered.get("result")),
            "metadata": {"origin": "explicit_import"},
            "is_demo": False,
        },
    )
    cost = lowered.get("estimated_cost_usd")
    if not _blank(cost):
        try:
            amount = float(str(cost))
        except ValueError as exc:
            raise ValueError("estimated_cost_usd is not a number") from exc
        insert_cost_record(
            db,
            provider_id=provider.id,
            row={
                "external_record_id": identity + ":cost",
                "period_start_utc": occurred,
                "period_end_utc": occurred + timedelta(seconds=1),
                "cost_usd": amount,
                "source_type": "agent_import",
                "cost_kind": "gateway_estimated",
                "model": model,
                "agent_name": agent,
                "is_demo": False,
            },
        )
    return 1 if stored else 0
