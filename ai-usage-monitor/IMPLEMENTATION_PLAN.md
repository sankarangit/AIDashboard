# Implementation plan

## Milestone 0 — Scaffold
- Python project (`pyproject.toml`), environment template, gitignore, Alembic, Docker Compose, Windows and Ubuntu setup scripts.
- SQLite by default. PostgreSQL is configuration-only until the optional driver is installed.

## Milestone 1 — Phase 1 runnable MVP
- SQLAlchemy models, initial migration, and idempotent demo seed for at least 30 days across OpenAI, Anthropic, and xAI.
- FastAPI routes for health, overview, usage, costs, providers, subscriptions, budgets, reconciliation, and imports.
- Streamlit pages: Overview, Provider Comparison, Usage Trends, Model Breakdown, Coding Agents, Subscriptions, Budgets & Alerts, Reconciliation, Settings.
- Demo rows are labeled and excluded from live totals when demo mode is off.
- Provider status defaults to Not Configured. No API key is required.
- Automated tests for aggregation, null handling, Singapore-day boundaries, reconciliation, redaction, and API behavior.

## Milestone 2 — Phase 2 live ingestion
- Read-only connectors for OpenAI organization usage/costs, Anthropic Usage & Cost Admin API, and xAI Management API billing usage.
- Permission and rate-limit statuses, cursor pagination, retry/backoff, and idempotent sync.
- Missing credentials or an unrecognized payload store nothing. No inferred usage.

## Milestone 3 — Phase 3 imports and reconciliation
- Explicit CSV/JSONL agent-log import and optional LiteLLM spend-log pull.
- Secret-bearing columns dropped. Duplicate files and duplicate external IDs do not change totals.
- Reconciliation compares provider-billed totals with gateway estimates and never adds them.

## Milestone 4 — Phase 4 local reliability
- Budget thresholds at 50/80/100 percent with UI warnings.
- Email only when SMTP is configured and alerting is explicitly enabled.
- Scheduler off by default. Compose binds published ports to localhost and requires an auth token inside the containers.
- Docs: architecture, provider setup, data dictionary, limitations, testing.

## Out of scope
- Scraping consumer chat sites, session cookies, passwords, or subscription reset timers.
- Inference calls made only to probe a key.
- Inventing token prices when a provider cost endpoint does not return them.
- Treating ChatGPT Plus/Pro, Claude Pro/Max, or Grok consumer plans as API billing accounts.
