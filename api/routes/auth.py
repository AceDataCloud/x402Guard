"""`/api/v1/auth/*` — Phantom-signed login."""

from __future__ import annotations

from fastapi import APIRouter

from api.core.auth import (
    SESSION_LIFETIME_SECONDS,
    issue_session,
    make_challenge,
    verify_phantom_signature,
)
from api.routes.schemas import ChallengeResponse, LoginRequest, LoginResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.get("/challenge", response_model=ChallengeResponse)
async def challenge() -> ChallengeResponse:
    """Step 1: client requests an unsigned challenge.

    Caller is expected to ask Phantom (`signMessage`) to sign the
    `message` field, then POST it back to `/login`.
    """
    nonce, message = make_challenge()
    return ChallengeResponse(nonce=nonce, message=message)


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest) -> LoginResponse:
    """Step 2: verify the signature, mint a 24h Bearer token."""
    verify_phantom_signature(req.pubkey, req.message, req.signature)
    return LoginResponse(
        session_token=issue_session(req.pubkey),
        pubkey=req.pubkey,
        expires_in=SESSION_LIFETIME_SECONDS,
    )
