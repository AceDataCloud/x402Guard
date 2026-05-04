"""Pytest fixtures shared across the API test suite.

We swap to a shared file-backed SQLite so every connection in every test
sees the same schema. `:memory:` would isolate each connection from the
others, which surfaces as `OperationalError: no such table` the moment a
route's `Depends(get_session)` opens a new connection.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile

# Override env BEFORE any application module imports `Settings`.
_DB_FILE = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)  # noqa: SIM115
_DB_FILE.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_FILE.name}"
os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("APP_DEBUG", "false")
os.environ.setdefault(
    "AGENT_VAULT_PROGRAM_ID",
    "56TbAziiW8pDHFpRsxfnfBUfimBRTMCHw4gwDGw9uPW6",
)
os.environ.setdefault(
    "USDC_MINT",
    "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU",
)
os.environ.setdefault(
    "CONNECTION_VAULT_KEY",
    "00" * 32,
)
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-for-pytest-only")


def pytest_sessionstart(session) -> None:  # type: ignore[no-untyped-def]
    """Create tables once per pytest session."""
    from api.core.db import init_models

    asyncio.run(init_models())


def pytest_sessionfinish(session, exitstatus) -> None:  # type: ignore[no-untyped-def]
    with contextlib.suppress(OSError):
        os.unlink(_DB_FILE.name)
