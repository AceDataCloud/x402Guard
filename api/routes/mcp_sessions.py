"""`/api/v1/vaults/{id}/mcp-sessions` — owner-only management of the
opaque session tokens an agent uses to talk to `/mcp/<token>`.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.auth import OwnerDep
from api.core.config import get_settings
from api.core.db import get_session
from api.core.models import MCPSession, Vault
from api.routes.schemas import (
    CreateMCPSessionRequest,
    CreateMCPSessionResponse,
)

router = APIRouter(prefix="/api/v1/vaults", tags=["mcp-sessions"])


def _public_mcp_url(token: str) -> str:
    """The URL we tell the user to paste into Claude Desktop."""
    s = get_settings()
    base = (
        "https://x402guard.acedata.cloud"
        if s.app_env == "production"
        else "http://localhost:8000"
    )
    return f"{base}/mcp/{token}"


async def _vault_or_404(db: AsyncSession, owner: str, vault_id: str) -> Vault:
    try:
        uid = uuid.UUID(vault_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid vault id") from exc
    res = await db.execute(select(Vault).where(Vault.id == uid))
    v = res.scalar_one_or_none()
    if v is None or v.owner_pubkey != owner:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
    return v


@router.post(
    "/{vault_id}/mcp-sessions",
    response_model=CreateMCPSessionResponse,
)
async def create_mcp_session(
    vault_id: str,
    body: CreateMCPSessionRequest,
    owner: OwnerDep,
    db: AsyncSession = Depends(get_session),
) -> CreateMCPSessionResponse:
    v = await _vault_or_404(db, owner, vault_id)

    token = secrets.token_urlsafe(32)
    s = MCPSession(token=token, vault_id=v.id, label=body.label)
    db.add(s)
    await db.commit()
    await db.refresh(s)

    return CreateMCPSessionResponse(
        token=token,
        label=s.label,
        mcp_url=_public_mcp_url(token),
        created_at=s.created_at,
    )


@router.get(
    "/{vault_id}/mcp-sessions",
    response_model=list[CreateMCPSessionResponse],
)
async def list_mcp_sessions(
    vault_id: str,
    owner: OwnerDep,
    db: AsyncSession = Depends(get_session),
) -> list[CreateMCPSessionResponse]:
    v = await _vault_or_404(db, owner, vault_id)
    res = await db.execute(
        select(MCPSession)
        .where(MCPSession.vault_id == v.id, MCPSession.revoked_at.is_(None))
        .order_by(MCPSession.created_at.desc())
    )
    return [
        CreateMCPSessionResponse(
            token=s.token,
            label=s.label,
            mcp_url=_public_mcp_url(s.token),
            created_at=s.created_at,
        )
        for s in res.scalars().all()
    ]


@router.delete("/{vault_id}/mcp-sessions/{token}")
async def revoke_mcp_session(
    vault_id: str,
    token: str,
    owner: OwnerDep,
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    v = await _vault_or_404(db, owner, vault_id)
    res = await db.execute(
        select(MCPSession).where(
            MCPSession.token == token, MCPSession.vault_id == v.id
        )
    )
    s = res.scalar_one_or_none()
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    s.revoked_at = datetime.now(UTC)
    await db.commit()
    return {"status": "revoked"}
