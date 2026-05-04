"""Solana RPC + PDA helpers.

Stateless utilities the route handlers compose. The actual transaction
*construction* (instruction encoding, account ordering, signing) lives in
the next PR (`api/core/tx_builder.py`); this file is just the building
blocks (PDA derivation, RPC client, mint resolution) that everything else
needs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache

from solana.rpc.async_api import AsyncClient
from solders.pubkey import Pubkey

from api.core.config import get_settings

# PDA seeds — must match the on-chain definitions in
# `programs/agent_vault/src/state.rs`.
SEED_VAULT = b"vault"
SEED_POLICY = b"policy"


@dataclass(frozen=True)
class VaultAddresses:
    """The two PDAs and the bumps that derive them."""

    vault: Pubkey
    vault_bump: int
    policy: Pubkey
    policy_bump: int


def program_id() -> Pubkey:
    return Pubkey.from_string(get_settings().agent_vault_program_id)


def usdc_mint() -> Pubkey:
    return Pubkey.from_string(get_settings().usdc_mint)


def derive_vault_addresses(owner: Pubkey, agent_id: bytes) -> VaultAddresses:
    """Derive `(vault_pda, policy_pda)` for an owner+agent_id.

    Mirrors the seeds used in the program. Pure function — no RPC.
    """
    if len(agent_id) != 32:
        raise ValueError("agent_id must be 32 bytes")

    vault, vault_bump = Pubkey.find_program_address(
        [SEED_VAULT, bytes(owner), agent_id],
        program_id(),
    )
    policy, policy_bump = Pubkey.find_program_address(
        [SEED_POLICY, bytes(vault)],
        program_id(),
    )
    return VaultAddresses(
        vault=vault,
        vault_bump=vault_bump,
        policy=policy,
        policy_bump=policy_bump,
    )


def hash_endpoint(host: str) -> bytes:
    """`sha256(host)` — the canonical form used in on-chain allowlists.

    Strips scheme + path so the policy doesn't accidentally bind to
    `https://api.acedata.cloud/openai/...` when the user meant the host.
    """
    h = host.strip().lower()
    # tolerate accidental scheme/path
    if "://" in h:
        h = h.split("://", 1)[1]
    h = h.split("/", 1)[0]
    return hashlib.sha256(h.encode("utf-8")).digest()


def hash_agent_name(name: str) -> bytes:
    """Derive a deterministic 32-byte agent_id from a human-readable name."""
    return hashlib.sha256(name.strip().encode("utf-8")).digest()


@lru_cache(maxsize=1)
def _shared_rpc_client() -> AsyncClient:
    """Process-wide async RPC client. Created lazily so test harnesses can
    stub it out before any route handler asks for it.
    """
    return AsyncClient(get_settings().solana_rpc_url, commitment="confirmed")


def get_rpc() -> AsyncClient:
    return _shared_rpc_client()
