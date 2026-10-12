"""Application settings. Provider secrets stay in the environment, never in SQLite."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


def _yaml_defaults() -> dict:
    path = ROOT / "config" / "app.yaml"
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return loaded if isinstance(loaded, dict) else {}


class Settings(BaseSettings):
    app_env: str = "local"
    database_url: str = "sqlite:///./data/usage.db"
    bind_host: str = "127.0.0.1"
    api_port: int = 8000
    ui_port: int = 8501
    api_base_url: str = "http://127.0.0.1:8000"
    default_timezone: str = "Asia/Singapore"
    require_auth: bool = False
    api_auth_token: str = ""
    scheduler_enabled: bool = False
    openai_admin_key: str = ""
    anthropic_admin_key: str = ""
    xai_management_api_key: str = ""
    xai_team_id: str = ""
    litellm_base_url: str = ""
    litellm_api_key: str = ""
    alert_email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    alert_email_to: str = ""
    fx_usd_rates: str = ""
    demo_days: int = 35
    sync_overlap_days: int = 2
    sync_lookback_days: int = 31
    max_import_bytes: int = 5_242_880
    max_import_rows: int = 50_000
    standard_alert_thresholds: list[int] = Field(default_factory=lambda: [50, 80, 100])

    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def resolved_database_url(self) -> str:
        url = self.database_url
        if not url.startswith("sqlite:///"):
            return url
        relative = url.removeprefix("sqlite:///")
        if relative.startswith("./"):
            relative = relative[2:]
        path = Path(relative)
        if not path.is_absolute():
            path = ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return "sqlite:///" + path.as_posix()

    @property
    def auth_required(self) -> bool:
        """Loopback development stays open. Any other bind requires a token."""
        if self.require_auth:
            return True
        return self.bind_host not in {"127.0.0.1", "localhost", "::1"}


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    file_defaults = _yaml_defaults()
    # Apply YAML only for fields the operator did not set via the environment.
    # Pydantic has already applied env vars. Compare against a bare Settings
    # built without the env file by checking os.environ names.
    import os

    env_names = {key.lower() for key in os.environ}
    updates = {}
    for yaml_key, attr in (
        ("default_timezone", "default_timezone"),
        ("demo_days", "demo_days"),
        ("sync_overlap_days", "sync_overlap_days"),
        ("sync_lookback_days", "sync_lookback_days"),
        ("max_import_bytes", "max_import_bytes"),
        ("max_import_rows", "max_import_rows"),
        ("standard_alert_thresholds", "standard_alert_thresholds"),
    ):
        if attr.lower() not in env_names and yaml_key in file_defaults:
            updates[attr] = file_defaults[yaml_key]
    if updates:
        return settings.model_copy(update=updates)
    return settings


def reset_settings() -> None:
    get_settings.cache_clear()
