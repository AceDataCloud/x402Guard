"""Tests for `api.core.solana` — pure helpers, no RPC."""

from __future__ import annotations

from api.core.solana import (
    derive_vault_addresses,
    hash_agent_name,
    hash_endpoint,
    program_id,
    usdc_mint,
)
from solders.pubkey import Pubkey


def test_program_id_and_usdc_mint_are_valid_pubkeys() -> None:
    # Both should round-trip through Pubkey without raising.
    Pubkey.from_string(str(program_id()))
    Pubkey.from_string(str(usdc_mint()))


def test_derive_vault_addresses_is_deterministic() -> None:
    owner = Pubkey.from_string("11111111111111111111111111111112")
    agent = hash_agent_name("Claude-Birthday-Helper")

    a = derive_vault_addresses(owner, agent)
    b = derive_vault_addresses(owner, agent)

    assert a.vault == b.vault
    assert a.vault_bump == b.vault_bump
    assert a.policy == b.policy
    assert a.policy_bump == b.policy_bump


def test_derive_rejects_wrong_agent_id_size() -> None:
    owner = Pubkey.from_string("11111111111111111111111111111112")
    try:
        derive_vault_addresses(owner, b"too-short")
    except ValueError:
        return
    raise AssertionError("expected ValueError for non-32-byte agent_id")


def test_hash_endpoint_normalises_scheme_path_and_case() -> None:
    a = hash_endpoint("api.acedata.cloud")
    b = hash_endpoint("https://api.acedata.cloud/openai/chat/completions")
    c = hash_endpoint("API.AceData.Cloud")
    assert a == b == c
    assert len(a) == 32


def test_hash_agent_name_is_32_bytes() -> None:
    h = hash_agent_name("Claude-Birthday-Helper")
    assert len(h) == 32
    # Same input → same output
    assert h == hash_agent_name("Claude-Birthday-Helper")
    # Different input → different output
    assert h != hash_agent_name("GPT-Birthday-Helper")
