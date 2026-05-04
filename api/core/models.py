"""ORM models.

Mirror of the on-chain account types — we cache enough to render the Dapp
without an RPC round-trip for every page view, and to issue MCP session
tokens without hitting Solana on every spend.

Each row's authoritative source is the Solana program; this DB is a
projection of on-chain state, never the source of truth.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from api.core.db import Base


class GUID(TypeDecorator):
    """Cross-DB UUID. Postgres native, SQLite stores as 36-char string."""

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[no-untyped-def]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PgUUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return None
        if isinstance(value, UUID):
            return value if dialect.name == "postgresql" else str(value)
        return value

    def process_result_value(self, value, dialect):  # type: ignore[no-untyped-def]
        if value is None:
            return None
        return value if isinstance(value, UUID) else UUID(str(value))


def _now() -> datetime:
    return datetime.now(UTC)


class Vault(Base):
    """Owner's view of an on-chain Vault PDA."""

    __tablename__ = "vaults"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    owner_pubkey: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_id_hex: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(120), nullable=False)
    vault_pda: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    policy_pda: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    delegation_pubkey: Mapped[str] = mapped_column(String(64), nullable=False)
    delegation_priv_wrapped: Mapped[bytes] = mapped_column(nullable=False)

    daily_cap: Mapped[int] = mapped_column(BigInteger, nullable=False)
    per_call_cap: Mapped[int] = mapped_column(BigInteger, nullable=False)
    endpoint_allowlist: Mapped[str] = mapped_column(Text, nullable=False, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # On-chain creation tx — for "Verified on Solscan" badges in the UI.
    create_tx: Mapped[str | None] = mapped_column(String(96), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    sessions: Mapped[list[MCPSession]] = relationship(
        "MCPSession", back_populates="vault", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_vaults_owner_agent", "owner_pubkey", "agent_id_hex", unique=True),
    )


class MCPSession(Base):
    """An opaque token bound to one vault. Pasted into Claude Desktop /
    Cursor / etc. as the URL `https://x402guard.acedata.cloud/mcp/<token>`.
    """

    __tablename__ = "mcp_sessions"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    vault_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    vault: Mapped[Vault] = relationship("Vault", back_populates="sessions")


class SpendRecord(Base):
    """Mirror of the on-chain SpendEvent — populated via a log subscription
    so the UI history page is one DB read, not a full-chain scan.
    """

    __tablename__ = "spend_records"

    id: Mapped[UUID] = mapped_column(GUID(), primary_key=True, default=uuid4)
    vault_id: Mapped[UUID] = mapped_column(
        GUID(), ForeignKey("vaults.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nonce: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recipient_pubkey: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tx_signature: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    block_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    api_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
