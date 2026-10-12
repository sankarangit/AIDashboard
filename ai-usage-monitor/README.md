# AI Usage Monitor

Local dashboard for authorized OpenAI, Anthropic, and xAI usage. It runs with labeled synthetic data and does not need API keys. Live numbers appear only after a read-only admin or management credential is set in `.env`.

Consumer subscriptions (ChatGPT Plus/Pro, Claude Pro/Max, Grok) are manual records. They are not read from the API and they are not added to provider-billed API cost.

## Run on Windows

```powershell
cd ai-usage-monitor
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python scripts\seed_demo.py
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, from the same folder:

```powershell
.\.venv\Scripts\python -m streamlit run frontend/Home.py --server.address 127.0.0.1 --server.port 8501
```

Or run `.\scripts\setup.ps1`, which creates the environment, seeds the demo, and opens both processes.

- Dashboard: http://127.0.0.1:8501
- API: http://127.0.0.1:8000
- Health: http://127.0.0.1:8000/health

## Run on Ubuntu

```bash
cd ai-usage-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
python scripts/seed_demo.py
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Second terminal:

```bash
streamlit run frontend/Home.py --server.address 127.0.0.1 --server.port 8501
```

`./scripts/setup.sh` does the same and starts both processes.

## Checks

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check .
```

## Live provider data

Leave the keys in `.env` empty until you have them. A missing key shows **Not Configured** and does not invent usage.

| Variable | What it is |
| --- | --- |
| `OPENAI_ADMIN_KEY` | Organization admin key for usage and `/v1/organization/costs` |
| `ANTHROPIC_ADMIN_KEY` | Organization admin key for the Usage & Cost Admin API |
| `XAI_MANAGEMENT_API_KEY` and `XAI_TEAM_ID` | Management API access. An inference key is not enough |
| `LITELLM_BASE_URL` and `LITELLM_API_KEY` | Optional spend-log import. Costs stay estimated |

Then call **Test connection** or **Sync now** in Settings, or run `python scripts/sync_once.py`.

PostgreSQL is selected with `DATABASE_URL` after `pip install -e ".[pg]"`. SQLite is the default.

## Security

The API and Streamlit bind to `127.0.0.1` by default. Docker Compose publishes those ports on localhost and requires `API_AUTH_TOKEN`. Do not publish the dashboard on a public interface without authentication and HTTPS. Do not commit `.env`. Provider secrets are not stored in SQLite. See `docs/LIMITATIONS.md`.
