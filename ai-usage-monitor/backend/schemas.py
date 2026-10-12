"""Request and response models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    error_code: str
    message: str


class HealthResponse(BaseModel):
    status: str
    database: str
    time_utc: datetime


class SubscriptionIn(BaseModel):
    provider: str
    plan: str = Field(min_length=1, max_length=80)
    monthly_fee: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=8)
    billing_day: int | None = Field(default=None, ge=1, le=28)
    renewal_date: date | None = None
    manual_allowance: str | None = None
    manually_recorded_usage: str | None = None
    usage_page_url: str | None = None
    notes: str | None = None


class SubscriptionUpdate(BaseModel):
    plan: str | None = None
    monthly_fee: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    billing_day: int | None = Field(default=None, ge=1, le=28)
    renewal_date: date | None = None
    manual_allowance: str | None = None
    manually_recorded_usage: str | None = None
    usage_page_url: str | None = None
    notes: str | None = None


class BudgetIn(BaseModel):
    provider: str | None = None
    monthly_budget_usd: Decimal = Field(gt=0)
    threshold_percent: int = Field(default=80, ge=1, le=100)
    enabled: bool = True


class BudgetUpdate(BaseModel):
    monthly_budget_usd: Decimal | None = Field(default=None, gt=0)
    threshold_percent: int | None = Field(default=None, ge=1, le=100)
    enabled: bool | None = None


class SettingsUpdate(BaseModel):
    timezone: str | None = None
    include_demo: bool | None = None
    retention_days: int | None = Field(default=None, ge=0, le=3650)
    alert_email_enabled: bool | None = None
    alert_email_to: str | None = None
    fx_usd_rates: str | None = None


class ProviderUpdate(BaseModel):
    enabled: bool
