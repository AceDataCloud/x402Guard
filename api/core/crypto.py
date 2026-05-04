"""Delegation key custody.

The vault's `delegation_key` is the only signer the on-chain `spend` ix
will accept. It must live somewhere — for the hackathon it lives server-
side, encrypted at rest with AES-256-GCM under a master key derived from
`CONNECTION_VAULT_KEY`.

V2 (post-hackathon) replaces this with browser-held WebAuthn passkeys.
The interface here (`wrap` + `unwrap`) deliberately mirrors what the
WebAuthn flow will provide so the swap is local.
"""

from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from solders.keypair import Keypair

from api.core.config import get_settings


def _master_key() -> bytes:
    """Resolve the 32-byte AES-256-GCM master key from settings.

    The setting is hex; we tolerate a missing setting in dev by deriving a
    deterministic local key — production must set a real one.
    """
    raw = get_settings().connection_vault_key
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise RuntimeError("CONNECTION_VAULT_KEY must be hex") from exc
    if len(key) != 32:
        raise RuntimeError(f"CONNECTION_VAULT_KEY must decode to 32 bytes (got {len(key)})")
    return key


def wrap(plaintext: bytes) -> bytes:
    """Encrypt `plaintext` under the master key.

    Returned blob: `[12B nonce][ciphertext+16B tag]` — AES-GCM authenticated.
    Storable as-is in a `bytes` column.
    """
    aes = AESGCM(_master_key())
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext, associated_data=b"x402guard-delegation-v1")
    return nonce + ct


def unwrap(blob: bytes) -> bytes:
    """Inverse of `wrap`. Raises on tag mismatch or wrong key."""
    aes = AESGCM(_master_key())
    if len(blob) < 12 + 16:
        raise ValueError("blob too short")
    nonce, ct = blob[:12], blob[12:]
    return aes.decrypt(nonce, ct, associated_data=b"x402guard-delegation-v1")


def generate_delegation_keypair() -> Keypair:
    """Fresh Ed25519 keypair the vault's policy will register."""
    return Keypair()
