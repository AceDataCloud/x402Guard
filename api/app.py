"""FastAPI app factory + routing wiring."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.core.config import get_settings
from api.core.db import init_models
from api.routes import auth, health, mcp, mcp_sessions, vaults


@asynccontextmanager
async def _lifespan(_: FastAPI):
    """Ensure DB schema exists for local SQLite dev. Production runs Alembic
    migrations and bypasses this branch by checking the URL.
    """
    if get_settings().database_url.startswith("sqlite"):
        await init_models()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="x402guard",
        version="0.1.0",
        description=(
            "Solana-native spending guardrails for AI agents. "
            "REST + per-vault MCP backend."
        ),
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,  # we use bearer tokens, not cookies
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes are mounted by the router file itself so we don't have to
    # remember a prefix here. Keeps tests independent of mount order.
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(vaults.router)
    app.include_router(mcp_sessions.router)
    app.include_router(mcp.router)

    return app


app = create_app()
