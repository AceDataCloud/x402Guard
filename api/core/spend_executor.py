"""On-chain spend executor.

Given a vault + endpoint + amount, this builds a `spend` ix, signs it
with the vault's delegation key (unwrapped from server-side custody),
and submits it to Solana.

This is the load-bearing piece of the MCP layer — the agent calls
`aceguard.spend` (or `aceguard.pay_for_api`) over MCP, the route handler
calls into here, and a Solana tx happens. Failures are surfaced 1:1 from
the on-chain `VaultError` enum so the agent gets actionable feedback.
"""

from __future__ import annotations

from dataclasses import dataclass

from solders.keypair import Keypair
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.crypto import unwrap
from api.core.ix_builder import (
    SpendArgs,
    build_spend_ix,
    derive_associated_token_account,
)
from api.core.models import SpendRecord, Vault
from api.core.solana import get_rpc, hash_endpoint, usdc_mint


@dataclass(frozen=True)
class SpendResult:
    tx_signature: str
    amount_usdc: float
    nonce: int


@dataclass(frozen=True)
class SpendError(Exception):
    """Raised when the program rejects the spend (or RPC fails)."""

    reason: str
    cluster_message: str | None = None


async def _next_nonce(db: AsyncSession, vault: Vault) -> int:
    """Issue the next strictly-monotonic nonce for this vault.

    We persist the running counter as `MAX(SpendRecord.nonce) + 1` and
    fall back to 1 on the first spend. The on-chain program enforces the
    same rule independently so concurrent backend instances can never
    drift past the chain.
    """
    from sqlalchemy import func, select

    res = await db.execute(
        select(func.max(SpendRecord.nonce)).where(SpendRecord.vault_id == vault.id)
    )
    last = res.scalar()
    return int((last or 0) + 1)


async def _confirm(rpc, signature: str, timeout_s: float = 30.0) -> None:
    """Block until the cluster confirms the tx (or raise on timeout).

    `solana-py >= 0.34` / `solders` typing notes:
    - `get_signature_statuses(...)` requires `Signature` objects, not strings
    - `s.confirmation_status` is a `solders.transaction_status.TransactionConfirmationStatus`
      enum value (not hashable into a `set` of strings). Compare via its
      string repr instead.
    """
    import asyncio

    from solders.signature import Signature

    sig_obj = Signature.from_string(signature)
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        status = await rpc.get_signature_statuses([sig_obj])
        s = status.value[0]
        if s is not None:
            if s.err is not None:
                raise SpendError(reason="cluster_rejected", cluster_message=str(s.err))
            # `confirmation_status` may be a solders enum or a plain string
            # depending on the solana-py / solders version. Coerce to string
            # before membership-checking against the {confirmed,finalized} set.
            cs = str(s.confirmation_status).lower().rsplit(".", 1)[-1]
            if cs in {"confirmed", "finalized"}:
                return
        await asyncio.sleep(0.5)
    raise SpendError(reason="confirm_timeout")


async def execute_spend(
    db: AsyncSession,
    vault: Vault,
    *,
    amount_usdc: float,
    endpoint_host: str,
    recipient: str,
    api_path: str | None = None,
) -> SpendResult:
    """Run a spend end-to-end.

    1. Derive recipient ATA.
    2. Issue next nonce.
    3. Build, sign with delegation key, send.
    4. Wait for confirmation.
    5. Persist a `SpendRecord` mirror row.
    """
    from datetime import UTC, datetime

    if vault.paused:
        raise SpendError(reason="vault_paused")

    rpc = get_rpc()
    amount_units = int(round(amount_usdc * 1_000_000))
    if amount_units <= 0:
        raise SpendError(reason="non_positive_amount")
    if amount_units > vault.per_call_cap:
        raise SpendError(reason="per_call_cap_exceeded")

    try:
        recipient_pk = Pubkey.from_string(recipient)
    except Exception as exc:
        raise SpendError(reason="bad_recipient") from exc

    recipient_ata = derive_associated_token_account(recipient_pk, usdc_mint())
    delegation_secret = unwrap(vault.delegation_priv_wrapped)
    kp = Keypair.from_bytes(delegation_secret)

    nonce = await _next_nonce(db, vault)

    try:
        owner_pk = Pubkey.from_string(vault.owner_pubkey)
    except Exception as exc:
        raise SpendError(reason="bad_owner_pubkey_in_db") from exc

    ix = build_spend_ix(
        delegation_authority=kp.pubkey(),
        owner=owner_pk,
        agent_id=bytes.fromhex(vault.agent_id_hex),
        usdc_mint=usdc_mint(),
        recipient_usdc_ata=recipient_ata,
        args=SpendArgs(
            amount=amount_units,
            endpoint_hash=hash_endpoint(endpoint_host),
            nonce=nonce,
        ),
    )

    bh_resp = await rpc.get_latest_blockhash()
    blockhash = bh_resp.value.blockhash

    msg = Message.new_with_blockhash([ix], kp.pubkey(), blockhash)
    tx = Transaction([kp], msg, blockhash)

    send_resp = await rpc.send_raw_transaction(bytes(tx))
    sig = str(send_resp.value)
    await _confirm(rpc, sig)

    record = SpendRecord(
        vault_id=vault.id,
        nonce=nonce,
        amount=amount_units,
        recipient_pubkey=recipient,
        endpoint_host=endpoint_host,
        tx_signature=sig,
        block_time=datetime.now(UTC),
        api_path=api_path,
    )
    db.add(record)
    await db.commit()

    return SpendResult(tx_signature=sig, amount_usdc=amount_usdc, nonce=nonce)
