"""`/api/v1/vaults/*` — owner-signed CRUD over agent vaults.

Flow:

  GET    /vaults                              List your vaults
  POST   /vaults/create                       Build unsigned create_vault tx
                                              + persist a pending row
  POST   /vaults/finalise                     Receive the on-chain tx sig
                                              after Phantom confirms;
                                              flip the row to active
  POST   /vaults/{id}/pause                   Build unsigned pause tx
  POST   /vaults/{id}/resume                  Build unsigned resume tx
  POST   /vaults/{id}/clawback                Build unsigned clawback tx
  POST   /vaults/{id}/finalise-action         Generic confirmation hook for
                                              the above three — flips
                                              `paused` in our local cache
"""

from __future__ import annotations

import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from solana.rpc.async_api import AsyncClient
from solders.hash import Hash
from solders.message import Message
from solders.transaction import Transaction
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.auth import OwnerDep
from api.core.crypto import generate_delegation_keypair, wrap
from api.core.db import get_session
from api.core.ix_builder import (
    CreateVaultArgs,
    build_clawback_ix,
    build_create_vault_ix,
    build_pause_ix,
    build_resume_ix,
    derive_associated_token_account,
)
from api.core.models import Vault
from api.core.solana import (
    derive_vault_addresses,
    get_rpc,
    hash_agent_name,
    hash_endpoint,
    usdc_mint,
)
from api.routes.schemas import (
    CreateVaultRequest,
    FinaliseVaultRequest,
    UnsignedTxResponse,
    VaultListResponse,
    VaultRow,
)

router = APIRouter(prefix="/api/v1/vaults", tags=["vaults"])


# ─── helpers ──────────────────────────────────────────────────────────


def _vault_row_to_schema(v: Vault) -> VaultRow:
    return VaultRow(
        id=str(v.id),
        owner_pubkey=v.owner_pubkey,
        agent_name=v.agent_name,
        vault_pda=v.vault_pda,
        policy_pda=v.policy_pda,
        delegation_pubkey=v.delegation_pubkey,
        daily_cap_usdc=v.daily_cap / 1_000_000,
        per_call_cap_usdc=v.per_call_cap / 1_000_000,
        endpoint_allowlist=[e for e in (v.endpoint_allowlist or "").split(",") if e],
        expires_at=v.expires_at,
        paused=v.paused,
        create_tx=v.create_tx,
        created_at=v.created_at,
    )


async def _serialize_unsigned_tx(rpc: AsyncClient, *, payer: str, ixs) -> str:
    """Build a v0-legacy `Transaction` with a fresh recent blockhash and
    return a base64-encoded serialization the frontend can hand to
    Phantom (`solana.signTransaction`).
    """
    from solders.pubkey import Pubkey

    blockhash_resp = await rpc.get_latest_blockhash()
    blockhash: Hash = blockhash_resp.value.blockhash

    payer_pk = Pubkey.from_string(payer)
    msg = Message.new_with_blockhash(ixs, payer_pk, blockhash)
    # Empty signatures placeholder; the wallet fills them in.
    tx = Transaction.new_unsigned(msg)
    return base64.b64encode(bytes(tx)).decode("ascii")


# ─── routes ───────────────────────────────────────────────────────────


@router.get("", response_model=VaultListResponse)
async def list_vaults(
    owner: OwnerDep,
    db: AsyncSession = Depends(get_session),
) -> VaultListResponse:
    res = await db.execute(
        select(Vault).where(Vault.owner_pubkey == owner).order_by(Vault.created_at.desc())
    )
    rows = res.scalars().all()
    return VaultListResponse(vaults=[_vault_row_to_schema(v) for v in rows])


