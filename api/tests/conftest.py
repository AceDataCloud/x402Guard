"""Pytest fixtures shared across the API test suite."""

from __future__ import annotations

import os

# Override env BEFORE any application module imports `Settings`.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("APP_ENV", "local")
os.environ.setdefault("APP_DEBUG", "false")
os.environ.setdefault(
    # Devnet program ID is the same vanity placeholder used in declare_id!.
    "AGENT_VAULT_PROGRAM_ID",
    "5s9rscxcoXZMLwn2cenGYhj6zd5voyMHAmFBe4qhZQxH",
)
os.environ.setdefault(
    "USDC_MINT",
    "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU",
)
