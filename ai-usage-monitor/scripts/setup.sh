#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
if [[ ! -f .env ]]; then
  cp .env.example .env
fi
mkdir -p data
python -m alembic upgrade head
python scripts/seed_demo.py
echo "API:        http://127.0.0.1:8000"
echo "Dashboard:  http://127.0.0.1:8501"
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
python -m streamlit run frontend/Home.py --server.address 127.0.0.1 --server.port 8501 &
UI_PID=$!
echo "API pid ${API_PID}, dashboard pid ${UI_PID}"
wait