@router.post("/create", response_model=UnsignedTxResponse)
async def create_vault(
    body: CreateVaultRequest,
    owner: OwnerDep,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> UnsignedTxResponse:
    """Build the unsigned `create_vault` tx the wallet will sign + send."""
    from solders.pubkey import Pubkey

    if body.per_call_cap_usdc > body.daily_cap_usdc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "per_call_cap > daily_cap")

    # Derive deterministic agent_id from the requested name.
    agent_id = hash_agent_name(body.agent_name)
    addrs = derive_vault_addresses(Pubkey.from_string(owner), agent_id)

    # Generate a fresh delegation keypair; wrap the private bytes.
    kp = generate_delegation_keypair()
    delegation_pub = kp.pubkey()
    delegation_secret = bytes(kp)  # 64-byte expanded keypair (priv ++ pub)
    wrapped = wrap(delegation_secret)

    allowlist_hashes = [hash_endpoint(h) for h in body.endpoint_allowlist]

    # Persist a "pending" row before building the tx so a successful tx
    # has somewhere to land. We use `vault_pda` as the natural key and let
    # finalise() set `create_tx`.
    existing = (
        await db.execute(select(Vault).where(Vault.vault_pda == str(addrs.vault)))
    ).scalar_one_or_none()
    if existing is not None and existing.owner_pubkey != owner:
        raise HTTPException(status.HTTP_409_CONFLICT, "vault PDA collision")

    if existing is None:
        v = Vault(
            id=uuid.uuid4(),
            owner_pubkey=owner,
            agent_id_hex=agent_id.hex(),
            agent_name=body.agent_name,
            vault_pda=str(addrs.vault),
            policy_pda=str(addrs.policy),
            delegation_pubkey=str(delegation_pub),
            delegation_priv_wrapped=wrapped,
            daily_cap=int(body.daily_cap_usdc * 1_000_000),
            per_call_cap=int(body.per_call_cap_usdc * 1_000_000),
            endpoint_allowlist=",".join(body.endpoint_allowlist),
            expires_at=body.expires_at,
            paused=False,
        )
        db.add(v)
        await db.commit()
        await db.refresh(v)
        existing = v

    ix = build_create_vault_ix(
        owner=Pubkey.from_string(owner),
        usdc_mint=usdc_mint(),
        args=CreateVaultArgs(
            agent_id=agent_id,
            delegation_key=delegation_pub,
            daily_cap=existing.daily_cap,
            per_call_cap=existing.per_call_cap,
            endpoint_allowlist=allowlist_hashes,
            expires_at=int(body.expires_at.timestamp()),
        ),
    )
    tx_b64 = await _serialize_unsigned_tx(get_rpc(), payer=owner, ixs=[ix])

    return UnsignedTxResponse(
        tx_b64=tx_b64,
        vault_pda=str(addrs.vault),
        policy_pda=str(addrs.policy),
        delegation_pubkey=str(delegation_pub),
        pending_id=str(existing.id),
    )


@router.post("/finalise")
async def finalise_vault(
    body: FinaliseVaultRequest,
    owner: OwnerDep,
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    v = (
        await db.execute(select(Vault).where(Vault.id == uuid.UUID(body.pending_id)))
    ).scalar_one_or_none()
    if v is None or v.owner_pubkey != owner:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
    v.create_tx = body.tx_signature
    await db.commit()
    return {"status": "ok", "vault_pda": v.vault_pda, "create_tx": v.create_tx}


# ─── pause / resume / clawback (build-only) ───────────────────────────


async def _vault_or_404(db: AsyncSession, owner: str, vault_id: str) -> Vault:
    try:
        uid = uuid.UUID(vault_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid vault id") from exc

    v = (await db.execute(select(Vault).where(Vault.id == uid))).scalar_one_or_none()
    if v is None or v.owner_pubkey != owner:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "vault not found")
    return v


def _agent_id_bytes(v: Vault) -> bytes:
    return bytes.fromhex(v.agent_id_hex)


async def _build_owner_ix_response(
    rpc: AsyncClient, owner: str, ixs
) -> UnsignedTxResponse:
    tx_b64 = await _serialize_unsigned_tx(rpc, payer=owner, ixs=ixs)
    return UnsignedTxResponse(
        tx_b64=tx_b64,
        vault_pda="",
        policy_pda="",
        delegation_pubkey="",
        pending_id="",
    )


@router.post("/{vault_id}/pause", response_model=UnsignedTxResponse)
async def pause_vault(
    vault_id: str,
    owner: OwnerDep,
    db: AsyncSession = Depends(get_session),
) -> UnsignedTxResponse:
    from solders.pubkey import Pubkey

    v = await _vault_or_404(db, owner, vault_id)
    ix = build_pause_ix(owner=Pubkey.from_string(owner), agent_id=_agent_id_bytes(v))
    return await _build_owner_ix_response(get_rpc(), owner, [ix])


@router.post("/{vault_id}/resume", response_model=UnsignedTxResponse)
async def resume_vault(
    vault_id: str,
    owner: OwnerDep,
    db: AsyncSession = Depends(get_session),
) -> UnsignedTxResponse:
    from solders.pubkey import Pubkey

    v = await _vault_or_404(db, owner, vault_id)
    ix = build_resume_ix(owner=Pubkey.from_string(owner), agent_id=_agent_id_bytes(v))
    return await _build_owner_ix_response(get_rpc(), owner, [ix])


@router.post("/{vault_id}/clawback", response_model=UnsignedTxResponse)
async def clawback_vault(
    vault_id: str,
    owner: OwnerDep,
    db: AsyncSession = Depends(get_session),
) -> UnsignedTxResponse:
    from solders.pubkey import Pubkey

    v = await _vault_or_404(db, owner, vault_id)
    owner_ata = derive_associated_token_account(Pubkey.from_string(owner), usdc_mint())
    ix = build_clawback_ix(
        owner=Pubkey.from_string(owner),
        agent_id=_agent_id_bytes(v),
        usdc_mint=usdc_mint(),
        owner_usdc_ata=owner_ata,
    )
    return await _build_owner_ix_response(get_rpc(), owner, [ix])


@router.post("/{vault_id}/mark-paused")
async def mark_paused(
    vault_id: str,
    paused: bool,
    owner: OwnerDep,
    db: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    """UI calls this after Phantom confirms a pause/resume tx so the
    cached `paused` flag matches on-chain reality without us needing a
    log subscription yet.
    """
    v = await _vault_or_404(db, owner, vault_id)
    v.paused = paused
    await db.commit()
    return {"paused": v.paused}
