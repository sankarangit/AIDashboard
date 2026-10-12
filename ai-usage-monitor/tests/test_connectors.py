from datetime import UTC, datetime

import httpx
from backend.connectors.anthropic_usage import _parse_costs as parse_anthropic_costs
from backend.connectors.anthropic_usage import _parse_usage as parse_anthropic_usage
from backend.connectors.base import ConfigCheck, Page
from backend.connectors.openai_usage import OpenAIUsageConnector, _parse_costs, _parse_usage
from backend.connectors.xai_usage import XAIUsageConnector, _split
from backend.services.ingest import insert_cost_record, insert_usage_event
from backend.services.sync import sync_provider


def test_missing_openai_key_makes_no_request(monkeypatch):
    monkeypatch.delenv("OPENAI_ADMIN_KEY", raising=False)
    from backend.config import reset_settings

    reset_settings()
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"data": []})

    connector = OpenAIUsageConnector(client=httpx.Client(transport=httpx.MockTransport(handler)), sleeper=lambda _s: None)
    result = connector.test_connection()
    assert result.status == "not_configured"
    assert calls["n"] == 0
    reset_settings()


def test_openai_permission_and_rate_limit(monkeypatch):
    monkeypatch.setenv("OPENAI_ADMIN_KEY", "present-admin-key")
    from backend.config import reset_settings

    reset_settings()

    def denied(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "secret-body-should-not-leak"})

    denied_client = httpx.Client(transport=httpx.MockTransport(denied))
    denied_result = OpenAIUsageConnector(client=denied_client, sleeper=lambda _s: None).test_connection()
    assert denied_result.status == "insufficient_permissions"
    assert "secret-body-should-not-leak" not in denied_result.message

    def limited(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "0"})

    limited_client = httpx.Client(transport=httpx.MockTransport(limited))
    limited_result = OpenAIUsageConnector(client=limited_client, sleeper=lambda _s: None).test_connection()
    assert limited_result.status == "rate_limited"
    reset_settings()


def test_openai_parsers_do_not_merge_cost_and_usage():
    usage = _parse_usage(
        {
            "data": [
                {
                    "start_time": 1767225600,
                    "end_time": 1767312000,
                    "results": [
                        {
                            "input_tokens": 1000,
                            "output_tokens": 250,
                            "input_cached_tokens": 100,
                            "num_model_requests": 4,
                            "model": "gpt-4.1",
                            "project_id": "proj_a",
                        }
                    ],
                }
            ],
            "next_page": None,
        }
    )
    costs = _parse_costs(
        {
            "data": [
                {
                    "start_time": 1767225600,
                    "end_time": 1767312000,
                    "results": [
                        {
                            "amount": {"currency": "usd", "value": 2.5},
                            "line_item": "gpt-4.1, input",
                            "project_id": "proj_a",
                        }
                    ],
                }
            ]
        }
    )
    assert usage.records[0].input_tokens == 1000
    assert usage.records[0].cache_read_tokens == 100
    assert costs.records[0].cost_usd == 2.5
    assert costs.records[0].cost_kind == "provider_billed"
    assert usage.records[0].external_event_id != costs.records[0].external_record_id


def test_anthropic_cost_uses_minor_units_and_separate_cache():
    usage = parse_anthropic_usage(
        {
            "data": [
                {
                    "starting_at": "2026-01-01T00:00:00Z",
                    "ending_at": "2026-01-02T00:00:00Z",
                    "results": [
                        {
                            "uncached_input_tokens": 10,
                            "output_tokens": 4,
                            "cache_read_input_tokens": 3,
                            "cache_creation": {"ephemeral_5m_input_tokens": 2, "ephemeral_1h_input_tokens": 1},
                            "model": "claude-sonnet-4-5",
                        }
                    ],
                }
            ]
        }
    )
    costs = parse_anthropic_costs(
        {
            "data": [
                {
                    "starting_at": "2026-01-01T00:00:00Z",
                    "ending_at": "2026-01-02T00:00:00Z",
                    "results": [{"currency": "USD", "amount": "150", "model": "claude-sonnet-4-5"}],
                }
            ]
        }
    )
    assert usage.records[0].input_tokens == 10
    assert usage.records[0].cache_read_tokens == 3
    assert usage.records[0].cache_write_tokens == 3
    assert costs.records[0].cost_usd == 1.5


