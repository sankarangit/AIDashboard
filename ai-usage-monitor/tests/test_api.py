import py_compile
from pathlib import Path

from backend.config import reset_settings
from backend.database import reset_engine
from fastapi.testclient import TestClient


def test_health_overview_and_providers(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "api.db").as_posix())
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("OPENAI_ADMIN_KEY", "")
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", "")
    monkeypatch.setenv("XAI_MANAGEMENT_API_KEY", "")
    monkeypatch.setenv("XAI_TEAM_ID", "")
    reset_settings()
    reset_engine()
    from backend.main import app

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        seeded = client.post("/api/demo/seed")
        assert seeded.status_code == 200
        overview = client.get("/api/overview", params={"include_demo": "true", "timezone": "Asia/Singapore"})
        assert overview.status_code == 200
        body = overview.json()
        assert body["data_classification"] == "demo"
        assert body["includes_demo_data"] is True
        assert body["kpis"]["billed_api_cost_usd"] is not None
        assert body["kpis"]["combined_monthly_outlay_usd"] is None
        hidden = client.get("/api/overview", params={"include_demo": "false"})
        assert hidden.json()["kpis"]["billed_api_cost_usd"] is None
        providers = client.get("/api/providers").json()["providers"]
        statuses = {row["name"]: row["connection_status"] for row in providers}
        assert statuses["openai"] == "not_configured"
        assert statuses["anthropic"] == "not_configured"
        assert statuses["xai"] == "not_configured"
        secret = "present-admin-key-should-not-appear"
        assert secret not in client.get("/api/providers").text
        exported = client.get("/api/usage", params={"include_demo": "true"})
        assert exported.status_code == 200
        assert exported.json()["rows"]
    reset_engine()
    reset_settings()


def test_frontend_files_compile():
    root = Path(__file__).resolve().parents[1] / "frontend"
    files = list(root.rglob("*.py"))
    assert files
    for path in files:
        py_compile.compile(str(path), doraise=True)


def test_subscription_sgd_is_not_added_to_usd(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "api2.db").as_posix())
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    reset_settings()
    reset_engine()
    from backend.main import app

    with TestClient(app) as client:
        client.post("/api/demo/seed")
        subs = client.get("/api/subscriptions", params={"include_demo": "true"}).json()
        currencies = {row["currency"] for row in subs["subscriptions"]}
        assert "SGD" in currencies
        assert "USD" in currencies
        overview = client.get("/api/overview", params={"include_demo": "true"}).json()
        assert overview["kpis"]["subscription_fees_usd"] == 40
        assert overview["kpis"]["subscription_fees_other"][0]["currency"] == "SGD"
    reset_engine()
    reset_settings()
