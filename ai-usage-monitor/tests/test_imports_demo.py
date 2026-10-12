from pathlib import Path

from backend.connectors.agent_import import import_agent_bytes
from backend.models import CostRecord, UsageEvent
from backend.services.demo_data import seed_demo
from sqlalchemy import select


def test_import_file_twice_does_not_change_totals(db):
    payload = (Path(__file__).parent / "fixtures" / "agent_sample.csv").read_bytes()
    first = import_agent_bytes(db, filename="agent_sample.csv", payload=payload)
    second = import_agent_bytes(db, filename="agent_sample.csv", payload=payload)
    db.commit()
    assert first["inserted"] == 2
    assert second["inserted"] == 0
    assert second["duplicate_file"] is True
    stored = " ".join((row.metadata_json or "") for row in db.scalars(select(UsageEvent)).all())
    assert "SECRET_PROMPT_TEXT" not in stored
    assert "SECRET_RESPONSE_TEXT" not in stored
    costs = list(db.scalars(select(CostRecord)).all())
    assert len(costs) == 2
    assert {row.cost_kind for row in costs} == {"gateway_estimated"}


def test_demo_seed_is_idempotent_and_labeled(db):
    first = seed_demo(db)
    second = seed_demo(db)
    db.commit()
    assert first["already_present"] is False
    assert first["inserted_usage"] > 0
    assert second["already_present"] is True
    assert second["inserted_usage"] == 0
    assert all(row.is_demo for row in db.scalars(select(UsageEvent)).all())
    assert all(row.is_demo for row in db.scalars(select(CostRecord)).all())
