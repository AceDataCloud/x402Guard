"""Tests for `api.core.crypto` — round-trip wrap/unwrap."""

from __future__ import annotations

import os

import pytest
from api.core import crypto
from cryptography.exceptions import InvalidTag


def test_wrap_unwrap_round_trip() -> None:
    secret = os.urandom(64)
    blob = crypto.wrap(secret)
    assert blob != secret
    assert len(blob) >= 12 + len(secret) + 16  # nonce + ct + tag
    assert crypto.unwrap(blob) == secret


def test_unwrap_rejects_tampered_blob() -> None:
    blob = bytearray(crypto.wrap(b"hello world"))
    blob[-1] ^= 0xFF  # flip a bit in the tag
    with pytest.raises(InvalidTag):
        crypto.unwrap(bytes(blob))


def test_unwrap_rejects_short_blob() -> None:
    with pytest.raises(ValueError):
        crypto.unwrap(b"\x00" * 5)


def test_generate_delegation_keypair_returns_unique_keys() -> None:
    a = crypto.generate_delegation_keypair()
    b = crypto.generate_delegation_keypair()
    assert a.pubkey() != b.pubkey()
