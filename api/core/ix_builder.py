"""Hand-rolled instruction encoder for the agent_vault Anchor program.

We don't have a generated TypeScript/Python client (the IDL JSON only
gets emitted on `anchor build`, which doesn't run on this CI). Anchor
instruction encoding is well-defined though:

  ix_data = sha256("global:<method_name>")[:8]  # discriminator
            ++ borsh-encoded args struct

We re-implement just the discriminator + args we need. The accounts
order **must** match `#[derive(Accounts)]` field order from the program;
we re-derive that here as a single source of truth.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from solders.instruction import AccountMeta, Instruction
from solders.pubkey import Pubkey
from solders.system_program import ID as SYSTEM_PROGRAM_ID
from solders.sysvar import RENT as RENT_SYSVAR_ID

from api.core.solana import (
    derive_vault_addresses,
    program_id,
)

# Match anchor_spl ids (they're well-known constants).
TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")


def _disc(name: str) -> bytes:
    return hashlib.sha256(f"global:{name}".encode()).digest()[:8]


def _u64(n: int) -> bytes:
    if n < 0:
        raise ValueError("u64 cannot be negative")
    return int(n).to_bytes(8, "little", signed=False)


def _i64(n: int) -> bytes:
    return int(n).to_bytes(8, "little", signed=True)


def _opt_u64(n: int | None) -> bytes:
    return b"\x00" if n is None else b"\x01" + _u64(n)


def _opt_i64(n: int | None) -> bytes:
    return b"\x00" if n is None else b"\x01" + _i64(n)


def _opt_pubkey(p: Pubkey | None) -> bytes:
    return b"\x00" if p is None else b"\x01" + bytes(p)


def _vec_hash32(items: Sequence[bytes]) -> bytes:
    if any(len(x) != 32 for x in items):
        raise ValueError("each allowlist entry must be 32 bytes")
    return len(items).to_bytes(4, "little") + b"".join(items)


def _opt_vec_hash32(items: Sequence[bytes] | None) -> bytes:
    return b"\x00" if items is None else b"\x01" + _vec_hash32(items)


def derive_associated_token_account(owner: Pubkey, mint: Pubkey) -> Pubkey:
    """SPL ATA derivation. Avoids importing spl-token just for this."""
    ata, _ = Pubkey.find_program_address(
        [bytes(owner), bytes(TOKEN_PROGRAM_ID), bytes(mint)],
        ASSOCIATED_TOKEN_PROGRAM_ID,
    )
    return ata


# ─── create_vault ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class CreateVaultArgs:
    agent_id: bytes  # 32B
    delegation_key: Pubkey
    daily_cap: int  # USDC base units
    per_call_cap: int
    endpoint_allowlist: Sequence[bytes]  # each 32B
    expires_at: int  # unix seconds


def build_create_vault_ix(
    *,
    owner: Pubkey,
    usdc_mint: Pubkey,
    args: CreateVaultArgs,
) -> Instruction:
    if len(args.agent_id) != 32:
        raise ValueError("agent_id must be 32 bytes")

    addrs = derive_vault_addresses(owner, args.agent_id)
    vault_ata = derive_associated_token_account(addrs.vault, usdc_mint)

    data = _disc("create_vault") + (
        bytes(args.agent_id)
        + bytes(args.delegation_key)
        + _u64(args.daily_cap)
        + _u64(args.per_call_cap)
        + _vec_hash32(args.endpoint_allowlist)
        + _i64(args.expires_at)
    )

    accounts = [
        AccountMeta(pubkey=owner, is_signer=True, is_writable=True),
        AccountMeta(pubkey=addrs.vault, is_signer=False, is_writable=True),
        AccountMeta(pubkey=addrs.policy, is_signer=False, is_writable=True),
        AccountMeta(pubkey=usdc_mint, is_signer=False, is_writable=False),
        AccountMeta(pubkey=vault_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=SYSTEM_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=ASSOCIATED_TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=RENT_SYSVAR_ID, is_signer=False, is_writable=False),
    ]
    return Instruction(program_id=program_id(), accounts=accounts, data=data)


# ─── spend ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SpendArgs:
    amount: int
    endpoint_hash: bytes  # 32B
    nonce: int


def build_spend_ix(
    *,
    delegation_authority: Pubkey,
    owner: Pubkey,
    agent_id: bytes,
    usdc_mint: Pubkey,
    recipient_usdc_ata: Pubkey,
    args: SpendArgs,
) -> Instruction:
    if len(args.endpoint_hash) != 32:
        raise ValueError("endpoint_hash must be 32 bytes")
    addrs = derive_vault_addresses(owner, agent_id)
    vault_ata = derive_associated_token_account(addrs.vault, usdc_mint)

    data = _disc("spend") + (
        _u64(args.amount) + bytes(args.endpoint_hash) + _u64(args.nonce)
    )

    accounts = [
        AccountMeta(pubkey=delegation_authority, is_signer=True, is_writable=False),
        AccountMeta(pubkey=addrs.vault, is_signer=False, is_writable=False),
        AccountMeta(pubkey=addrs.policy, is_signer=False, is_writable=True),
        AccountMeta(pubkey=usdc_mint, is_signer=False, is_writable=False),
        AccountMeta(pubkey=vault_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=recipient_usdc_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=ASSOCIATED_TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
        AccountMeta(pubkey=SYSTEM_PROGRAM_ID, is_signer=False, is_writable=False),
    ]
    return Instruction(program_id=program_id(), accounts=accounts, data=data)


# ─── owner ops ────────────────────────────────────────────────────────

def _owner_only_accounts(owner: Pubkey, vault: Pubkey, policy: Pubkey) -> list[AccountMeta]:
    return [
        AccountMeta(pubkey=owner, is_signer=True, is_writable=False),
        AccountMeta(pubkey=vault, is_signer=False, is_writable=False),
        AccountMeta(pubkey=policy, is_signer=False, is_writable=True),
    ]


def build_pause_ix(*, owner: Pubkey, agent_id: bytes) -> Instruction:
    addrs = derive_vault_addresses(owner, agent_id)
    return Instruction(
        program_id=program_id(),
        accounts=_owner_only_accounts(owner, addrs.vault, addrs.policy),
        data=_disc("pause"),
    )


def build_resume_ix(*, owner: Pubkey, agent_id: bytes) -> Instruction:
    addrs = derive_vault_addresses(owner, agent_id)
    return Instruction(
        program_id=program_id(),
        accounts=_owner_only_accounts(owner, addrs.vault, addrs.policy),
        data=_disc("resume"),
    )


@dataclass(frozen=True)
class UpdatePolicyArgs:
    delegation_key: Pubkey | None = None
    daily_cap: int | None = None
    per_call_cap: int | None = None
    endpoint_allowlist: Sequence[bytes] | None = None
    expires_at: int | None = None


def build_update_policy_ix(
    *,
    owner: Pubkey,
    agent_id: bytes,
    args: UpdatePolicyArgs,
) -> Instruction:
    addrs = derive_vault_addresses(owner, agent_id)
    data = _disc("update_policy") + (
        _opt_pubkey(args.delegation_key)
        + _opt_u64(args.daily_cap)
        + _opt_u64(args.per_call_cap)
        + _opt_vec_hash32(args.endpoint_allowlist)
        + _opt_i64(args.expires_at)
    )
    return Instruction(
        program_id=program_id(),
        accounts=_owner_only_accounts(owner, addrs.vault, addrs.policy),
        data=data,
    )


def build_clawback_ix(
    *,
    owner: Pubkey,
    agent_id: bytes,
    usdc_mint: Pubkey,
    owner_usdc_ata: Pubkey,
) -> Instruction:
    addrs = derive_vault_addresses(owner, agent_id)
    vault_ata = derive_associated_token_account(addrs.vault, usdc_mint)
    accounts = [
        AccountMeta(pubkey=owner, is_signer=True, is_writable=True),
        AccountMeta(pubkey=addrs.vault, is_signer=False, is_writable=False),
        AccountMeta(pubkey=addrs.policy, is_signer=False, is_writable=True),
        AccountMeta(pubkey=usdc_mint, is_signer=False, is_writable=False),
        AccountMeta(pubkey=vault_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=owner_usdc_ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=TOKEN_PROGRAM_ID, is_signer=False, is_writable=False),
    ]
    return Instruction(
        program_id=program_id(),
        accounts=accounts,
        data=_disc("clawback"),
    )
