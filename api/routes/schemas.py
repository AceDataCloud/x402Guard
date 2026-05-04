"""Pydantic schemas for the REST API.

Kept separate from ORM models — request/response validation is the
HTTP boundary, persistence is its own concern.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# ─── Auth ─────────────────────────────────────────────────────────────


class ChallengeResponse(BaseModel):
    nonce: str
    message: str


class LoginRequest(BaseModel):
    pubkey: str
    message: str
    signature: str  # base64


class LoginResponse(BaseModel):
    session_token: str
    pubkey: str
    expires_in: int


# ─── Vault ────────────────────────────────────────────────────────────


class CreateVaultRequest(BaseModel):
    agent_name: Annotated[str, Field(min_length=1, max_length=120)]
    daily_cap_usdc: Annotated[float, Field(gt=0, le=10_000)]
    per_call_cap_usdc: Annotated[float, Field(gt=0, le=10_000)]
    endpoint_allowlist: Annotated[list[str], Field(min_length=1, max_length=8)]
    expires_at: datetime


class UnsignedTxResponse(BaseModel):
    """Backend builds the tx, frontend asks Phantom to sign + send.

    We return the serialized message (base64) so the wallet can show the
    user a meaningful preview.
    """

    tx_b64: str
    vault_pda: str
    policy_pda: str
    delegation_pubkey: str
    # Pending-row id; frontend POSTs this back after Phantom confirms,
    # along with the tx signature, so the backend can finalise.
    pending_id: str


class FinaliseVaultRequest(BaseModel):
    pending_id: str
    tx_signature: str


class VaultRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_pubkey: str
    agent_name: str
    vault_pda: str
    policy_pda: str
    delegation_pubkey: str
    daily_cap_usdc: float
    per_call_cap_usdc: float
    endpoint_allowlist: list[str]
    expires_at: datetime
    paused: bool
    create_tx: str | None
    created_at: datetime


class VaultListResponse(BaseModel):
    vaults: list[VaultRow]


# ─── MCP session ──────────────────────────────────────────────────────


class CreateMCPSessionRequest(BaseModel):
    label: Annotated[str | None, Field(default=None, max_length=120)] = None


class CreateMCPSessionResponse(BaseModel):
    token: str
    label: str | None
    mcp_url: str
    created_at: datetime
