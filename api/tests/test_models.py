"""Tests for SQLAlchemy models — round-trip persistence via SQLite."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from api.core.db import SessionLocal
from api.core.models import MCPSession, Vault
from sqlalchemy import select


@pytest.mark.asyncio
async def test_vault_round_trip() -> None:
    async with SessionLocal() as s:
        v = Vault(
            owner_pubkey="GxK8ownerExampleExampleExampleExampleExample",
            agent_id_hex="ab" * 32,
            agent_name="Claude Birthday Helper",
            vault_pda="HxK8vaultExampleExampleExampleExampleExample",
            policy_pda="JxK8policyExampleExampleExampleExampleExample",
            delegation_pubkey="DxK8delegationExampleExampleExampleExample",
            delegation_priv_wrapped=b"\x00" * 64,
            daily_cap=2_000_000,
            per_call_cap=500_000,
            endpoint_allowlist="api.acedata.cloud",
            expires_at=datetime.now(UTC) + timedelta(days=7),
            paused=False,
        )
        s.add(v)
        await s.commit()
        await s.refresh(v)
        assert v.id is not None

        result = await s.execute(select(Vault).where(Vault.vault_pda == v.vault_pda))
        loaded = result.scalar_one()
        assert loaded.daily_cap == 2_000_000
        assert loaded.per_call_cap == 500_000
        assert loaded.paused is False


@pytest.mark.asyncio
async def test_mcp_session_attaches_to_vault() -> None:
    async with SessionLocal() as s:
        v = Vault(
            owner_pubkey="GxK8owner2ExampleExampleExampleExampleExample",
            agent_id_hex="cd" * 32,
            agent_name="Cursor Helper",
            vault_pda="HxK8vault2ExampleExampleExampleExampleExample",
            policy_pda="JxK8policy2ExampleExampleExampleExampleExample",
            delegation_pubkey="DxK8delegation2ExampleExampleExampleExample",
            delegation_priv_wrapped=b"\x01" * 64,
            daily_cap=10_000_000,
            per_call_cap=1_000_000,
            endpoint_allowlist="api.acedata.cloud",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        s.add(v)
        await s.flush()  # populate v.id without commit

        session = MCPSession(
            token="test-mcp-session-token-1234567890abcdef",
            vault_id=v.id,
            label="default",
        )
        s.add(session)
        await s.commit()

        result = await s.execute(
            select(MCPSession).where(MCPSession.token == session.token)
        )
        loaded = result.scalar_one()
        assert loaded.vault_id == v.id
