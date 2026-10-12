"""Anthropic organization Usage & Cost Admin API.

Claude Pro/Max and Claude Code subscription quotas are not read from this API.
https://platform.claude.com/docs/en/manage-claude/usage-cost-api
https://platform.claude.com/docs/en/manage-claude/admin-api
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
    "Anthropic is not configured. Set ANTHROPIC_ADMIN_KEY to an organization Admin API key. "
    "Claude Pro, Max, and Claude Code subscription quotas are not available from the Admin API. "
    "https://platform.claude.com/docs/en/manage-claude/usage-cost-api"
)
_PERMISSION = (
    "Anthropic rejected the admin key or this account has no organization Admin API access. "
    "Import an official usage report or an agent log instead of treating a personal subscription as API billing. "
    "https://platform.claude.com/docs/en/manage-claude/admin-api"
)


class AnthropicUsageConnector(HttpConnector):
    name = "anthropic"

    def validate_config(self) -> ConfigCheck:
        if not get_settings().anthropic_admin_key.strip():
            return ConfigCheck(False, "not_configured", _NOT_CONFIGURED)
        return ConfigCheck(True, "configured", "An Anthropic admin key is present and has not been verified yet.")

    def capabilities(self) -> dict:
        return {
            "tokens": True,
            "costs": True,
            "requests": False,
            "latency": False,
            "cache_tokens": True,
            "required_roles": ["Anthropic organization admin key"],
            "coverage": "Messages usage report and cost report. Cost amounts are minor currency units (cents) per Anthropic's cost report.",
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
            self.fetch_usage(start, end)
        except ConnectorError as exc:
            return ConnectionResult(exc.status, exc.message)
        return ConnectionResult("connected", "Read-only usage report endpoint responded. No message was generated.")

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": get_settings().anthropic_admin_key.strip(),
            "anthropic-version": "2023-06-01",
        }

    def fetch_usage(self, start_at: datetime, end_at: datetime, cursor: str | None = None) -> Page:
        self._require()
        params = _window_params(start_at, end_at, cursor)
        params.extend([("group_by[]", "model"), ("group_by[]", "workspace_id")])
        response = self.request(
            "GET",
            "https://api.anthropic.com/v1/organizations/usage_report/messages",
            headers=self._headers(),
            params=params,
        )
        return _parse_usage(response.json())

    def fetch_costs(self, start_at: datetime, end_at: datetime, cursor: str | None = None) -> Page:
        self._require()
        params = _window_params(start_at, end_at, cursor)
        params.append(("group_by[]", "description"))
        response = self.request(
            "GET",
            "https://api.anthropic.com/v1/organizations/cost_report",
            headers=self._headers(),
            params=params,
        )
        return _parse_costs(response.json())

    def _require(self) -> None:
        check = self.validate_config()
        if not check.ok:
            raise ConnectorError(check.status, check.message)


def _window_params(start_at: datetime, end_at: datetime, cursor: str | None) -> list[tuple[str, str]]:
    params = [
        ("starting_at", start_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("ending_at", end_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ("bucket_width", "1d"),
        ("limit", "31"),
    ]
    if cursor:
        params.append(("page", cursor))
    return params


def _cache_write(result: dict) -> int | None:
    creation = result.get("cache_creation")
    if not isinstance(creation, dict):
        return result.get("cache_creation_input_tokens")
    parts = [
        creation.get("ephemeral_5m_input_tokens"),
        creation.get("ephemeral_1h_input_tokens"),
    ]
    present = [int(part) for part in parts if part is not None]
    if not present:
        return None
    return sum(present)


def _parse_usage(payload: dict) -> Page:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return Page(unrecognized=True, notice="Anthropic usage response did not include a data array. Nothing was stored.")
    records: list[UsageDraft] = []
    for bucket in payload["data"]:
        start = parse_timestamp(bucket.get("starting_at"))
        for result in bucket.get("results") or []:
            model = result.get("model")
            workspace = result.get("workspace_id")
            records.append(
                UsageDraft(
                    external_event_id=stable_id(
                        "anthropic",
                        "messages",
                        bucket.get("starting_at"),
                        bucket.get("ending_at"),
                        model,
                        workspace,
                        result.get("api_key_id"),
                    ),
                    occurred_at_utc=start,
                    source_type="provider_usage",
                    model=model,
                    project_id=workspace,
                    input_tokens=result.get("uncached_input_tokens"),
                    output_tokens=result.get("output_tokens"),
                    cache_read_tokens=result.get("cache_read_input_tokens"),
                    cache_write_tokens=_cache_write(result),
                    metadata={"cache_relationship": "additive", "usage_family": "messages"},
                )
            )
    return Page(records=records, next_cursor=payload.get("next_page") or None)


def _parse_costs(payload: dict) -> Page:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return Page(unrecognized=True, notice="Anthropic cost response did not include a data array. Nothing was stored.")
    records: list[CostDraft] = []
    skipped = 0
    for bucket in payload["data"]:
        start = parse_timestamp(bucket.get("starting_at"))
        end = parse_timestamp(bucket.get("ending_at"))
        for result in bucket.get("results") or []:
            currency = str(result.get("currency") or "USD").upper()
            raw_amount = result.get("amount")
            if raw_amount is None:
                continue
            if currency != "USD":
                skipped += 1
                continue
            # Official cost report amounts are minor units (cents for USD).
            cost = (Decimal(str(raw_amount)) / Decimal("100")).quantize(Decimal("0.000001"))
            model = result.get("model") or result.get("description")
            records.append(
                CostDraft(
                    external_record_id=stable_id(
                        "anthropic",
                        "cost",
                        bucket.get("starting_at"),
                        bucket.get("ending_at"),
                        model,
                        result.get("token_type"),
                        result.get("cost_type"),
                        result.get("workspace_id"),
                    ),
                    period_start_utc=start,
                    period_end_utc=end,
                    cost_usd=cost,
                    source_type="provider_cost",
                    cost_kind="provider_billed",
                    model=model,
                    project_id=result.get("workspace_id"),
                )
            )
    notice = None
    if skipped:
        notice = f"Skipped {skipped} non-USD Anthropic cost rows. They were not converted."
    return Page(records=records, next_cursor=payload.get("next_page") or None, notice=notice)
