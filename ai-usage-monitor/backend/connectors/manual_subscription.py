"""Manual subscription records. This connector never calls a provider."""

from __future__ import annotations

from datetime import datetime

from backend.connectors.base import ConfigCheck, ConnectionResult, Page, ProviderConnector

OFFICIAL_PAGES = {
    "openai": "https://platform.openai.com/usage",
    "anthropic": "https://console.anthropic.com/settings/usage",
    "xai": "https://console.x.ai/",
}

CONSUMER_PAGES = {
    "openai": "https://chatgpt.com/",
    "anthropic": "https://claude.ai/settings",
    "xai": "https://grok.com/",
}


class ManualSubscriptionConnector(ProviderConnector):
    name = "manual_subscription"

    def validate_config(self) -> ConfigCheck:
        return ConfigCheck(
            True,
            "unverified",
            "Subscription allowances are entered by hand. No provider is contacted.",
        )

    def test_connection(self) -> ConnectionResult:
        return ConnectionResult(
            "unverified",
            "There is no read-only API for ChatGPT, Claude, or Grok consumer plan balances. "
            "Record what you can see in the official account page and keep the observed time.",
        )

    def fetch_usage(self, start_at: datetime, end_at: datetime, cursor: str | None = None) -> Page:
        return Page(notice="Manual subscriptions do not produce usage events.")

    def fetch_costs(self, start_at: datetime, end_at: datetime, cursor: str | None = None) -> Page:
        return Page(notice="Manual subscription fees are not API costs.")

    def capabilities(self) -> dict:
        return {
            "tokens": False,
            "costs": False,
            "requests": False,
            "latency": False,
            "cache_tokens": False,
            "required_roles": [],
            "consumer_subscription": "manual_only",
        }
