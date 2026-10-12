# Architecture

Streamlit calls the FastAPI process over HTTP on `127.0.0.1`. FastAPI owns SQLite (or a configured PostgreSQL database), the connectors, and the accounting rules.

```
Streamlit pages → FastAPI → connectors / import service → SQLite
```

Usage events and cost records are separate. A provider-billed cost is never added to a gateway estimate. Demo rows share the tables and are filtered with `is_demo`.

Timestamps are stored in UTC. The UI defaults to Asia/Singapore and converts day boundaries before querying.

Sync is read-only. A connector that lacks a credential returns Not Configured and makes no HTTP call. An unrecognized payload is not stored. One provider's failure is recorded on that provider and does not stop the others.

The scheduler is off unless `SCHEDULER_ENABLED=true`. Email is off unless `ALERT_EMAIL_ENABLED=true` and SMTP settings exist, and demo budgets never send mail.

## Deployment

For a VPS, terminate TLS at a reverse proxy, set `REQUIRE_AUTH=true` and a long `API_AUTH_TOKEN`, and do not publish port 8501 or 8000 on a public interface. Compose in this repo binds published ports to `127.0.0.1` only.
