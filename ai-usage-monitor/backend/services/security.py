"""Redaction, local-only auth, and alert mail that stays off unless enabled."""

from __future__ import annotations

import re
import smtplib
from email.message import EmailMessage

from fastapi import HTTPException, Request

from backend.config import Settings, get_settings

_SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"xai-[A-Za-z0-9_\-]{8,}"),
    re.compile(
        r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[=:]\s*\S+"
    ),
)


def redact(value: str | None) -> str:
    if not value:
        return ""
    text = value
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def mask_secret(value: str) -> str:
    if not value:
        return "missing"
    if len(value) <= 4:
        return "present"
    return "present · ends with " + value[-4:]


def require_mutation_auth(request: Request, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if not settings.auth_required:
        return
    expected = settings.api_auth_token.strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "auth_not_configured",
                "message": "This bind address requires API_AUTH_TOKEN before sync or imports.",
            },
        )
    header = request.headers.get("authorization", "")
    if header != f"Bearer {expected}":
        raise HTTPException(
            status_code=401,
            detail={"error_code": "unauthorized", "message": "Missing or invalid bearer token."},
        )


def send_budget_email(subject: str, body: str, settings: Settings | None = None) -> str:
    """Send mail only after the operator explicitly enables it and sets SMTP."""
    settings = settings or get_settings()
    if not settings.alert_email_enabled:
        return "disabled"
    if not settings.smtp_host or not settings.alert_email_to:
        return "not_configured"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_username or "ai-usage-monitor@localhost"
    message["To"] = settings.alert_email_to
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except OSError as exc:
        return "failed: " + redact(str(exc))
    return "sent"
