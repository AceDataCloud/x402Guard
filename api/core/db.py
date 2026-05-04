"""SQLAlchemy 2.x async session factory.

Sessions live for the duration of one HTTP request via the `get_session`
FastAPI dependency. Production (Postgres) and tests/local (SQLite) share
the same code path; the only difference is the URL.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from api.core.config import get_settings


class Base(DeclarativeBase):
    """Project-wide declarative base. All ORM models inherit from this."""


_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=_settings.app_debug,
    future=True,
    # SQLite needs `check_same_thread=False` when used from multiple coroutines
    # which all share the same loop; SQLAlchemy handles this automatically when
    # the URL begins with `sqlite+aiosqlite://` so we don't need extra args.
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: per-request session that auto-rolls-back on error."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_models() -> None:
    """Create all tables. Called from the FastAPI startup event for the
    SQLite-backed local dev mode. Production uses Alembic migrations once
    that lands in a follow-up PR.
    """
    # Importing models here registers them on Base.metadata.
    from api.core import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
