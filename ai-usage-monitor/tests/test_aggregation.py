from datetime import UTC, date, datetime
from decimal import Decimal

from backend.services.aggregation import build_overview
from backend.services.ingest import insert_cost_record, insert_usage_event
from backend.services.timeutils import to_local_date


def _provider_id(db, name: str) -> int:
    from backend.models import Provider
    from sqlalchemy import select

    return db.scalar(select(Provider.id).where(Provider.name == name))


def test_singapore_day_crosses_utc_midnight():
    before = datetime(2026, 1, 1, 15, 59, tzinfo=UTC)
    boundary = datetime(2026, 1, 1, 16, 0, tzinfo=UTC)
    assert to_local_date(before, "Asia/Singapore") == date(2026, 1, 1)
    assert to_local_date(boundary, "Asia/Singapore") == date(2026, 1, 2)


def test_missing_counts_stay_null(db):
    provider_id = _provider_id(db, "openai")
    insert_usage_event(
        db,
        provider_id=provider_id,
        row={
            "external_event_id": "null-measure",
            "occurred_at_utc": datetime(2026, 4, 2, 4, 0, tzinfo=UTC),
            "source_type": "provider_usage",
            "model": "gpt-4.1",
            "is_demo": False,
        },
    )
    db.commit()
    payload = build_overview(
        db,
        tz_name="Asia/Singapore",
        start=date(2026, 4, 1),
        end=date(2026, 4, 3),
        include_demo=False,
        provider="openai",
    )
    kpis = payload["kpis"]
    assert kpis["input_tokens"] is None
    assert kpis["request_count"] is None
    assert kpis["avg_latency_ms"] is None
    assert kpis["error_rate"] is None
    assert kpis["billed_api_cost_usd"] is None


def test_billed_and_estimated_are_not_added(db):
    provider_id = _provider_id(db, "anthropic")
    start = datetime(2026, 5, 2, 4, 0, tzinfo=UTC)
    insert_cost_record(
        db,
        provider_id=provider_id,
        row={
            "external_record_id": "billed-1",
            "period_start_utc": start,
            "period_end_utc": datetime(2026, 5, 3, 4, 0, tzinfo=UTC),
            "cost_usd": Decimal("10"),
            "source_type": "provider_cost",
            "cost_kind": "provider_billed",
            "model": "claude-sonnet-4-5",
            "is_demo": False,
        },
    )
    insert_cost_record(
        db,
        provider_id=provider_id,
        row={
            "external_record_id": "est-1",
            "period_start_utc": start,
            "period_end_utc": start,
            "cost_usd": Decimal("4"),
            "source_type": "agent_import",
            "cost_kind": "gateway_estimated",
            "model": "claude-sonnet-4-5",
            "is_demo": False,
        },
    )
    db.commit()
    kpis = build_overview(
        db,
        tz_name="UTC",
        start=date(2026, 5, 1),
        end=date(2026, 5, 3),
        include_demo=False,
    )["kpis"]
    assert kpis["billed_api_cost_usd"] == 10
    assert kpis["gateway_estimated_cost_usd"] == 4
    assert kpis["combined_monthly_outlay_usd"] is None
    assert "total_cost_usd" not in kpis


def test_cache_tokens_stay_distinct(db):
    provider_id = _provider_id(db, "anthropic")
    insert_usage_event(
        db,
        provider_id=provider_id,
        row={
            "external_event_id": "cache-1",
            "occurred_at_utc": datetime(2026, 6, 2, 4, 0, tzinfo=UTC),
            "source_type": "provider_usage",
            "model": "claude-sonnet-4-5",
            "input_tokens": 100,
            "output_tokens": 40,
            "cache_read_tokens": 15,
            "cache_write_tokens": 5,
            "is_demo": False,
        },
    )
    db.commit()
    kpis = build_overview(
        db,
        tz_name="UTC",
        start=date(2026, 6, 1),
        end=date(2026, 6, 3),
        include_demo=False,
    )["kpis"]
    assert kpis["input_tokens"] == 100
    assert kpis["cache_read_tokens"] == 15
    assert kpis["cache_write_tokens"] == 5
    assert kpis["input_tokens"] != 100 + 15 + 5
