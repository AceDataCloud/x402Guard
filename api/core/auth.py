"""Phantom signature → x402guard session.

Phantom signs an opaque challenge with the user's wallet keypair; we
verify the Ed25519 signature and mint an opaque session token bound to
that pubkey. The session is the only thing required to call the rest of
`/api/v1/vaults/*` — there's no traditional username/password.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from solders.pubkey import Pubkey

from api.core.config import get_settings

# We don't store sessions in the DB — they're stateless HMAC tokens, like
# JWTs but without the version-skew gotchas. Session lifetime is 24h;
# users who care about long-lived sessions can refresh by re-signing.
SESSION_LIFETIME_SECONDS = 24 * 3600

# A fixed challenge prefix so a signature obtained for some other Solana
# dapp can't be replayed against us. Phantom shows the user this exact
# bytestring at signing time.
CHALLENGE_TEMPLATE = "x402guard | sign in to manage your AI agent vaults | nonce={nonce}"


def make_challenge() -> tuple[str, str]:
    """Return `(nonce, message)` to display to the user. Nonce is a random
    16-byte hex string; message is what Phantom signs.
    """
    nonce = secrets.token_hex(16)
    return nonce, CHALLENGE_TEMPLATE.format(nonce=nonce)


def verify_phantom_signature(
    pubkey: str,
    message: str,
    signature_b64: str,
) -> None:
    """Raise HTTPException(401) on any failure path. On success, returns
    quietly — the caller can trust the pubkey afterwards.
    """
    try:
        pk = Pubkey.from_string(pubkey)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "malformed pubkey") from exc

    try:
        sig = base64.b64decode(signature_b64)
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "malformed signature") from exc

    try:
        VerifyKey(bytes(pk)).verify(message.encode("utf-8"), sig)
    except BadSignatureError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "signature mismatch") from exc


# ─── Stateless session token (HMAC-SHA256) ────────────────────────────

def _hmac(payload: bytes) -> bytes:
    secret = get_settings().app_secret_key.encode("utf-8")
    return hmac.new(secret, payload, hashlib.sha256).digest()


def issue_session(pubkey: str) -> str:
    """Mint an opaque session token: `b64(payload).b64(hmac)`."""
    payload = json.dumps(
        {"pubkey": pubkey, "exp": int(time.time()) + SESSION_LIFETIME_SECONDS},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    sig = _hmac(payload)
    return f"{base64.urlsafe_b64encode(payload).decode().rstrip('=')}." \
           f"{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"


def _b64decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def verify_session(token: str) -> str:
    """Return the pubkey embedded in the token, or raise 401."""
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = _b64decode(payload_b64)
        sig = _b64decode(sig_b64)
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "malformed session") from exc

    if not hmac.compare_digest(_hmac(payload), sig):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session signature mismatch")

    try:
        body = json.loads(payload)
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "malformed session payload") from exc

    if int(body.get("exp", 0)) < int(time.time()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired")

    pubkey = body.get("pubkey")
    if not isinstance(pubkey, str):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing pubkey claim")
    return pubkey


# ─── FastAPI dependency ───────────────────────────────────────────────

def auth_required(request: Request) -> str:
    """Extract the Bearer session token and return the verified owner pubkey.

    Use as `owner: str = Depends(auth_required)` in any vault route.
    """
    raw = request.headers.get("authorization", "")
    if not raw.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return verify_session(raw[7:].strip())


# Type alias for the FastAPI signature.
OwnerDep = Annotated[str, Depends(auth_required)]
