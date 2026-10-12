# Data dictionary

| Table | Purpose |
| --- | --- |
| `providers` | OpenAI, Anthropic, xAI, and optional LiteLLM status. Secrets are not stored. |
| `usage_events` | Token and request measurements. `request_count`, latency, and `success` are nullable. |
| `cost_records` | Money. `cost_kind` is `provider_billed`, `gateway_estimated`, or `manual`. |
| `subscriptions` | Manual plan fees. `is_demo` marks seeded rows. Currency is kept as entered. |
| `sync_runs` | One row per sync attempt, including permission and rate-limit failures. |
| `budgets` | Monthly billed-API budget. `provider_id` null means the combined budget. |
| `alerts` | Threshold crossings at 50, 80, and 100 percent for a calendar month. |
| `imports` | SHA-256 of an uploaded file so the same file is not applied twice. |
| `app_settings` | Timezone, demo visibility, retention, and optional FX JSON. |

`usage_events` and `cost_records` are unique on provider, source type, and external id. Repeating a sync or import does not change totals.

`agent_name` on `cost_records`, `is_demo` on subscriptions and budgets, and `app_settings` are local extensions so demo data can be hidden and agent estimates can be filtered.

Demo rows are excluded when `include_demo` is false. They are never treated as live billing.
