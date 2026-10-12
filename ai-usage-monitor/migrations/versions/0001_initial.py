"""Initial schema."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "providers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(32), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("connection_status", sa.String(40), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
    )
    op.create_table(
        "usage_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("external_event_id", sa.String(80), nullable=False),
        sa.Column("occurred_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.String(120)),
        sa.Column("project_id", sa.String(80)),
        sa.Column("agent_name", sa.String(80)),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("cache_read_tokens", sa.Integer()),
        sa.Column("cache_write_tokens", sa.Integer()),
        sa.Column("request_count", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("success", sa.Boolean()),
        sa.Column("metadata_json", sa.Text()),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider_id", "source_type", "external_event_id", name="uq_usage_event_identity"),
    )
    op.create_index("ix_usage_provider_time", "usage_events", ["provider_id", "occurred_at_utc"])
    op.create_index("ix_usage_model", "usage_events", ["model"])
    op.create_index("ix_usage_demo", "usage_events", ["is_demo"])
    op.create_table(
        "cost_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("external_record_id", sa.String(80), nullable=False),
        sa.Column("period_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.String(160)),
        sa.Column("project_id", sa.String(80)),
        sa.Column("agent_name", sa.String(80)),
        sa.Column("cost_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("cost_kind", sa.String(32), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider_id", "source_type", "external_record_id", name="uq_cost_record_identity"),
    )
    op.create_index("ix_cost_provider_period", "cost_records", ["provider_id", "period_start_utc"])
    op.create_index("ix_cost_demo", "cost_records", ["is_demo"])
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("plan", sa.String(80), nullable=False),
        sa.Column("monthly_fee", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("billing_day", sa.Integer()),
        sa.Column("renewal_date", sa.Date()),
        sa.Column("manual_allowance", sa.Text()),
        sa.Column("manually_recorded_usage", sa.Text()),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.Column("usage_page_url", sa.String(300)),
        sa.Column("notes", sa.Text()),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("providers.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("records_inserted", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.Text()),
        sa.Column("next_cursor", sa.Text()),
    )
    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("providers.id")),
        sa.Column("monthly_budget_usd", sa.Numeric(18, 2), nullable=False),
        sa.Column("threshold_percent", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("budget_id", sa.Integer(), sa.ForeignKey("budgets.id"), nullable=False),
        sa.Column("period", sa.String(16), nullable=False),
        sa.Column("threshold", sa.Integer(), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.UniqueConstraint("budget_id", "period", "threshold", name="uq_alert_budget_period"),
    )
    op.create_table(
        "imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(240), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    for name in (
        "app_settings",
        "imports",
        "alerts",
        "budgets",
        "sync_runs",
        "subscriptions",
        "cost_records",
        "usage_events",
        "providers",
    ):
        op.drop_table(name)
