"""Shared database fixture."""

from __future__ import annotations

import pytest
from backend.config import reset_settings
from backend.database import Base, get_engine, get_session_factory, reset_engine
from backend.services.demo_data import ensure_providers
from sqlalchemy.orm import Session


@pytest.fixture
def db(tmp_path, monkeypatch) -> Session:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (tmp_path / "test.db").as_posix())
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    reset_settings()
    reset_engine()
    Base.metadata.create_all(get_engine())
    session = get_session_factory()()
    ensure_providers(session)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        reset_engine()
        reset_settings()
