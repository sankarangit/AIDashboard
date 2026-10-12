"""Optional LiteLLM spend-log import.

Rows are gateway estimates. They are never stored as provider-billed cost.
https://docs.litellm.ai/docs/proxy/cost_tracking
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from backend.config import get_settings
from backend.connectors.base import (
    ConfigCheck,
    ConnectionResult,
    ConnectorError,
    CostDraft,
    HttpConnector,
    Page,
    UsageDraft,
)
from backend.services.ingest import stable_id
from backend.services.timeutils import parse_timestamp

_PROVIDER_ALIASES = {
    "openai": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "xai": "xai",
    "grok": "xai",
}


class LiteLLMImportConnector(HttpConnector):
    name = "litellm"

    def validate_config(self) -> ConfigCheck:
        settings = get_settings()
        if not settings.litellm_base_url.strip() or not settings.litellm_api_key.strip():
            return ConfigCheck(
                False,
                "not_configured",
                "LiteLLM import is optional. Set LITELLM_BASE_URL and LITELLM_API_KEY only if this app should read an existing proxy's spend logs.",
            )
        return ConfigCheck(True, "configured", "LiteLLM spend-log settings are present and have not been verified yet.")

    def capabilities(self) -> dict:
        return {
            "tokens": True,
            "costs": True,
            "requests": True,
            "latency": True,
            "cache_tokens": False,
            "required_roles": ["LiteLLM proxy key with spend-log read access"],
            "cost_kind": "gateway_estimated",
            "consumer_subscription": False,
        }

    def test_connection(self) -> ConnectionResult:
        check = self.validate_config()
        if not check.ok:
            return ConnectionResult(check.status, check.message)
        end = datetime.now().astimezone()
        start = end.replace(hour=0, minute=0, second=0, microsecond=0)
        try:
            page = self.fetch_usage(start, end)
        except ConnectorError as exc:
            return ConnectionResult(exc.status, exc.message)
        if page.unrecognized:
            return ConnectionResult("failed", page.notice or "LiteLLM response was not a spend log.")
        return ConnectionResult("connected", "LiteLLM spend logs responded. Costs from this source stay estimated.")

    def fetch_usage(self, start_at: datetime, end_at: datetime, cursor: str | None = None) -> Page:
        payload = self._logs(start_at, end_at, cursor)
        return _split(payload)[0]

    def fetch_costs(self, start_at: datetime, end_at: datetime, cursor: str | None = None) -> Page:
        payload = self._logs(start_at, end_at, cursor)
        return _split(payload)[1]

    def _logs(self, start_at: datetime, end_at: datetime, cursor: str | None) -> dict | list:
        check = self.validate_config()
        if not check.ok:
            raise ConnectorError(check.status, check.message)
        base = get_settings().litellm_base_url.strip().rstrip("/")
        params = {
            "start_date": start_at.date().isoformat(),
            "end_date": end_at.date().isoformat(),
        }
        if cursor:
            params["page"] = cursor
        cache_key = (params["start_date"], params["end_date"], cursor)
        cache = getattr(self, "_page_cache", {})
        if cache_key in cache:
            return cache[cache_key]
        response = self.request(
            "GET",
            base + "/spend/logs",
            headers={"Authorization": "Bearer " + get_settings().litellm_api_key.strip()},
            params=params,
        )
        payload = response.json()
        cache[cache_key] = payload
        self._page_cache = cache
        return payload


def map_provider(value: str | None) -> str | None:
    if not value:
        return None
    return _PROVIDER_ALIASES.get(value.strip().lower())


def _entries(payload) -> tuple[list, str | None, bool]:
    if isinstance(payload, list):
        return payload, None, False
    if isinstance(payload, dict):
        for key in ("data", "logs", "spend_logs"):
            if isinstance(payload.get(key), list):
                cursor = payload.get("next_page") or payload.get("next_cursor")
                return payload[key], cursor or None, False
    return [], None, True


def _split(payload) -> tuple[Page, Page]:
    rows, cursor, unrecognized = _entries(payload)
    if unrecognized:
        notice = "LiteLLM response was not a list of spend logs. Nothing was stored."
        return Page(unrecognized=True, notice=notice), Page(unrecognized=True, notice=notice)
    usage: list[UsageDraft] = []
    costs: list[CostDraft] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        provider = map_provider(item.get("custom_llm_provider") or item.get("provider"))
        stamp = item.get("startTime") or item.get("start_time") or item.get("timestamp")
        if provider is None or stamp is None:
            continue
        occurred = parse_timestamp(stamp)
        request_id = item.get("request_id") or item.get("litellm_call_id")
        model = item.get("model")
        identity = stable_id("litellm", provider, request_id or occurred.isoformat(), model)
        latency = item.get("response_time_ms") or item.get("latency_ms")
        draft = UsageDraft(
            external_event_id=identity,
            occurred_at_utc=occurred,
            source_type="litellm",
            model=model,
            input_tokens=item.get("prompt_tokens"),
            output_tokens=item.get("completion_tokens"),
            request_count=1 if request_id else None,
            latency_ms=None if latency is None else int(float(latency)),
            metadata={"provider": provider, "cost_kind": "gateway_estimated"},
        )
        setattr(draft, "provider_name", provider)
        usage.append(draft)
        spend = item.get("spend")
        if spend is None:
            spend = item.get("response_cost")
        if spend is not None:
            cost = CostDraft(
                external_record_id=identity + ":cost",
                period_start_utc=occurred,
                period_end_utc=occurred,
                cost_usd=Decimal(str(spend)),
                source_type="litellm",
                cost_kind="gateway_estimated",
                model=model,
            )
            setattr(cost, "provider_name", provider)
            costs.append(cost)
    return Page(records=usage, next_cursor=cursor), Page(records=costs, next_cursor=cursor)
