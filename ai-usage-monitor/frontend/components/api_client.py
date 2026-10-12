"""HTTP client for the local API. Failures stay visible; they never become demo numbers."""

from __future__ import annotations

import os

import httpx

DEFAULT_BASE = "http://127.0.0.1:8000"


def api_base() -> str:
    return os.environ.get("API_BASE_URL", DEFAULT_BASE).rstrip("/")


def _headers() -> dict[str, str]:
    token = os.environ.get("API_AUTH_TOKEN", "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def request(method: str, path: str, **kwargs):
    try:
        response = httpx.request(
            method,
            api_base() + path,
            headers=_headers(),
            timeout=30.0,
            **kwargs,
        )
    except httpx.HTTPError as exc:
        raise ConnectionError(f"API at {api_base()} is not reachable. {exc}") from exc
    if response.status_code >= 400:
        message = response.text
        try:
            body = response.json()
            message = body.get("message") or body.get("detail") or message
        except ValueError:
            pass
        raise ConnectionError(f"{response.status_code}: {message}")
    if not response.content:
        return {}
    return response.json()


def get_json(path: str, params: dict | None = None):
    clean = {key: value for key, value in (params or {}).items() if value is not None and value != ""}
    return request("GET", path, params=clean)


def send(method: str, path: str, json: dict | None = None):
    return request(method, path, json=json)
