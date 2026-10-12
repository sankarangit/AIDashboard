"""Connector registry."""

from __future__ import annotations

from backend.connectors.anthropic_usage import AnthropicUsageConnector
from backend.connectors.base import ProviderConnector
from backend.connectors.litellm_import import LiteLLMImportConnector
from backend.connectors.openai_usage import OpenAIUsageConnector
from backend.connectors.xai_usage import XAIUsageConnector

PROVIDER_NAMES = ("openai", "anthropic", "xai")


def build_connector(name: str, **kwargs) -> ProviderConnector:
    mapping = {
        "openai": OpenAIUsageConnector,
        "anthropic": AnthropicUsageConnector,
        "xai": XAIUsageConnector,
        "litellm": LiteLLMImportConnector,
    }
    if name not in mapping:
        raise KeyError(name)
    return mapping[name](**kwargs)
