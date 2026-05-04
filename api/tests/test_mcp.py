"""Tests for the MCP endpoint at `/mcp/{token}`.

We never let the MCP route hit Solana for real — the spend-related tools
get monkey-patched to a mock `execute_spend` that records the call and
returns a fake tx signature. That isolates the JSON-RPC plumbing from
on-chain semantics (which are exhaustively tested by the Anchor test
suite).
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from api.app import create_app
from api.core import solana as solana_mod
from api.core.db import SessionLocal
from api.core.models import MCPSession, Vault
from api.core.spend_executor import SpendResult
from fastapi.testclient import TestClient
from nacl.signing import SigningKey
from solders.hash import Hash
from solders.pubkey import Pubkey


@pytest.fixture
def stub_rpc(monkeypatch):  # type: ignore[no-untyped-def]
    fake = MagicMock()
    fake.get_latest_blockhash = AsyncMock(
        return_value=MagicMock(value=MagicMock(blockhash=Hash.default()))
    )
    fake.get_token_account_balance = AsyncMock(
        return_value=MagicMock(value=MagicMock(amount="3500000", decimals=6))
    )
    monkeypatch.setattr(solana_mod, "get_rpc", lambda: fake)
    from api.routes import mcp as mcp_mod
    from api.routes import vaults as vaults_mod

    monkeypatch.setattr(mcp_mod, "get_rpc", lambda: fake)
    monkeypatch.setattr(vaults_mod, "get_rpc", lambda: fake)
    return fake


def _login(client: TestClient) -> tuple[str, str]:
    msg = client.get("/api/v1/auth/challenge").json()["message"]
    sk = SigningKey.generate()
    pubkey = str(Pubkey.from_bytes(bytes(sk.verify_key)))
    sig = base64.b64encode(sk.sign(msg.encode()).signature).decode()
    body = client.post(
        "/api/v1/auth/login",
        json={"pubkey": pubkey, "message": msg, "signature": sig},
    ).json()
    return pubkey, body["session_token"]


async def _seed_vault_and_session() -> tuple[str, Vault, MCPSession]:
    """Insert a vault + active MCP session directly via the ORM so we
    don't have to drive the full Phantom + Solana flow in every test.
    Returns the session token.
    """
    async with SessionLocal() as s:
        sk = SigningKey.generate()
        owner_pubkey = str(Pubkey.from_bytes(bytes(sk.verify_key)))
        suffix = uuid.uuid4().hex[:6]

        v = Vault(
            id=uuid.uuid4(),
            owner_pubkey=owner_pubkey,
            agent_id_hex="ee" * 32,
            agent_name="Demo Agent",
            vault_pda=f"HxK8DemoVault{suffix}" + "1" * (43 - 13 - len(suffix)),
            policy_pda=f"JxK8DemoPol{suffix}" + "1" * (44 - 11 - len(suffix)),
            delegation_pubkey=f"DxK8Deleg{suffix}" + "1" * (43 - 9 - len(suffix)),
            delegation_priv_wrapped=b"\x00" * 100,
            daily_cap=2_000_000,
            per_call_cap=500_000,
            endpoint_allowlist="api.acedata.cloud",
            expires_at=datetime.now(UTC) + timedelta(days=7),
            paused=False,
        )
        sess = MCPSession(
            token="testtoken-" + uuid.uuid4().hex,
            vault_id=v.id,
            label="default",
        )
        s.add_all([v, sess])
        await s.commit()
        await s.refresh(v)
        await s.refresh(sess)
        return sess.token, v, sess


@pytest.mark.asyncio
async def test_initialize_returns_server_info() -> None:
    token, _, _ = await _seed_vault_and_session()
    client = TestClient(create_app())
    res = client.post(
        f"/mcp/{token}",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["result"]["serverInfo"]["name"] == "x402guard"
    assert "tools" in body["result"]["capabilities"]


@pytest.mark.asyncio
async def test_tools_list_exposes_four_tools() -> None:
    token, _, _ = await _seed_vault_and_session()
    client = TestClient(create_app())
    res = client.post(
        f"/mcp/{token}",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    body = res.json()
    names = {t["name"] for t in body["result"]["tools"]}
    assert names == {
        "aceguard_balance",
        "aceguard_history",
        "aceguard_spend",
        "aceguard_pay_for_api",
    }


@pytest.mark.asyncio
async def test_balance_tool_returns_structured_payload(
    stub_rpc,  # type: ignore[no-untyped-def]
) -> None:
    token, _, _ = await _seed_vault_and_session()
    client = TestClient(create_app())
    res = client.post(
        f"/mcp/{token}",
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "aceguard_balance", "arguments": {}},
        },
    )
    body = res.json()
    text = body["result"]["content"][0]["text"]
    payload = json.loads(text)
    assert payload["balance_usdc"] == 3.5  # 3,500,000 / 1e6
    assert payload["daily_cap_usdc"] == 2.0
    assert payload["per_call_cap_usdc"] == 0.5
    assert payload["paused"] is False


@pytest.mark.asyncio
async def test_spend_tool_dispatches_to_executor(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    token, _, _ = await _seed_vault_and_session()

    async def fake_execute_spend(db, vault, **kwargs):  # type: ignore[no-untyped-def]
        return SpendResult(
            tx_signature="5fak" + "e" * 84,
            amount_usdc=float(kwargs["amount_usdc"]),
            nonce=1,
        )

    from api.routes import mcp as mcp_mod

    monkeypatch.setattr(mcp_mod, "execute_spend", fake_execute_spend)

    client = TestClient(create_app())
    res = client.post(
        f"/mcp/{token}",
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "aceguard_spend",
                "arguments": {
                    "amount_usdc": 0.025,
                    "recipient": "11111111111111111111111111111112",
                    "endpoint_host": "api.acedata.cloud",
                },
            },
        },
    )
    payload = json.loads(res.json()["result"]["content"][0]["text"])
    assert payload["amount_usdc"] == 0.025
    assert payload["tx"].startswith("5fake")


@pytest.mark.asyncio
async def test_unknown_token_rejected() -> None:
    client = TestClient(create_app())
    res = client.post(
        "/mcp/no-such-token",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_unknown_tool_returns_jsonrpc_error() -> None:
    token, _, _ = await _seed_vault_and_session()
    client = TestClient(create_app())
    res = client.post(
        f"/mcp/{token}",
        json={
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "totally_unknown_tool", "arguments": {}},
        },
    )
    body = res.json()
    assert body["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_pay_for_api_runs_full_x402_dance(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    token, _, _ = await _seed_vault_and_session()

    # Stub execute_spend so we don't actually hit Solana.
    async def fake_execute_spend(db, vault, **kwargs):  # type: ignore[no-untyped-def]
        return SpendResult(
            tx_signature="6sig" + "f" * 84,
            amount_usdc=float(kwargs["amount_usdc"]),
            nonce=2,
        )

    from api.routes import mcp as mcp_mod

    monkeypatch.setattr(mcp_mod, "execute_spend", fake_execute_spend)

    # Stub the upstream API: first call returns 402, second (with X-Payment)
    # returns 200 with our happy-path body.
    calls: list[httpx.Request] = []

    async def transport_handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if "x-payment" in {h.lower() for h in request.headers}:
            return httpx.Response(
                200, json={"image_url": "https://cdn.acedata.cloud/birthday.jpg"}
            )
        return httpx.Response(
            402,
            json={
                "x402Version": 1,
                "accepts": [
                    {
                        "scheme": "solana",
                        "network": "solana",
                        "maxAmountRequired": "25000",  # 0.025 USDC
                        "payTo": "11111111111111111111111111111112",
                        "asset": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(transport_handler)
    real_async_client_cls = httpx.AsyncClient

    class _PatchedAsyncClient(real_async_client_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    from api.routes import mcp as mcp_mod

    monkeypatch.setattr(mcp_mod.httpx, "AsyncClient", _PatchedAsyncClient)

    client = TestClient(create_app())
    res = client.post(
        f"/mcp/{token}",
        json={
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "aceguard_pay_for_api",
                "arguments": {
                    "url": "https://api.acedata.cloud/midjourney/imagine",
                    "method": "POST",
                    "json_body": {"prompt": "birthday card"},
                },
            },
        },
    )
    body = res.json()
    assert "result" in body, body  # bubble up the error in test output
    payload = json.loads(body["result"]["content"][0]["text"])
    assert payload["x402_paid_usdc"] == 0.025
    assert payload["x402_tx"].startswith("6sig")
    assert payload["upstream_response"]["image_url"].endswith(".jpg")
    # Both upstream calls happened — first 402, then 200 with X-Payment.
    assert len(calls) == 2
    assert any("x-payment" in {h.lower() for h in c.headers} for c in calls)
