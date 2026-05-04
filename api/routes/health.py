"""Liveness + readiness."""

from __future__ import annotations

from fastapi import APIRouter

from api import __version__
from api.core.config import get_settings
from api.core.solana import program_id, usdc_mint

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    """Cheap liveness check used by load balancers + smoke tests."""
    return {"status": "ok", "version": __version__}


@router.get("/.well-known/x402guard")
async def well_known() -> dict[str, object]:
    """Self-describing endpoint clients can hit to discover network +
    program + USDC mint without consulting docs.
    """
    s = get_settings()
    return {
        "service": "x402guard",
        "version": __version__,
        "cluster": s.solana_cluster,
        "rpc_url_redacted": (
            s.solana_rpc_url.split("?", 1)[0]  # strip API key query param if any
        ),
        "agent_vault_program_id": str(program_id()),
        "usdc_mint": str(usdc_mint()),
    }
