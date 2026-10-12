"""Typed connector results and read-only HTTP behavior."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime

import httpx

from backend.services.security import redact


class ConnectorError(Exception):
    def __init__(self, status: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = redact(message)


@dataclass
class ConfigCheck:
    ok: bool
    status: str
    message: str


@dataclass
class ConnectionResult:
    status: str
    message: str
    reported_balance: str | None = None


@dataclass
class UsageDraft:
    external_event_id: str
    occurred_at_utc: datetime
    source_type: str
    model: str | None = None
    project_id: str | None = None
    agent_name: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    request_count: int | None = None
    latency_ms: int | None = None
    success: bool | None = None
    metadata: dict | None = None
    is_demo: bool = False

    def as_row(self) -> dict:
        return asdict(self)


@dataclass
class CostDraft:
    external_record_id: str
    period_start_utc: datetime
    period_end_utc: datetime
    cost_usd: object
    source_type: str
    cost_kind: str = "provider_billed"
    model: str | None = None
    project_id: str | None = None
    agent_name: str | None = None
    is_demo: bool = False

    def as_row(self) -> dict:
        return asdict(self)


@dataclass
class Page:
    records: list = field(default_factory=list)
    next_cursor: str | None = None
    unrecognized: bool = False
    notice: str | None = None


class ProviderConnector(ABC):
    name: str

    @abstractmethod
    def validate_config(self) -> ConfigCheck:
        raise NotImplementedError

    @abstractmethod
    def test_connection(self) -> ConnectionResult:
        raise NotImplementedError

    @abstractmethod
    def fetch_usage(self, start_at: datetime, end_at: datetime, cursor: str | None = None) -> Page:
        raise NotImplementedError

    @abstractmethod
    def fetch_costs(self, start_at: datetime, end_at: datetime, cursor: str | None = None) -> Page:
        raise NotImplementedError

    @abstractmethod
    def capabilities(self) -> dict:
        raise NotImplementedError


class HttpConnector(ProviderConnector):
    def __init__(self, client: httpx.Client | None = None, sleeper=None) -> None:
        self._client = client
        self.sleeper = sleeper or time.sleep

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=httpx.Timeout(30.0), verify=True, follow_redirects=False)
        return self._client

    def permission_message(self, status_code: int) -> str:
        return f"The provider rejected a read-only request with HTTP {status_code}."

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        kwargs.pop("timeout", None)
        for attempt in range(3):
            try:
                response = self.client.request(method, url, timeout=30.0, **kwargs)
            except httpx.HTTPError as exc:
                if attempt < 2:
                    self.sleeper(2**attempt)
                    continue
                raise ConnectorError("failed", "Could not reach the provider. " + redact(str(exc))) from exc
            if response.status_code in {401, 403}:
                raise ConnectorError("insufficient_permissions", self.permission_message(response.status_code))
            if response.status_code == 404:
                raise ConnectorError(
                    "unsupported",
                    "The read-only endpoint returned HTTP 404 for this account.",
                )
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    delay = 2**attempt
                    retry_after = response.headers.get("retry-after")
                    if retry_after and retry_after.isdigit():
                        delay = min(int(retry_after), 30)
                    self.sleeper(delay)
                    continue
                if response.status_code == 429:
                    raise ConnectorError(
                        "rate_limited",
                        "The provider rate limited a read-only usage request. Retry later. Other providers are unchanged.",
                    )
                raise ConnectorError("failed", f"The provider returned HTTP {response.status_code} after retries.")
            if response.status_code >= 400:
                raise ConnectorError("failed", f"The provider returned HTTP {response.status_code}.")
            return response
        raise ConnectorError("failed", "The provider request did not complete.")
