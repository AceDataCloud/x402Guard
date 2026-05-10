"""`/mcp/{token}` — Streamable HTTP MCP endpoint.

This is the URL the user pastes into Claude Desktop / Cursor / any
MCP-compatible client. The token authenticates a single vault — the
agent never sees `Authorization` headers; just hits a URL.

Wire format: JSON-RPC 2.0 over HTTP POST. Methods we implement:

  initialize          handshake, return server capabilities + tool count
  tools/list          enumerate the four tools below
  tools/call          dispatch a single tool by name

Tools exposed:

  aceguard.balance        returns vault USDC balance + remaining daily cap
  aceguard.history        recent spends with tx links
  aceguard.spend          { amount_usdc, recipient, endpoint_host }
                          → builds + signs + sends a Solana spend tx
  aceguard.pay_for_api    full x402 dance: the agent gives an API URL +
                          method + body; we hit it, parse the 402, run
                          spend(), retry with X-Payment header, return
                          the upstream JSON to the agent
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from solders.pubkey import Pubkey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.db import get_session
from api.core.ix_builder import derive_associated_token_account
from api.core.models import MCPSession, SpendRecord, Vault
from api.core.solana import get_rpc, usdc_mint
from api.core.spend_executor import SpendError, execute_spend

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ─── tool definitions ────────────────────────────────────────────────


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "aceguard_balance",
            "description": (
                "Return the agent vault's current USDC balance + how much of "
                "today's spending cap is still available. Use this before any "
                "spend to know whether you can afford it."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        {
            "name": "aceguard_history",
            "description": (
                "Return the most recent spends from this vault, with on-chain "
                "tx signatures. Useful to confirm a payment landed."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "aceguard_spend",
            "description": (
                "Send USDC from the agent vault to a recipient on Solana. "
                "Returns a tx signature. The on-chain program will reject the "
                "spend if it violates the user-defined policy (per-call cap, "
                "daily cap, endpoint allowlist, paused, expired)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "amount_usdc": {"type": "number", "minimum": 0.000001},
                    "recipient": {
                        "type": "string",
                        "description": "Solana wallet address (base58)",
                    },
                    "endpoint_host": {
                        "type": "string",
                        "description": (
                            "The hostname of the API you are paying for. "
                            "Must match an entry in the vault's policy "
                            "allowlist (e.g. 'api.acedata.cloud')."
                        ),
                    },
                },
                "required": ["amount_usdc", "recipient", "endpoint_host"],
                "additionalProperties": False,
            },
        },
        {
            "name": "aceguard_pay_for_api",
            "description": (
                "End-to-end x402 wrapper for an HTTP API call. Given a URL "
                "(must be on the vault's allowlist), this tool will: (1) hit "
                "it, (2) read the 402 Payment Required response, (3) make the "
                "Solana payment, (4) retry the call with the X-Payment header, "
                "and (5) return the upstream JSON. You should prefer this "
                "over Bash whenever you need to call a paid API."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "format": "uri"},
                    "method": {"type": "string", "enum": ["GET", "POST"], "default": "POST"},
                    "json_body": {
                        "type": "object",
                        "description": "Request body (JSON). Optional for GET.",
                    },
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    ]


# ─── helpers ─────────────────────────────────────────────────────────


async def _resolve_session(token: str, db: AsyncSession) -> tuple[MCPSession, Vault]:
    res = await db.execute(
        select(MCPSession, Vault)
        .join(Vault, Vault.id == MCPSession.vault_id)
        .where(MCPSession.token == token, MCPSession.revoked_at.is_(None))
    )
    row = res.first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown or revoked token")
    return row[0], row[1]


def _ok(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    obj: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
    if data is not None:
        obj["error"]["data"] = data
    return obj


def _content_text(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


# ─── tool implementations ────────────────────────────────────────────


async def _tool_balance(db: AsyncSession, vault: Vault) -> dict[str, Any]:
    """Read the vault USDC ATA balance + remaining daily cap."""
    rpc = get_rpc()
    from api.core.solana import derive_vault_addresses
    owner_pk = Pubkey.from_string(vault.owner_pubkey)
    addrs = derive_vault_addresses(owner_pk, bytes.fromhex(vault.agent_id_hex))
    vault_ata = derive_associated_token_account(addrs.vault, usdc_mint())

    balance_usdc = 0.0
    try:
        bal = await rpc.get_token_account_balance(vault_ata)
        # solana-py returns .value with .amount + .decimals
        amt = int(bal.value.amount) if bal.value else 0
        decimals = int(bal.value.decimals) if bal.value else 6
        balance_usdc = amt / (10**decimals)
    except Exception:
        # Account might not exist yet (vault not created on-chain).
        balance_usdc = 0.0

    # Daily remaining is best-computed locally from our SpendRecord
    # rows that match today's UTC day.
    from sqlalchemy import func

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    res = await db.execute(
        select(func.coalesce(func.sum(SpendRecord.amount), 0)).where(
            SpendRecord.vault_id == vault.id,
            SpendRecord.block_time >= today_start,
        )
    )
    spent_today = int(res.scalar() or 0)
    daily_remaining = max(vault.daily_cap - spent_today, 0)

    payload = {
        "balance_usdc": balance_usdc,
        "daily_cap_usdc": vault.daily_cap / 1_000_000,
        "spent_today_usdc": spent_today / 1_000_000,
        "daily_remaining_usdc": daily_remaining / 1_000_000,
        "per_call_cap_usdc": vault.per_call_cap / 1_000_000,
        "endpoint_allowlist": [e for e in (vault.endpoint_allowlist or "").split(",") if e],
        "paused": vault.paused,
        "vault_pda": vault.vault_pda,
    }
    return _content_text(json.dumps(payload, ensure_ascii=False, indent=2))


async def _tool_history(db: AsyncSession, vault: Vault, limit: int = 10) -> dict[str, Any]:
    res = await db.execute(
        select(SpendRecord)
        .where(SpendRecord.vault_id == vault.id)
        .order_by(SpendRecord.block_time.desc())
        .limit(min(max(int(limit or 10), 1), 50))
    )
    rows = res.scalars().all()
    items = [
        {
            "amount_usdc": r.amount / 1_000_000,
            "recipient": r.recipient_pubkey,
            "endpoint": r.endpoint_host,
            "api_path": r.api_path,
            "tx": r.tx_signature,
            "block_time": r.block_time.isoformat(),
            "solscan": f"https://solscan.io/tx/{r.tx_signature}",
        }
        for r in rows
    ]
    return _content_text(json.dumps({"spends": items}, ensure_ascii=False, indent=2))


async def _tool_spend(db: AsyncSession, vault: Vault, args: dict[str, Any]) -> dict[str, Any]:
    try:
        result = await execute_spend(
            db,
            vault,
            amount_usdc=float(args["amount_usdc"]),
            endpoint_host=str(args["endpoint_host"]),
            recipient=str(args["recipient"]),
        )
    except SpendError as exc:
        return _content_text(
            f"spend rejected: {exc.reason}"
            + (f" — {exc.cluster_message}" if exc.cluster_message else ""),
            is_error=True,
        )
    return _content_text(
        json.dumps(
            {
                "tx": result.tx_signature,
                "amount_usdc": result.amount_usdc,
                "nonce": result.nonce,
                "solscan": f"https://solscan.io/tx/{result.tx_signature}",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


async def _tool_pay_for_api(
    db: AsyncSession, vault: Vault, args: dict[str, Any]
) -> dict[str, Any]:
    """Hit a paid HTTP endpoint, parse 402, run spend(), retry."""
    url = args["url"]
    method = args.get("method", "POST").upper()
    body = args.get("json_body") or None

    from urllib.parse import urlparse

    host = urlparse(url).hostname or ""

    async with httpx.AsyncClient(timeout=60.0) as client:
        first = await client.request(method, url, json=body)
        if first.status_code != 402:
            # No payment needed — pass through the response.
            try:
                return _content_text(json.dumps(first.json(), ensure_ascii=False, indent=2))
            except Exception:
                return _content_text(first.text)

        # Parse x402 payment requirements.
        try:
            requirements = first.json().get("accepts") or first.json().get(
                "paymentRequirements"
            )
        except Exception:
            return _content_text(
                f"endpoint returned 402 with non-JSON body: {first.text[:400]}",
                is_error=True,
            )
        if not requirements:
            return _content_text(
                "endpoint returned 402 but no `accepts` array",
                is_error=True,
            )

        # Pick the first Solana option.
        chosen = next(
            (r for r in requirements if str(r.get("network", "")).lower() == "solana"),
            None,
        )
        if chosen is None:
            return _content_text(
                "endpoint does not accept Solana settlement", is_error=True
            )

        amount_units = int(chosen.get("maxAmountRequired") or chosen.get("amount") or 0)
        if amount_units <= 0:
            return _content_text("payment requirement missing amount", is_error=True)
        amount_usdc = amount_units / 1_000_000
        pay_to = chosen.get("payTo") or chosen.get("payee")
        if not pay_to:
            return _content_text("payment requirement missing payTo", is_error=True)

        try:
            result = await execute_spend(
                db,
                vault,
                amount_usdc=amount_usdc,
                endpoint_host=host,
                recipient=pay_to,
                api_path=urlparse(url).path,
            )
        except SpendError as exc:
            return _content_text(
                f"on-chain spend rejected: {exc.reason}"
                + (f" — {exc.cluster_message}" if exc.cluster_message else ""),
                is_error=True,
            )

        # Construct an X-Payment header that the facilitator understands.
        # The facilitator (FacilitatorX402) is x402-spec compliant: it matches
        # `scheme="exact"` + `network="solana"` and reads the on-chain tx
        # signature out of `payload.signature`. See
        # https://github.com/AceDataCloud/FacilitatorX402 (`solana_chain.py
        # ::_extract_signature`).
        envelope = {
            "x402Version": 1,
            "scheme": "exact",
            "network": "solana",
            "payload": {"signature": result.tx_signature},
        }
        x_payment = base64.b64encode(json.dumps(envelope).encode()).decode()

        retry = await client.request(
            method, url, json=body, headers={"X-Payment": x_payment}
        )
        try:
            response_json = retry.json()
        except Exception:
            return _content_text(
                f"upstream returned {retry.status_code} non-JSON: {retry.text[:400]}",
                is_error=retry.status_code >= 400,
            )

        return _content_text(
            json.dumps(
                {
                    "x402_paid_usdc": amount_usdc,
                    "x402_tx": result.tx_signature,
                    "x402_solscan": f"https://solscan.io/tx/{result.tx_signature}",
                    "upstream_status": retry.status_code,
                    "upstream_response": response_json,
                },
                ensure_ascii=False,
                indent=2,
            ),
            is_error=retry.status_code >= 400,
        )


# ─── route ───────────────────────────────────────────────────────────


@router.post("/{token}")
async def streamable_http_mcp(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    session, vault = await _resolve_session(token, db)

    # Update last_used_at; cheap, fire-and-forget.
    session.last_used_at = datetime.now(UTC)

    body = await request.json()
    if not isinstance(body, dict):
        return _err(None, -32600, "invalid request: not a JSON object")

    method = body.get("method")
    req_id = body.get("id")
    params = body.get("params") or {}

    if method == "initialize":
        return _ok(
            req_id,
            {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "x402guard", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        )

    if method == "tools/list":
        return _ok(req_id, {"tools": _tool_definitions()})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            if name == "aceguard_balance":
                result = await _tool_balance(db, vault)
            elif name == "aceguard_history":
                result = await _tool_history(db, vault, int(args.get("limit") or 10))
            elif name == "aceguard_spend":
                result = await _tool_spend(db, vault, args)
            elif name == "aceguard_pay_for_api":
                result = await _tool_pay_for_api(db, vault, args)
            else:
                return _err(req_id, -32601, f"unknown tool: {name}")
        except Exception as exc:  # noqa: BLE001
            return _err(req_id, -32000, "tool exception", {"detail": repr(exc)})
        await db.commit()
        return _ok(req_id, result)

    if method in {"notifications/initialized", "ping"}:
        return _ok(req_id, {})

    return _err(req_id, -32601, f"method not implemented: {method}")
