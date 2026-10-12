from datetime import UTC, date, datetime
from decimal import Decimal

from backend.services.ingest import insert_cost_record
from backend.services.reconciliation import build_reconciliation


def _provider_id(db, name: str) -> int:
    from backend.models import Provider
    from sqlalchemy import select

    return db.scalar(select(Provider.id).where(Provider.name == name))


def test_reconciliation_variance_and_unmatched(db):
    provider_id = _provider_id(db, "openai")
    start = datetime(2026, 7, 2, 4, 0, tzinfo=UTC)
    insert_cost_record(
        db,
        provider_id=provider_id,
        row={
            "external_record_id": "bill",
            "period_start_utc": start,
            "period_end_utc": datetime(2026, 7, 3, 4, 0, tzinfo=UTC),
            "cost_usd": Decimal("10"),
            "source_type": "provider_cost",
            "cost_kind": "provider_billed",
            "model": "gpt-4.1",
            "is_demo": False,
        },
    )
    insert_cost_record(
        db,
        provider_id=provider_id,
        row={
            "external_record_id": "est-match",
            "period_start_utc": start,
            "period_end_utc": start,
            "cost_usd": Decimal("8"),
            "source_type": "agent_import",
            "cost_kind": "gateway_estimated",
            "model": "gpt-4.1",
            "is_demo": False,
        },
    )
    insert_cost_record(
        db,
        provider_id=provider_id,
        row={
            "external_record_id": "est-miss",
            "period_start_utc": start,
            "period_end_utc": start,
            "cost_usd": Decimal("1.5"),
            "source_type": "agent_import",
            "cost_kind": "gateway_estimated",
            "model": "unmatched-local-log",
            "is_demo": False,
        },
    )
    db.commit()
    payload = build_reconciliation(
        db,
        tz_name="UTC",
        start=date(2026, 7, 1),
        end=date(2026, 7, 3),
        include_demo=False,
        provider="openai",
    )
    openai = next(row for row in payload["providers"] if row["provider"] == "openai")
    assert openai["billed_api_cost_usd"] == 10
    assert openai["gateway_estimated_cost_usd"] == 9.5
    assert openai["variance_usd"] == -0.5
    assert openai["unmatched_estimated_count"] == 1
    assert openai["unmatched_estimated_cost_usd"] == 1.5
