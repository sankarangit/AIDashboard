"""Usage and cost rows."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.deps import query_filters
from backend.services.aggregation import (
    attach_model_costs,
    classification,
    load_costs,
    load_usage,
    resolve_window,
    usage_payload,
)

router = APIRouter()


def _loaded(filters: dict):
    _start, _end, start_utc, end_utc = resolve_window(filters["timezone"], filters["start"], filters["end"])
    usage = load_usage(
        filters["db"],
        start_utc=start_utc,
        end_utc=end_utc,
        include_demo=filters["include_demo"],
        provider=filters["provider"],
        model=filters["model"],
        source=filters["source"],
        project=filters["project"],
        agent=filters["agent"],
    )
    costs = load_costs(
        filters["db"],
        start_utc=start_utc,
        end_utc=end_utc,
        include_demo=filters["include_demo"],
        provider=filters["provider"],
        model=filters["model"],
        source=filters["source"],
        project=filters["project"],
        agent=filters["agent"],
    )
    return usage, costs


@router.get("/usage")
def usage(filters: dict = Depends(query_filters)) -> dict:
    usage_rows, cost_rows = _loaded(filters)
    payload = usage_payload(usage_rows, filters["timezone"])
    payload["by_model"] = attach_model_costs(payload["by_model"], cost_rows)
    flags = [event.is_demo for event, _name in usage_rows]
    payload.update(classification(flags))
    return payload


@router.get("/costs")
def costs(filters: dict = Depends(query_filters)) -> dict:
    _usage_rows, cost_rows = _loaded(filters)
    rows = []
    for record, provider_name in cost_rows:
        badge = "Demo" if record.is_demo else {
            "provider_billed": "Provider-reported",
            "gateway_estimated": "Estimated",
            "manual": "Manual",
        }.get(record.cost_kind, "Manual")
        rows.append(
            {
                "provider": provider_name,
                "source_type": record.source_type,
                "cost_kind": record.cost_kind,
                "period_start_utc": record.period_start_utc.isoformat(),
                "period_end_utc": record.period_end_utc.isoformat(),
                "model": record.model,
                "project_id": record.project_id,
                "agent_name": record.agent_name,
                "cost_usd": float(record.cost_usd),
                "is_demo": record.is_demo,
                "badge": badge,
            }
        )
    flags = [record.is_demo for record, _name in cost_rows]
    return {"rows": rows, **classification(flags)}


@router.get("/agents")
def agents(filters: dict = Depends(query_filters)) -> dict:
    usage_rows, _costs = _loaded(filters)
    payload = usage_payload(usage_rows, filters["timezone"])
    flags = [event.is_demo for event, _name in usage_rows if event.agent_name]
    return {
        "agents": payload["by_agent"],
        "note": "Agent telemetry is imported or instrumented locally. It is not a consumer subscription cap.",
        **classification(flags),
    }
