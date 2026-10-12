"""Cost and token aggregation.

Provider-billed amounts and gateway estimates are returned as separate fields.
They are never added together. Missing measurements stay null.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Budget, CostRecord, Provider, Subscription, UsageEvent
from backend.services.timeutils import (
    as_utc,
    default_range,
    inclusive_range_bounds,
    month_bounds,
    to_local_date,
)

PROVIDER_ORDER = ("openai", "anthropic", "xai")


def money(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(Decimal(value).quantize(Decimal("0.000001")))


def _decimal_sum(values: list) -> Decimal | None:
    present = [Decimal(str(item)) for item in values if item is not None]
    if not present:
        return None
    return sum(present, Decimal("0"))


def _int_sum(values: list) -> tuple[int | None, bool]:
    present = [int(item) for item in values if item is not None]
    if not present:
        return None, False
    return sum(present), len(present) != len(values)


def _avg(values: list) -> float | None:
    present = [float(item) for item in values if item is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _error_rate(values: list) -> float | None:
    present = [item for item in values if item is not None]
    if not present:
        return None
    failures = sum(1 for item in present if item is False)
    return failures / len(present)


def provider_map(db: Session) -> dict[str, Provider]:
    rows = db.scalars(select(Provider)).all()
    return {row.name: row for row in rows}


def resolve_window(
    tz_name: str,
    start: date | None,
    end: date | None,
) -> tuple[date, date, datetime, datetime]:
    if start is None or end is None:
        default_start, default_end = default_range(tz_name, 30)
        start = start or default_start
        end = end or default_end
    start_utc, end_utc = inclusive_range_bounds(start, end, tz_name)
    return start, end, start_utc, end_utc


def load_usage(
    db: Session,
    *,
    start_utc: datetime,
    end_utc: datetime,
    include_demo: bool,
    provider: str | None = None,
    model: str | None = None,
    source: str | None = None,
    project: str | None = None,
    agent: str | None = None,
) -> list[tuple[UsageEvent, str]]:
    stmt = (
        select(UsageEvent, Provider.name)
        .join(Provider, Provider.id == UsageEvent.provider_id)
        .where(UsageEvent.occurred_at_utc >= start_utc, UsageEvent.occurred_at_utc < end_utc)
    )
    if not include_demo:
        stmt = stmt.where(UsageEvent.is_demo.is_(False))
    if provider:
        stmt = stmt.where(Provider.name == provider)
    if model:
        stmt = stmt.where(UsageEvent.model == model)
    if source:
        stmt = stmt.where(UsageEvent.source_type == source)
    if project:
        stmt = stmt.where(UsageEvent.project_id == project)
    if agent:
        stmt = stmt.where(UsageEvent.agent_name == agent)
    return list(db.execute(stmt).all())


def load_costs(
    db: Session,
    *,
    start_utc: datetime,
    end_utc: datetime,
    include_demo: bool,
    provider: str | None = None,
    model: str | None = None,
    source: str | None = None,
    project: str | None = None,
    agent: str | None = None,
    cost_kind: str | None = None,
) -> list[tuple[CostRecord, str]]:
    stmt = (
        select(CostRecord, Provider.name)
        .join(Provider, Provider.id == CostRecord.provider_id)
        .where(CostRecord.period_start_utc >= start_utc, CostRecord.period_start_utc < end_utc)
    )
    if not include_demo:
        stmt = stmt.where(CostRecord.is_demo.is_(False))
    if provider:
        stmt = stmt.where(Provider.name == provider)
    if model:
        stmt = stmt.where(CostRecord.model == model)
    if source:
        stmt = stmt.where(CostRecord.source_type == source)
    if project:
        stmt = stmt.where(CostRecord.project_id == project)
    if agent:
        stmt = stmt.where(CostRecord.agent_name == agent)
    if cost_kind:
        stmt = stmt.where(CostRecord.cost_kind == cost_kind)
    return list(db.execute(stmt).all())


def classification(demo_flags: list[bool]) -> dict:
    includes_demo = any(demo_flags)
    has_live = any(not flag for flag in demo_flags)
    if not demo_flags:
        label = "empty"
    elif includes_demo and not has_live:
        label = "demo"
    elif includes_demo and has_live:
        label = "mixed"
    else:
        label = "live"
    return {
        "includes_demo_data": includes_demo,
        "has_live_data": has_live,
        "data_classification": label,
    }


def _badge(is_demo: bool, cost_kind: str | None = None) -> str:
    if is_demo:
        return "Demo"
    if cost_kind == "provider_billed":
        return "Provider-reported"
    if cost_kind == "gateway_estimated":
        return "Estimated"
    if cost_kind == "manual":
        return "Manual"
    return "Provider-reported"


def usage_payload(rows: list[tuple[UsageEvent, str]], tz_name: str) -> dict:
    serialized = []
    by_day: dict[date, dict] = defaultdict(
        lambda: {
            "input_tokens": [],
            "output_tokens": [],
            "cache_read_tokens": [],
            "cache_write_tokens": [],
            "request_count": [],
        }
    )
    by_model: dict[tuple[str, str], dict] = defaultdict(lambda: defaultdict(list))
    by_agent: dict[str, dict] = defaultdict(lambda: defaultdict(list))
    for event, provider_name in rows:
        local_day = to_local_date(event.occurred_at_utc, tz_name)
        serialized.append(
            {
                "provider": provider_name,
                "source_type": event.source_type,
                "occurred_at_utc": event.occurred_at_utc.isoformat(),
                "local_date": local_day.isoformat(),
                "model": event.model,
                "project_id": event.project_id,
                "agent_name": event.agent_name,
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "cache_read_tokens": event.cache_read_tokens,
                "cache_write_tokens": event.cache_write_tokens,
                "request_count": event.request_count,
                "latency_ms": event.latency_ms,
                "success": event.success,
                "is_demo": event.is_demo,
                "badge": _badge(event.is_demo),
            }
        )
        bucket = by_day[local_day]
        bucket["input_tokens"].append(event.input_tokens)
        bucket["output_tokens"].append(event.output_tokens)
        bucket["cache_read_tokens"].append(event.cache_read_tokens)
        bucket["cache_write_tokens"].append(event.cache_write_tokens)
        bucket["request_count"].append(event.request_count)
        model_key = (provider_name, event.model or "unspecified")
        for field in (
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "request_count",
        ):
            by_model[model_key][field].append(getattr(event, field))
        by_model[model_key]["is_demo"].append(event.is_demo)
        if event.agent_name:
            for field in ("input_tokens", "output_tokens", "request_count", "latency_ms", "success"):
                by_agent[event.agent_name][field].append(getattr(event, field))
            by_agent[event.agent_name]["provider"].append(provider_name)
            by_agent[event.agent_name]["is_demo"].append(event.is_demo)

    input_sum, input_partial = _int_sum([row[0].input_tokens for row in rows])
    output_sum, output_partial = _int_sum([row[0].output_tokens for row in rows])
    cache_read, cache_read_partial = _int_sum([row[0].cache_read_tokens for row in rows])
    cache_write, cache_write_partial = _int_sum([row[0].cache_write_tokens for row in rows])
    requests, requests_partial = _int_sum([row[0].request_count for row in rows])
    summary = {
        "input_tokens": input_sum,
        "input_tokens_partial": input_partial,
        "output_tokens": output_sum,
        "output_tokens_partial": output_partial,
        "cache_read_tokens": cache_read,
        "cache_read_tokens_partial": cache_read_partial,
        "cache_write_tokens": cache_write,
        "cache_write_tokens_partial": cache_write_partial,
        "request_count": requests,
        "request_count_partial": requests_partial,
        "avg_latency_ms": _avg([row[0].latency_ms for row in rows]),
        "error_rate": _error_rate([row[0].success for row in rows]),
        "event_count": len(rows),
    }
    daily = []
    for day in sorted(by_day):
        item = by_day[day]
        daily.append(
            {
                "date": day.isoformat(),
                "input_tokens": _int_sum(item["input_tokens"])[0],
                "output_tokens": _int_sum(item["output_tokens"])[0],
                "cache_read_tokens": _int_sum(item["cache_read_tokens"])[0],
                "cache_write_tokens": _int_sum(item["cache_write_tokens"])[0],
                "request_count": _int_sum(item["request_count"])[0],
            }
        )
    models = []
    for (provider_name, model_name), item in sorted(by_model.items()):
        models.append(
            {
                "provider": provider_name,
                "model": model_name,
                "input_tokens": _int_sum(item["input_tokens"])[0],
                "output_tokens": _int_sum(item["output_tokens"])[0],
                "cache_read_tokens": _int_sum(item["cache_read_tokens"])[0],
                "cache_write_tokens": _int_sum(item["cache_write_tokens"])[0],
                "request_count": _int_sum(item["request_count"])[0],
                "badge": "Demo" if any(item["is_demo"]) else "Provider-reported",
            }
        )
    agents = []
    for name, item in sorted(by_agent.items()):
        agents.append(
            {
                "agent": name,
                "providers": sorted(set(item["provider"])),
                "input_tokens": _int_sum(item["input_tokens"])[0],
                "output_tokens": _int_sum(item["output_tokens"])[0],
                "request_count": _int_sum(item["request_count"])[0],
                "avg_latency_ms": _avg(item["latency_ms"]),
                "error_rate": _error_rate(item["success"]),
                "badge": "Demo" if any(item["is_demo"]) else "Estimated",
            }
        )
    return {"rows": serialized, "daily": daily, "by_model": models, "by_agent": agents, "summary": summary}


def _series(costs: list[tuple[CostRecord, str]], tz_name: str) -> list[dict]:
    buckets: dict[date, list] = defaultdict(list)
    for record, _name in costs:
        buckets[to_local_date(record.period_start_utc, tz_name)].append(record.cost_usd)
    series = []
    running = Decimal("0")
    has_any = False
    for day in sorted(buckets):
        total = _decimal_sum(buckets[day])
        if total is None:
            series.append({"date": day.isoformat(), "cost_usd": None, "cumulative_usd": None})
            continue
        has_any = True
        running += total
        series.append(
            {
                "date": day.isoformat(),
                "cost_usd": money(total),
                "cumulative_usd": money(running) if has_any else None,
            }
        )
    return series


def reconcile(costs: list[tuple[CostRecord, str]], tz_name: str) -> dict:
    billed = [row for row in costs if row[0].cost_kind == "provider_billed"]
    estimated = [row for row in costs if row[0].cost_kind == "gateway_estimated"]
    manual = [row for row in costs if row[0].cost_kind == "manual"]
    billed_keys = {
        (name, record.model, to_local_date(record.period_start_utc, tz_name).isoformat())
        for record, name in billed
    }
    by_provider: dict[str, dict] = {}
    for name in PROVIDER_ORDER:
        provider_billed = [record for record, provider_name in billed if provider_name == name]
        provider_estimated = [record for record, provider_name in estimated if provider_name == name]
        billed_total = _decimal_sum([record.cost_usd for record in provider_billed])
        estimated_total = _decimal_sum([record.cost_usd for record in provider_estimated])
        unmatched = []
        for record in provider_estimated:
            key = (name, record.model, to_local_date(record.period_start_utc, tz_name).isoformat())
            if key not in billed_keys:
                unmatched.append(record)
        variance = None
        variance_pct = None
        if billed_total is not None and estimated_total is not None:
            variance = estimated_total - billed_total
            if billed_total != 0:
                variance_pct = float((variance / billed_total) * Decimal("100"))
        by_provider[name] = {
            "provider": name,
            "billed_api_cost_usd": money(billed_total),
            "gateway_estimated_cost_usd": money(estimated_total),
            "variance_usd": money(variance),
            "variance_percent": None if variance_pct is None else round(variance_pct, 4),
            "billed_record_count": len(provider_billed),
            "estimated_record_count": len(provider_estimated),
            "unmatched_estimated_cost_usd": money(_decimal_sum([record.cost_usd for record in unmatched])),
            "unmatched_estimated_count": len(unmatched),
        }
    return {
        "providers": [by_provider[name] for name in PROVIDER_ORDER],
        "note": (
            "Provider-billed cost and gateway-estimated cost are compared, not added. "
            "A variance is the estimate minus the billed amount for the same window."
        ),
        "manual_cost_usd": money(_decimal_sum([record.cost_usd for record, _name in manual])),
    }


def subscription_summary(db: Session, include_demo: bool, fx_rates: dict[str, Decimal]) -> dict:
    stmt = select(Subscription, Provider.name).join(Provider, Provider.id == Subscription.provider_id)
    if not include_demo:
        stmt = stmt.where(Subscription.is_demo.is_(False))
    rows = db.execute(stmt).all()
    usd = Decimal("0")
    saw_usd = False
    other = []
    converted = Decimal("0")
    conversion_used = False
    serialized = []
    for item, provider_name in rows:
        currency = item.currency.upper()
        serialized.append(
            {
                "id": item.id,
                "provider": provider_name,
                "plan": item.plan,
                "monthly_fee": money(item.monthly_fee),
                "currency": currency,
                "billing_day": item.billing_day,
                "renewal_date": item.renewal_date.isoformat() if item.renewal_date else None,
                "manual_allowance": item.manual_allowance,
                "manually_recorded_usage": item.manually_recorded_usage,
                "last_verified_at": item.last_verified_at.isoformat() if item.last_verified_at else None,
                "usage_page_url": item.usage_page_url,
                "notes": item.notes,
                "is_demo": item.is_demo,
                "badge": "Demo" if item.is_demo else "Manual",
            }
        )
        if currency == "USD":
            usd += Decimal(item.monthly_fee)
            saw_usd = True
        else:
            other.append({"currency": currency, "amount": money(item.monthly_fee), "provider": provider_name})
            rate = fx_rates.get(currency)
            if rate is not None:
                converted += Decimal(item.monthly_fee) * rate
                conversion_used = True
    combined = None
    note = "Subscription fees are separate from variable API spend."
    if conversion_used and saw_usd:
        combined = usd + converted
        note = "Combined outlay uses the FX rates stored in settings. It is not a provider invoice."
    elif other:
        note = (
            "Non-USD subscription fees are listed separately and are not added to USD API spend. "
            "Set FX rates in settings to show a labeled combined outlay."
        )
    return {
        "records": serialized,
        "subscription_fees_usd": money(usd) if saw_usd else None,
        "subscription_fees_other": other,
        "combined_subscription_usd": money(combined) if combined is not None else None,
        "note": note,
    }


def attach_model_costs(models: list[dict], costs: list[tuple[CostRecord, str]]) -> list[dict]:
    """Attach billed cost only when the cost row names the same model.

    Unallocated provider buckets stay out of the per-model rate so token totals
    are not turned into an invented price.
    """
    billed: dict[tuple[str, str], list] = defaultdict(list)
    for record, provider_name in costs:
        if record.cost_kind != "provider_billed" or not record.model:
            continue
        billed[(provider_name, record.model)].append(record.cost_usd)
    enriched = []
    for row in models:
        total = _decimal_sum(billed.get((row["provider"], row["model"]), []))
        token_parts = [
            row["input_tokens"],
            row["output_tokens"],
            row["cache_read_tokens"],
            row["cache_write_tokens"],
        ]
        present_tokens = [part for part in token_parts if part is not None]
        denominator = sum(present_tokens) if present_tokens else None
        per_million = None
        if total is not None and denominator:
            per_million = float((total / Decimal(denominator)) * Decimal("1000000"))
        enriched.append(
            {
                **row,
                "billed_api_cost_usd": money(total),
                "cost_per_million_tokens_usd": None if per_million is None else round(per_million, 6),
                "cost_note": (
                    "Rate uses provider-billed cost divided by reported tokens for this model."
                    if per_million is not None
                    else "N/A — no provider-billed amount is stored for this model."
                ),
            }
        )
    return enriched


def budget_utilization(
    db: Session,
    *,
    include_demo: bool,
    tz_name: str,
) -> dict:
    start_utc, end_utc, period = month_bounds(tz_name)
    costs = load_costs(
        db,
        start_utc=start_utc,
        end_utc=end_utc,
        include_demo=include_demo,
        cost_kind="provider_billed",
    )
    spend = _decimal_sum([record.cost_usd for record, _name in costs])
    stmt = select(Budget, Provider.name).join(Provider, Provider.id == Budget.provider_id, isouter=True)
    if not include_demo:
        stmt = stmt.where(Budget.is_demo.is_(False))
    budgets = []
    for budget, provider_name in db.execute(stmt).all():
        if budget.provider_id is None:
            scoped = spend
        else:
            scoped = _decimal_sum(
                [
                    record.cost_usd
                    for record, name in costs
                    if name == provider_name
                ]
            )
        ratio = None
        if scoped is not None and budget.monthly_budget_usd:
            ratio = float(scoped / Decimal(budget.monthly_budget_usd))
        budgets.append(
            {
                "id": budget.id,
                "provider": provider_name,
                "monthly_budget_usd": money(budget.monthly_budget_usd),
                "threshold_percent": budget.threshold_percent,
                "enabled": budget.enabled,
                "is_demo": budget.is_demo,
                "spend_usd": money(scoped),
                "utilization": ratio,
                "period": period,
            }
        )
    combined = next((item for item in budgets if item["provider"] is None and item["enabled"]), None)
    return {
        "period": period,
        "month_billed_usd": money(spend),
        "budgets": budgets,
        "combined_utilization": None if combined is None else combined["utilization"],
    }


def build_overview(
    db: Session,
    *,
    tz_name: str,
    start: date | None,
    end: date | None,
    include_demo: bool,
    provider: str | None = None,
    model: str | None = None,
    source: str | None = None,
    project: str | None = None,
    agent: str | None = None,
    fx_rates: dict[str, Decimal] | None = None,
) -> dict:
    start_day, end_day, start_utc, end_utc = resolve_window(tz_name, start, end)
    usage_rows = load_usage(
        db,
        start_utc=start_utc,
        end_utc=end_utc,
        include_demo=include_demo,
        provider=provider,
        model=model,
        source=source,
        project=project,
        agent=agent,
    )
    cost_rows = load_costs(
        db,
        start_utc=start_utc,
        end_utc=end_utc,
        include_demo=include_demo,
        provider=provider,
        model=model,
        source=source,
        project=project,
        agent=agent,
    )
    usage = usage_payload(usage_rows, tz_name)
    billed = [row for row in cost_rows if row[0].cost_kind == "provider_billed"]
    estimated = [row for row in cost_rows if row[0].cost_kind == "gateway_estimated"]
    subs = subscription_summary(db, include_demo, fx_rates or {})
    util = budget_utilization(db, include_demo=include_demo, tz_name=tz_name)
    flags = [event.is_demo for event, _name in usage_rows] + [record.is_demo for record, _name in cost_rows]
    by_provider = []
    for name in PROVIDER_ORDER:
        if provider and provider != name:
            continue
        name_billed = _decimal_sum([record.cost_usd for record, pname in billed if pname == name])
        name_estimated = _decimal_sum(
            [record.cost_usd for record, pname in estimated if pname == name]
        )
        name_usage = [event for event, pname in usage_rows if pname == name]
        by_provider.append(
            {
                "provider": name,
                "billed_api_cost_usd": money(name_billed),
                "gateway_estimated_cost_usd": money(name_estimated),
                "input_tokens": _int_sum([event.input_tokens for event in name_usage])[0],
                "output_tokens": _int_sum([event.output_tokens for event in name_usage])[0],
                "cache_read_tokens": _int_sum([event.cache_read_tokens for event in name_usage])[0],
                "cache_write_tokens": _int_sum([event.cache_write_tokens for event in name_usage])[0],
                "request_count": _int_sum([event.request_count for event in name_usage])[0],
                "coverage": {
                    "provider_billed": name_billed is not None,
                    "provider_usage": bool(name_usage),
                    "gateway_estimated": name_estimated is not None,
                },
            }
        )
    sources = sorted({event.source_type for event, _name in usage_rows} | {record.source_type for record, _name in cost_rows})
    last_sync_values = [as_utc(item.last_sync_at) for item in provider_map(db).values() if item.last_sync_at]
    last_sync = max(last_sync_values).isoformat() if last_sync_values else None
    summary = usage["summary"]
    return {
        **classification(flags),
        "range": {
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
            "timezone": tz_name,
        },
        "kpis": {
            "billed_api_cost_usd": money(_decimal_sum([record.cost_usd for record, _n in billed])),
            "gateway_estimated_cost_usd": money(
                _decimal_sum([record.cost_usd for record, _n in estimated])
            ),
            "subscription_fees_usd": subs["subscription_fees_usd"],
            "subscription_fees_other": subs["subscription_fees_other"],
            "combined_monthly_outlay_usd": None,
            "input_tokens": summary["input_tokens"],
            "output_tokens": summary["output_tokens"],
            "cache_read_tokens": summary["cache_read_tokens"],
            "cache_write_tokens": summary["cache_write_tokens"],
            "request_count": summary["request_count"],
            "request_count_partial": summary["request_count_partial"],
            "avg_latency_ms": summary["avg_latency_ms"],
            "error_rate": summary["error_rate"],
            "budget_utilization": util["combined_utilization"],
            "last_sync_at": last_sync,
            "billed_record_count": len(billed),
            "estimated_record_count": len(estimated),
        },
        "daily_billed": _series(billed, tz_name),
        "daily_estimated": _series(estimated, tz_name),
        "by_provider": by_provider,
        "top_models": attach_model_costs(usage["by_model"], cost_rows)[:12],
        "by_agent": usage["by_agent"],
        "source_coverage": sources,
        "accounting_note": (
            "Billed API cost, gateway-estimated cost, and subscription fees are separate. "
            "They are not summed into one spend figure."
        ),
        "cache_note": (
            "Cache tokens are shown separately from input tokens. "
            "OpenAI cached input is a subset of input tokens, not additional usage."
        ),
    }
