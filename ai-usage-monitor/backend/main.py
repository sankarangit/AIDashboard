"""FastAPI application. Binds to loopback unless an auth token is configured."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.api import budgets, imports, overview, providers, subscriptions, sync, usage
from backend.config import ROOT, get_settings
from backend.database import get_engine, session_scope
from backend.schemas import HealthResponse
from backend.services.demo_data import ensure_providers
from backend.services.scheduler import start_scheduler

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def init_database() -> None:
    settings = get_settings()
    if settings.auth_required and not settings.api_auth_token.strip():
        raise RuntimeError("Refusing to start. A non-loopback bind requires API_AUTH_TOKEN.")
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.resolved_database_url)
    command.upgrade(cfg, "head")
    with session_scope() as db:
        ensure_providers(db)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_database()
    scheduler = start_scheduler() if get_settings().scheduler_enabled else None
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


app = FastAPI(title="AI Usage Monitor", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8501", "http://localhost:8501"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(overview.router, prefix="/api")
app.include_router(usage.router, prefix="/api")
app.include_router(providers.router, prefix="/api")
app.include_router(subscriptions.router, prefix="/api")
app.include_router(budgets.router, prefix="/api")
app.include_router(imports.router, prefix="/api")
app.include_router(sync.router, prefix="/api")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
    return HealthResponse(status="ok", database="ok", time_utc=datetime.now(UTC))


@app.exception_handler(ValueError)
async def value_error(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error_code": "invalid_request", "message": str(exc)})


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error_code": "invalid_request", "message": "Request validation failed.", "details": exc.errors()},
    )
