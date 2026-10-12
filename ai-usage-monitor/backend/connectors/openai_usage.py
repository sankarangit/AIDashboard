"""OpenAI organization usage and cost connector.

ChatGPT Plus/Pro usage is not available from these endpoints.
Docs checked against the organization costs and completions usage reference:
https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/costs
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from backend.config import get_settings
from backend.connectors.base import (
    ConfigCheck,
    ConnectionResult,
    CostDraft,
    HttpConnector,
    Page,
    UsageDraft,
)
from backend.services.ingest import stable_id
from backend.services.timeutils import parse_timestamp

_NOT_CONFIGURED = (
    "OpenAI is not configured. Set OPENAI_ADMIN_KEY to an organization Admin API key. "
    "A regular project key and a ChatGPT Plus or Pro subscription do not provide organization usage. "
    "https://platform.openai.com/settings/organization/admin-keys"
)
_PERMISSION = (
    "OpenAI rejected the Admin API key. Organization usage and /v1/organization/costs require "
    "an admin key with reporting access. ChatGPT subscription balances are not returned here. "
    "https://help.openai.com/en/articles/10478918-reviewing-api-usage-and-costs"
)


class OpenAIUsageConnector(HttpConnector):
    name = "openai"

    def validate_config(self) -> ConfigCheck:
        if not get_settings().openai_admin_key.strip():
            return ConfigCheck(False, "not_configured", _NOT_CONFIGURED)
        return ConfigCheck(True, "configured", "An OpenAI admin key is present and has not been verified yet.")

    def capabilities(self) -> dict:
        return {
            "tokens": True,
            "costs": True,
            "requests": True,
            "latency": False,
            "cache_tokens": True,
            "required_roles": ["OpenAI organization admin key"],
            "coverage": "Completions usage buckets and organization cost buckets. Embeddings, images, and audio are not collected.",
            "consumer_subscription": False,
        }

    def permission_message(self, status_code: int) -> str:
        return _PERMISSION + f" HTTP {status_code}."

    def test_connection(self) -> ConnectionResult:
        check = self.validate_config()
        if not check.ok:
            return ConnectionResult(check.status, check.message)
        end = datetime.now(UTC)
        start = end - timedelta(days=1)
        try:
            self.fetch_costs(start, end)
        except Exception as exc:
            from backend.connectors.base import ConnectorError

            if isinstance(exc, ConnectorError):
                return ConnectionResult(exc.status, exc.message)
            raise
        return ConnectionResult("connected", "Read-only organization costs endpoint responded. No inference call was made.")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer " + get_settings().openai_admin_key.strip()}

    def fetch_usage(self, start_at: datetime, end_at: datetime, cursor: str | None = None) -> Page:
        self._require()
        params: list[tuple[str, str]] = [
            ("start_time", str(int(start_at.timestamp()))),
            ("end_time", str(int(end_at.timestamp()))),
            ("bucket_width", "1d"),
            ("limit", "31"),
            ("group_by", "model"),
            ("group_by", "project_id"),
        ]
        if cursor:
            params.append(("page", cursor))
        response = self.request(
            "GET",
            "https://api.openai.com/v1/organization/usage/completions",
            headers=self._headers(),
            params=params,
        )
        return _parse_usage(response.json())

    def fetch_costs(self, start_at: datetime, end_at: datetime, cursor: str | None = None) -> Page:
        self._require()
        params: list[tuple[str, str]] = [
            ("start_time", str(int(start_at.timestamp()))),
            ("end_time", str(int(end_at.timestamp()))),
            ("bucket_width", "1d"),
            ("limit", "31"),
            ("group_by", "line_item"),
            ("group_by", "project_id"),
        ]
        if cursor:
            params.append(("page", cursor))
        response = self.request(
            "GET",
            "https://api.openai.com/v1/organization/costs",
            headers=self._headers(),
            params=params,
        )
        return _parse_costs(response.json())

    def _require(self) -> None:
        check = self.validate_config()
        if not check.ok:
            from backend.connectors.base import ConnectorError

            raise ConnectorError(check.status, check.message)


def _parse_usage(payload: dict) -> Page:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return Page(unrecognized=True, notice="OpenAI usage response did not include a data array. Nothing was stored.")
    records: list[UsageDraft] = []
    for bucket in payload["data"]:
        start = parse_timestamp(bucket.get("start_time"))
        for result in bucket.get("results") or []:
            model = result.get("model")
            project_id = result.get("project_id")
            request_count = result.get("num_model_requests")
            if request_count is None:
                request_count = result.get("num_requests")
            records.append(
                UsageDraft(
                    external_event_id=stable_id(
                        "openai",
                        "completions",
                        bucket.get("start_time"),
                        bucket.get("end_time"),
                        model,
                        project_id,
                        result.get("api_key_id"),
                    ),
                    occurred_at_utc=start,
                    source_type="provider_usage",
                    model=model,
                    project_id=project_id,
                    input_tokens=result.get("input_tokens"),
                    output_tokens=result.get("output_tokens"),
                    cache_read_tokens=result.get("input_cached_tokens"),
                    cache_write_tokens=result.get("input_cache_write_tokens"),
                    request_count=request_count,
                    metadata={"cache_relationship": "subset_of_input", "usage_family": "completions"},
                )
            )
    return Page(records=records, next_cursor=payload.get("next_page") or None)


def _parse_costs(payload: dict) -> Page:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return Page(unrecognized=True, notice="OpenAI cost response did not include a data array. Nothing was stored.")
    records: list[CostDraft] = []
    skipped = 0
    for bucket in payload["data"]:
        start = parse_timestamp(bucket.get("start_time"))
        end = parse_timestamp(bucket.get("end_time"))
        for result in bucket.get("results") or []:
            amount = (result.get("amount") or {}) if isinstance(result.get("amount"), dict) else {}
            currency = str(amount.get("currency") or "").lower()
            value = amount.get("value")
            if value is None:
                continue
            if currency and currency != "usd":
                skipped += 1
                continue
            line_item = result.get("line_item")
            project_id = result.get("project_id")
            records.append(
                CostDraft(
                    external_record_id=stable_id(
                        "openai",
                        "cost",
                        bucket.get("start_time"),
                        bucket.get("end_time"),
                        line_item,
                        project_id,
                        result.get("api_key_id"),
                        currency or "usd",
                    ),
                    period_start_utc=start,
                    period_end_utc=end,
                    cost_usd=Decimal(str(value)),
                    source_type="provider_cost",
                    cost_kind="provider_billed",
                    model=line_item,
                    project_id=project_id,
                )
            )
    notice = None
    if skipped:
        notice = f"Skipped {skipped} non-USD OpenAI cost rows. They were not converted."
    return Page(records=records, next_cursor=payload.get("next_page") or None, notice=notice)
