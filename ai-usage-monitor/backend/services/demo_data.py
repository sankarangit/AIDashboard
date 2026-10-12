"""Provider rows and the labeled synthetic dataset."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.connectors.manual_subscription import CONSUMER_PAGES, OFFICIAL_PAGES
from backend.models import Alert, Budget, CostRecord, Provider, Subscription, UsageEvent
from backend.services.ingest import insert_cost_record, insert_usage_event
from backend.services.settings_store import _put
from backend.services.timeutils import month_bounds

PROVIDER_NAMES = ("openai", "anthropic", "xai")
MODELS = {
    "openai": ("gpt-4.1", "gpt-4.1-mini"),
    "anthropic": ("claude-sonnet-4-5", "claude-haiku-4-5"),
    "xai": ("grok-4", "grok-3-mini"),
}
AGENTS = {"openai": "codex", "anthropic": "claude-code", "xai": "grok-bot"}
CACHE_RELATIONSHIP = {
    "openai": "subset_of_input",
    "anthropic": "additive",
    "xai": "unknown",
}


def ensure_providers(db: Session) -> None:
    for name in PROVIDER_NAMES:
        if db.scalar(select(Provider.id).where(Provider.name == name)) is None:
            db.add(Provider(name=name, enabled=True, connection_status="not_configured"))
    db.flush()


def seed_demo(db: Session) -> dict:
    ensure_providers(db)
    existing = db.scalar(select(func.count()).select_from(UsageEvent).where(UsageEvent.is_demo.is_(True)))
    if existing:
        _put(db, "demo_seed_version", "1")
        db.flush()
        return {"inserted_usage": 0, "already_present": True}
    providers = {row.name: row for row in db.scalars(select(Provider)).all()}
    end_day = datetime.now(UTC).date() - timedelta(days=1)
    start_day = end_day - timedelta(days=get_settings().demo_days - 1)
    usage_inserted = 0
    cost_inserted = 0
    day = start_day
    day_index = 0
    while day <= end_day:
        occurred = datetime(day.year, day.month, day.day, 4, 0, tzinfo=UTC)
        period_end = occurred + timedelta(days=1)
        for provider_index, name in enumerate(PROVIDER_NAMES):
            provider = providers[name]
            for model_index, model in enumerate(MODELS[name]):
                identity = f"demo:{name}:{model}:{day.isoformat()}"
                input_tokens = 1000 + day_index * 5 + model_index * 50
                output_tokens = 280 + day_index * 2
                cache_read = None if name == "xai" else 90 + model_index * 10
                cache_write = 25 if name == "anthropic" else None
                if insert_usage_event(
                    db,
                    provider_id=provider.id,
                    row={
                        "external_event_id": identity,
                        "occurred_at_utc": occurred,
                        "source_type": "provider_usage",
                        "model": model,
                        "project_id": "proj-demo",
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cache_read_tokens": cache_read,
                        "cache_write_tokens": cache_write,
                        "request_count": 3 + model_index,
                        "metadata": {"cache_relationship": CACHE_RELATIONSHIP[name], "synthetic": True},
                        "is_demo": True,
                    },
                ):
                    usage_inserted += 1
                if insert_cost_record(
                    db,
                    provider_id=provider.id,
                    row={
                        "external_record_id": identity + ":billed",
                        "period_start_utc": occurred,
                        "period_end_utc": period_end,
                        "cost_usd": Decimal("0.50"),
                        "source_type": "provider_cost",
                        "cost_kind": "provider_billed",
                        "model": model,
                        "project_id": "proj-demo",
                        "is_demo": True,
                    },
                ):
                    cost_inserted += 1
            agent = AGENTS[name]
            agent_model = MODELS[name][0]
            agent_id = f"demo:agent:{name}:{day.isoformat()}"
            if insert_usage_event(
                db,
                provider_id=provider.id,
                row={
                    "external_event_id": agent_id,
                    "occurred_at_utc": occurred + timedelta(hours=1),
                    "source_type": "agent_import",
                    "model": agent_model,
                    "agent_name": agent,
                    "project_id": "proj-demo",
                    "input_tokens": 400,
                    "output_tokens": 120,
                    "request_count": 1,
                    "latency_ms": 700 + (day_index % 5) * 40,
                    "success": day_index % 17 != 0,
                    "metadata": {"synthetic": True, "not_subscription_usage": True},
                    "is_demo": True,
                },
            ):
                usage_inserted += 1
            insert_cost_record(
                db,
                provider_id=provider.id,
                row={
                    "external_record_id": agent_id + ":estimated",
                    "period_start_utc": occurred + timedelta(hours=1),
                    "period_end_utc": occurred + timedelta(hours=1, seconds=1),
                    "cost_usd": Decimal("0.36"),
                    "source_type": "agent_import",
                    "cost_kind": "gateway_estimated",
                    "model": agent_model,
                    "agent_name": agent,
                    "project_id": "proj-demo",
                    "is_demo": True,
                },
            )
            cost_inserted += 1
        day += timedelta(days=1)
        day_index += 1
    unmatched_at = datetime(end_day.year, end_day.month, end_day.day, 6, 0, tzinfo=UTC)
    for name in PROVIDER_NAMES:
        insert_cost_record(
            db,
            provider_id=providers[name].id,
            row={
                "external_record_id": f"demo:unmatched:{name}:{end_day.isoformat()}",
                "period_start_utc": unmatched_at,
                "period_end_utc": unmatched_at + timedelta(seconds=1),
                "cost_usd": Decimal("0.15"),
                "source_type": "agent_import",
                "cost_kind": "gateway_estimated",
                "model": "unmatched-local-log",
                "agent_name": AGENTS[name],
                "is_demo": True,
            },
        )
        cost_inserted += 1
    _seed_subscriptions(db, providers)
    _seed_budgets(db, providers)
    _put(db, "demo_seed_version", "1")
    _put(db, "include_demo", "true")
    db.flush()
    return {
        "inserted_usage": usage_inserted,
        "inserted_costs": cost_inserted,
        "already_present": False,
        "days": get_settings().demo_days,
    }


def _seed_subscriptions(db: Session, providers: dict[str, Provider]) -> None:
    plans = {
        "openai": ("ChatGPT Plus", Decimal("20.00"), "USD"),
        "anthropic": ("Claude Pro", Decimal("20.00"), "USD"),
        "xai": ("SuperGrok", Decimal("49.00"), "SGD"),
    }
    verified = datetime.now(UTC)
    for name, (plan, fee, currency) in plans.items():
        db.add(
            Subscription(
                provider_id=providers[name].id,
                plan=plan,
                monthly_fee=fee,
                currency=currency,
                billing_day=11,
                renewal_date=(verified + timedelta(days=30)).date(),
                manual_allowance="Demo placeholder. Consumer plan balances are not read from an API.",
                manually_recorded_usage="Synthetic observation entered for the demo. Not a live remaining-message count.",
                last_verified_at=verified,
                usage_page_url=CONSUMER_PAGES[name],
                notes=(
                    "Manual demo record. This fee is a consumer subscription, not API usage. "
                    f"API billing for this vendor is separate: {OFFICIAL_PAGES[name]}"
                ),
                is_demo=True,
            )
        )


def _seed_budgets(db: Session, providers: dict[str, Provider]) -> None:
    start_utc, end_utc, _period = month_bounds("Asia/Singapore")
    totals = {}
    for name, provider in providers.items():
        amount = db.scalar(
            select(func.coalesce(func.sum(CostRecord.cost_usd), 0)).where(
                CostRecord.provider_id == provider.id,
                CostRecord.cost_kind == "provider_billed",
                CostRecord.is_demo.is_(True),
                CostRecord.period_start_utc >= start_utc,
                CostRecord.period_start_utc < end_utc,
            )
        )
        totals[name] = Decimal(str(amount or 0))
    combined = sum(totals.values(), Decimal("0"))
    db.add(
        Budget(
            provider_id=None,
            monthly_budget_usd=_budget_for(combined),
            threshold_percent=80,
            enabled=True,
            is_demo=True,
        )
    )
    for name, provider in providers.items():
        db.add(
            Budget(
                provider_id=provider.id,
                monthly_budget_usd=_budget_for(totals[name]),
                threshold_percent=80,
                enabled=True,
                is_demo=True,
            )
        )


def _budget_for(spend: Decimal) -> Decimal:
    if spend <= 0:
        return Decimal("40.00")
    return (spend / Decimal("0.62")).quantize(Decimal("0.01"))


def delete_demo(db: Session) -> dict:
    demo_budgets = list(db.scalars(select(Budget.id).where(Budget.is_demo.is_(True))).all())
    if demo_budgets:
        db.execute(delete(Alert).where(Alert.budget_id.in_(demo_budgets)))
    removed_budgets = db.execute(delete(Budget).where(Budget.is_demo.is_(True))).rowcount
    removed_subs = db.execute(delete(Subscription).where(Subscription.is_demo.is_(True))).rowcount
    removed_costs = db.execute(delete(CostRecord).where(CostRecord.is_demo.is_(True))).rowcount
    removed_usage = db.execute(delete(UsageEvent).where(UsageEvent.is_demo.is_(True))).rowcount
    _put(db, "demo_seed_version", "0")
    _put(db, "include_demo", "false")
    db.flush()
    return {
        "usage_events": removed_usage or 0,
        "cost_records": removed_costs or 0,
        "subscriptions": removed_subs or 0,
        "budgets": removed_budgets or 0,
    }
