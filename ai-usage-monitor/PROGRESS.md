# Progress

## Completed
- Phase 1 dashboard is running locally with FastAPI, Streamlit, SQLite, and 35 days of labeled synthetic data.
- Pages: Overview, Provider Comparison, Usage Trends, Model Breakdown, Coding Agents, Subscriptions, Budgets & Alerts, Reconciliation, Settings.
- Demo rows are watermarked. Hiding demo data removes them from totals. Provider-billed cost, gateway estimates, and subscription fees stay separate.
- OpenAI, Anthropic, and xAI show **Not Configured** until keys exist in `.env`. No usage was invented for them.
- Connectors implement the documented read-only usage and cost endpoints, permission and rate-limit statuses, pagination, and idempotent sync.
- CSV/JSONL agent import drops prompt and response columns. The same file does not change totals when imported twice.
- Optional LiteLLM spend logs are estimated costs only, and only when that proxy is configured.
- `pytest -q`: 23 passed. `ruff check backend tests scripts frontend`: passed.

## Not verified against live providers
- No `OPENAI_ADMIN_KEY`, `ANTHROPIC_ADMIN_KEY`, or `XAI_MANAGEMENT_API_KEY` / `XAI_TEAM_ID` is configured.
- Connection tests were not run against OpenAI, Anthropic, or xAI. Status remains Not Configured.
- Anthropic cost amounts are interpreted as minor units (cents). Confirm that against a real cost-report response before trusting live totals.
- xAI historical usage is stored only when the response contains a recognized record list.

## Local URLs
- Dashboard: http://127.0.0.1:8501
- API: http://127.0.0.1:8000
- Health: http://127.0.0.1:8000/health