def test_xai_unrecognized_payload_stores_nothing():
    usage, costs = _split({"unexpected": True})
    assert usage.unrecognized
    assert costs.records == []
    parsed_usage, parsed_costs = _split(
        {
            "data": [
                {
                    "model": "grok-4",
                    "start_time": "2026-09-01T00:00:00Z",
                    "end_time": "2026-09-02T00:00:00Z",
                    "input_tokens": 100,
                    "output_tokens": 40,
                    "cost_usd": 0.25,
                }
            ]
        }
    )
    assert parsed_usage.records[0].input_tokens == 100
    assert parsed_costs.records[0].cost_usd == 0.25
    assert parsed_costs.records[0].cost_kind == "provider_billed"


def test_sync_is_idempotent(db):
    class Fake:
        name = "openai"

        def validate_config(self):
            return ConfigCheck(True, "configured", "ok")

        def fetch_usage(self, _start, _end, cursor=None):
            from backend.connectors.base import UsageDraft

            return Page(
                records=[
                    UsageDraft(
                        external_event_id="live-1",
                        occurred_at_utc=datetime(2026, 8, 2, tzinfo=UTC),
                        source_type="provider_usage",
                        model="gpt-4.1",
                        input_tokens=10,
                        output_tokens=2,
                    )
                ]
            )

        def fetch_costs(self, _start, _end, cursor=None):
            from decimal import Decimal

            from backend.connectors.base import CostDraft

            return Page(
                records=[
                    CostDraft(
                        external_record_id="live-cost-1",
                        period_start_utc=datetime(2026, 8, 2, tzinfo=UTC),
                        period_end_utc=datetime(2026, 8, 3, tzinfo=UTC),
                        cost_usd=Decimal("1.25"),
                        source_type="provider_cost",
                        cost_kind="provider_billed",
                        model="gpt-4.1, input",
                    )
                ]
            )

        def capabilities(self):
            return {}

    first = sync_provider(db, "openai", Fake())
    second = sync_provider(db, "openai", Fake())
    db.commit()
    assert first["inserted"] == 2
    assert second["inserted"] == 0
    from backend.models import CostRecord
    from sqlalchemy import func, select

    total = db.scalar(select(func.sum(CostRecord.cost_usd)))
    assert float(total) == 1.25


def test_xai_without_management_key_is_not_configured(monkeypatch):
    monkeypatch.delenv("XAI_MANAGEMENT_API_KEY", raising=False)
    monkeypatch.delenv("XAI_TEAM_ID", raising=False)
    from backend.config import reset_settings

    reset_settings()
    assert XAIUsageConnector().validate_config().status == "not_configured"
    reset_settings()


def test_ingest_duplicate_identity(db):
    from backend.models import Provider, UsageEvent
    from sqlalchemy import func, select

    provider_id = db.scalar(select(Provider.id).where(Provider.name == "xai"))
    row = {
        "external_event_id": "same",
        "occurred_at_utc": datetime(2026, 8, 2, tzinfo=UTC),
        "source_type": "provider_usage",
        "input_tokens": 5,
        "is_demo": False,
    }
    assert insert_usage_event(db, provider_id=provider_id, row=row) is True
    assert insert_usage_event(db, provider_id=provider_id, row=row) is False
    assert insert_cost_record(
        db,
        provider_id=provider_id,
        row={
            "external_record_id": "same-cost",
            "period_start_utc": datetime(2026, 8, 2, tzinfo=UTC),
            "period_end_utc": datetime(2026, 8, 3, tzinfo=UTC),
            "cost_usd": 3,
            "source_type": "provider_cost",
            "cost_kind": "provider_billed",
            "is_demo": False,
        },
    )
    db.commit()
    assert db.scalar(select(func.count()).select_from(UsageEvent)) == 1
