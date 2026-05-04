"""Tests for the instruction encoder.

We don't run a Solana validator here — we just verify the encoder produces
deterministic, well-shaped instructions whose discriminators match the
`global:<method>` Anchor convention.
"""

from __future__ import annotations

import hashlib

from api.core.ix_builder import (
    CreateVaultArgs,
    SpendArgs,
    UpdatePolicyArgs,
    build_clawback_ix,
    build_create_vault_ix,
    build_pause_ix,
    build_resume_ix,
    build_spend_ix,
    build_update_policy_ix,
    derive_associated_token_account,
)
from api.core.solana import (
    derive_vault_addresses,
    hash_agent_name,
    hash_endpoint,
    program_id,
    usdc_mint,
)
from solders.pubkey import Pubkey


def _disc(name: str) -> bytes:
    return hashlib.sha256(f"global:{name}".encode()).digest()[:8]


OWNER = Pubkey.from_string("11111111111111111111111111111112")
DELEGATE = Pubkey.from_string("11111111111111111111111111111113")
RECIPIENT = Pubkey.from_string("11111111111111111111111111111114")


def test_create_vault_ix_has_correct_discriminator_and_account_count() -> None:
    agent_id = hash_agent_name("Test Agent")
    ix = build_create_vault_ix(
        owner=OWNER,
        usdc_mint=usdc_mint(),
        args=CreateVaultArgs(
            agent_id=agent_id,
            delegation_key=DELEGATE,
            daily_cap=2_000_000,
            per_call_cap=500_000,
            endpoint_allowlist=[hash_endpoint("api.acedata.cloud")],
            expires_at=1_900_000_000,
        ),
    )
    assert ix.program_id == program_id()
    assert ix.data[:8] == _disc("create_vault")
    assert len(ix.accounts) == 9


def test_create_vault_args_serialize_in_field_order() -> None:
    agent_id = b"a" * 32
    delegation = Pubkey.from_string("11111111111111111111111111111113")
    allowlist = [b"\x01" * 32, b"\x02" * 32]
    ix = build_create_vault_ix(
        owner=OWNER,
        usdc_mint=usdc_mint(),
        args=CreateVaultArgs(
            agent_id=agent_id,
            delegation_key=delegation,
            daily_cap=1_000_000,
            per_call_cap=500_000,
            endpoint_allowlist=allowlist,
            expires_at=1_999_999_999,
        ),
    )
    body = ix.data[8:]  # strip discriminator
    cursor = 0
    assert body[cursor : cursor + 32] == agent_id
    cursor += 32
    assert body[cursor : cursor + 32] == bytes(delegation)
    cursor += 32
    assert int.from_bytes(body[cursor : cursor + 8], "little") == 1_000_000
    cursor += 8
    assert int.from_bytes(body[cursor : cursor + 8], "little") == 500_000
    cursor += 8
    assert int.from_bytes(body[cursor : cursor + 4], "little") == 2
    cursor += 4
    assert body[cursor : cursor + 32] == allowlist[0]
    cursor += 32
    assert body[cursor : cursor + 32] == allowlist[1]
    cursor += 32
    assert int.from_bytes(body[cursor : cursor + 8], "little", signed=True) == 1_999_999_999


def test_spend_ix_discriminator() -> None:
    agent_id = hash_agent_name("Agent")
    addrs = derive_vault_addresses(OWNER, agent_id)
    recipient_ata = derive_associated_token_account(RECIPIENT, usdc_mint())
    ix = build_spend_ix(
        delegation_authority=DELEGATE,
        owner=OWNER,
        agent_id=agent_id,
        usdc_mint=usdc_mint(),
        recipient_usdc_ata=recipient_ata,
        args=SpendArgs(
            amount=250_000,
            endpoint_hash=hash_endpoint("api.acedata.cloud"),
            nonce=1,
        ),
    )
    assert ix.data[:8] == _disc("spend")
    # Account #2 must be the policy PDA.
    assert ix.accounts[2].pubkey == addrs.policy
    # Delegation must be the lone signer.
    signer_count = sum(1 for a in ix.accounts if a.is_signer)
    assert signer_count == 1
    assert ix.accounts[0].pubkey == DELEGATE
    assert ix.accounts[0].is_signer is True


def test_pause_resume_share_owner_only_layout() -> None:
    agent_id = hash_agent_name("Agent")
    p = build_pause_ix(owner=OWNER, agent_id=agent_id)
    r = build_resume_ix(owner=OWNER, agent_id=agent_id)

    assert p.data[:8] == _disc("pause")
    assert r.data[:8] == _disc("resume")

    for ix in (p, r):
        assert len(ix.accounts) == 3
        assert ix.accounts[0].pubkey == OWNER
        assert ix.accounts[0].is_signer
        assert ix.accounts[1].pubkey == derive_vault_addresses(OWNER, agent_id).vault


def test_update_policy_partial_args_use_option_encoding() -> None:
    agent_id = hash_agent_name("Agent")
    ix = build_update_policy_ix(
        owner=OWNER,
        agent_id=agent_id,
        args=UpdatePolicyArgs(daily_cap=999_000),
    )
    body = ix.data[8:]
    # delegation_key option None
    assert body[0:1] == b"\x00"
    # daily_cap option Some(999_000)
    assert body[1:2] == b"\x01"
    assert int.from_bytes(body[2:10], "little") == 999_000
    # per_call_cap None
    assert body[10:11] == b"\x00"
    # endpoint_allowlist None
    assert body[11:12] == b"\x00"
    # expires_at None
    assert body[12:13] == b"\x00"


def test_clawback_includes_owner_usdc_ata() -> None:
    agent_id = hash_agent_name("Agent")
    owner_ata = derive_associated_token_account(OWNER, usdc_mint())
    ix = build_clawback_ix(
        owner=OWNER,
        agent_id=agent_id,
        usdc_mint=usdc_mint(),
        owner_usdc_ata=owner_ata,
    )
    assert ix.data[:8] == _disc("clawback")
    pubkeys = [a.pubkey for a in ix.accounts]
    assert owner_ata in pubkeys
    assert OWNER in pubkeys
