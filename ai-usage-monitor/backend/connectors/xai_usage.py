"""xAI Management API historical usage.

A regular inference key is not treated as billing access.
https://docs.x.ai/developers/rest-api-reference/management/billing
https://docs.x.ai/developers/management-api-guide
"""

from __future__ import annotations

from datetime import UTC, datetime
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

_NOT_CONFIGURED = (
    "xAI billing is not configured. Set XAI_MANAGEMENT_API_KEY and XAI_TEAM_ID. "
    "A Grok consumer subscription and a regular inference key do not grant the Management API. "
    "https://docs.x.ai/developers/rest-api-reference/management/billing"
)


class XAIUsageConnector(HttpConnector):
    name = "xai"

    def validate_config(self) -> ConfigCheck:
        settings = get_settings()
        if not settings.xai_management_api_key.strip() or not settings.xai_team_id.strip():
            return ConfigCheck(False, "not_configured", _NOT_CONFIGURED)
        return ConfigCheck(True, "configured", "An xAI management key and team id are present and have not been verified yet.")

    def capabilities(self) -> dict:
        return {
            "tokens": True,
            "costs": True,
            "requests": True,
            "latency": False,
            "cache_tokens": True,
            "required_roles": ["xAI management API key", "team id"],
            "coverage": "POST /v1/billing/teams/{team_id}/usage and GET prepaid balance for the connection test only.",
            "consumer_subscription": False,
        }

    def permission_message(self, status_code: int) -> str:
        return (
            "xAI rejected the management key or team id. Regular inference keys cannot read billing. "
            f"HTTP {status_code}. https://docs.x.ai/developers/management-api-guide"
        )

    def test_connection(self) -> ConnectionResult:
        check = self.validate_config()
        if not check.ok:
            return ConnectionResult(check.status, check.message)
        team = get_settings().xai_team_id.strip()
        try:
            response = self.request(
                "GET",
                f"https://management-api.x.ai/v1/billing/teams/{team}/prepaid/balance",
                headers=self._headers(),
            )
        except ConnectorError as exc:
            return ConnectionResult(exc.status, exc.message)
        payload = response.json() if response.content else {}
        balance = _balance_text(payload if isinstance(payload, dict) else {})
        message = "Read-only prepaid balance endpoint responded. No inference call was made."
        if balance is None:
            message += " The response had no recognized balance field, so none is displayed."
        return ConnectionResult("connected", message, reported_balance=balance)

    def fetch_usage(self, start_at: datetime, end_at: datetime, cursor: str | None = None) -> Page:
        payload = self._usage_payload(start_at, end_at, cursor)
        return _split(payload)[0]

    def fetch_costs(self, start_at: datetime, end_at: datetime, cursor: str | None = None) -> Page:
        payload = self._usage_payload(start_at, end_at, cursor)
        return _split(payload)[1]

    def _usage_payload(self, start_at: datetime, end_at: datetime, cursor: str | None) -> dict:
        self._require()
        team = get_settings().xai_team_id.strip()
        body = {
            "start_time": start_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_time": end_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if cursor:
            body["cursor"] = cursor
        cache_key = (body["start_time"], body["end_time"], cursor)
        cache = getattr(self, "_page_cache", {})
        if cache_key in cache:
            return cache[cache_key]
        response = self.request(
            "POST",
            f"https://management-api.x.ai/v1/billing/teams/{team}/usage",
            headers={**self._headers(), "Content-Type": "application/json"},
            json=body,
        )
        payload = response.json()
        stored = payload if isinstance(payload, dict) else {"_unrecognized": True}
        cache[cache_key] = stored
        self._page_cache = cache
        return stored

    def _headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer " + get_settings().xai_management_api_key.strip()}

    def _require(self) -> None:
        check = self.validate_config()
        if not check.ok:
            raise ConnectorError(check.status, check.message)


def _balance_text(payload: dict) -> str | None:
    for key in ("balance", "prepaid_balance", "available_balance", "amount"):
        value = payload.get(key)
        if isinstance(value, (int, float, str)) and str(value) != "":
            return str(value)
        if isinstance(value, dict) and value.get("value") is not None:
            currency = value.get("currency") or ""
            return f"{value.get('value')} {currency}".strip()
    return None


def _rows(payload: dict) -> tuple[list, str | None, bool]:
    if not isinstance(payload, dict):
        return [], None, True
    for key in ("data", "usage", "results", "records"):
        value = payload.get(key)
        if isinstance(value, list):
            cursor = payload.get("next_cursor") or payload.get("next_page")
            return value, cursor or None, False
    return [], None, True


def _first(item: dict, *keys: str):
    for key in keys:
        if item.get(key) is not None:
            return item.get(key)
    return None


def _split(payload: dict) -> tuple[Page, Page]:
    rows, cursor, unrecognized = _rows(payload)
    if unrecognized:
        notice = "xAI usage response did not include a recognized record list. Nothing was stored."
        return Page(unrecognized=True, notice=notice), Page(unrecognized=True, notice=notice)
    usage: list[UsageDraft] = []
    costs: list[CostDraft] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        stamp = _first(item, "start_time", "timestamp", "date", "bucket_start")
        if stamp is None:
            continue
        start = parse_timestamp(stamp)
        end_raw = _first(item, "end_time", "bucket_end")
        end = parse_timestamp(end_raw) if end_raw is not None else start
        model = item.get("model")
        identity = stable_id("xai", start.isoformat(), end.isoformat(), model, item.get("api_key_id"))
        input_tokens = _first(item, "input_tokens", "prompt_tokens")
        output_tokens = _first(item, "output_tokens", "completion_tokens")
        cache_tokens = _first(item, "cached_tokens", "cache_read_tokens")
        requests = _first(item, "request_count", "requests", "num_requests")
        if any(value is not None for value in (input_tokens, output_tokens, cache_tokens, requests)):
            usage.append(
                UsageDraft(
                    external_event_id=identity,
                    occurred_at_utc=start,
                    source_type="provider_usage",
                    model=model,
                    input_tokens=None if input_tokens is None else int(input_tokens),
                    output_tokens=None if output_tokens is None else int(output_tokens),
                    cache_read_tokens=None if cache_tokens is None else int(cache_tokens),
                    request_count=None if requests is None else int(requests),
                    metadata={"cache_relationship": "unknown"},
                )
            )
        cost = _first(item, "cost_usd", "cost", "amount_usd")
        if cost is not None and not isinstance(cost, dict):
            costs.append(
                CostDraft(
                    external_record_id=identity + ":cost",
                    period_start_utc=start,
                    period_end_utc=end,
                    cost_usd=Decimal(str(cost)),
                    source_type="provider_cost",
                    cost_kind="provider_billed",
                    model=model,
                )
            )
    return Page(records=usage, next_cursor=cursor), Page(records=costs, next_cursor=cursor)
