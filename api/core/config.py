"""Application configuration.

Pydantic Settings reads from environment + `.env` (when present). Every value
that has a non-trivial production default is documented inline so the
production deployment manifest under `deploy/` knows exactly what it must set.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Runtime ──────────────────────────────────────────────────────────
    app_env: Literal["local", "staging", "production"] = "local"
    app_debug: bool = False
    app_secret_key: str = "change-me"

    # ─── Database ─────────────────────────────────────────────────────────
    # SQLite for local dev, Postgres in prod. Both go through SQLAlchemy
    # asyncio so the route handlers can stay native-async.
    database_url: str = "sqlite+aiosqlite:///./x402guard.db"

    # ─── Solana ───────────────────────────────────────────────────────────
    solana_rpc_url: str = "https://api.devnet.solana.com"
    solana_cluster: Literal["devnet", "mainnet"] = "devnet"

    # `solana-keygen grind` will give us a real ID before mainnet deploy.
    # Placeholder is the same vanity string used in the Anchor declare_id!.
    agent_vault_program_id: str = "5s9rscxcoXZMLwn2cenGYhj6zd5voyMHAmFBe4qhZQxH"

    # USDC mint address. Defaults are Circle's official mints:
    #   devnet:  4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU
    #   mainnet: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
    usdc_mint: str = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"

    # ─── Crypto ───────────────────────────────────────────────────────────
    # 32-byte master key (hex) used to wrap each user's per-account KEK
    # which in turn wraps that account's delegation private keys. Production
    # ROTATES this; for the hackathon a single key is good enough.
    connection_vault_key: str = "00" * 32

    # ─── CORS ─────────────────────────────────────────────────────────────
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor — populated once at import time per process."""
    return Settings()
