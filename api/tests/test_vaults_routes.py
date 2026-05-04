"""Vault route tests.

We stub `core.solana.get_rpc()` so we don't hit a real Solana RPC. That's
the only piece of state outside our process that route handlers touch;
everything else is local DB + crypto.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from api.app import create_app
from api.core import solana as solana_mod
from fastapi.testclient import TestClient
from nacl.signing import SigningKey
from solders.hash import Hash
from solders.pubkey import Pubkey


@contextmanager
def stub_rpc(monkeypatch_target):
    """Replace `core.solana.get_rpc()` with a mock that returns a fixed
    blockhash so the tx serializer doesn't need network access.
    """
    fake = MagicMock()
    fake.get_latest_blockhash = AsyncMock(
        return_value=MagicMock(value=MagicMock(blockhash=Hash.default()))
    )
    original = solana_mod.get_rpc
    solana_mod.get_rpc = lambda: fake  # type: ignore[assignment]
    # Routes import the helper by name; our `app.routes.vaults` did
    # `from api.core.solana import get_rpc`, so patch the local copy too.
    from api.routes import vaults as vaults_mod

    vaults_mod.get_rpc = lambda: fake  # type: ignore[assignment]
    try:
        yield fake
    finally:
        solana_mod.get_rpc = original  # type: ignore[assignment]
        vaults_mod.get_rpc = original  # type: ignore[assignment]


def _login(client: TestClient) -> tuple[str, str]:
    """Return (pubkey, session_token)."""
    msg = client.get("/api/v1/auth/challenge").json()["message"]
    sk = SigningKey.generate()
    pubkey = str(Pubkey.from_bytes(bytes(sk.verify_key)))
    sig = base64.b64encode(sk.sign(msg.encode()).signature).decode()
    body = client.post(
        "/api/v1/auth/login",
        json={"pubkey": pubkey, "message": msg, "signature": sig},
    ).json()
    return pubkey, body["session_token"]


def test_create_vault_returns_unsigned_tx_and_persists_pending_row() -> None:
    client = TestClient(create_app())
    pubkey, token = _login(client)

    with stub_rpc(None):
        res = client.post(
            "/api/v1/vaults/create",
            headers={"authorization": f"Bearer {token}"},
            json={
                "agent_name": "Claude-Birthday-Helper",
                "daily_cap_usdc": 2.0,
                "per_call_cap_usdc": 0.5,
                "endpoint_allowlist": ["api.acedata.cloud"],
                "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            },
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tx_b64"]
    assert body["vault_pda"]
    assert body["delegation_pubkey"]

    # Vault is listable for the same owner immediately.
    res = client.get(
        "/api/v1/vaults",
        headers={"authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    rows = res.json()["vaults"]
    assert len(rows) == 1
    row = rows[0]
    assert row["owner_pubkey"] == pubkey
    assert row["agent_name"] == "Claude-Birthday-Helper"
    assert row["daily_cap_usdc"] == 2.0
    assert row["per_call_cap_usdc"] == 0.5
    assert row["endpoint_allowlist"] == ["api.acedata.cloud"]


def test_create_vault_rejects_per_call_over_daily() -> None:
    client = TestClient(create_app())
    _, token = _login(client)
    with stub_rpc(None):
        res = client.post(
            "/api/v1/vaults/create",
            headers={"authorization": f"Bearer {token}"},
            json={
                "agent_name": "x",
                "daily_cap_usdc": 1.0,
                "per_call_cap_usdc": 5.0,
                "endpoint_allowlist": ["api.acedata.cloud"],
                "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        )
    assert res.status_code == 400


def test_finalise_records_tx_signature() -> None:
    client = TestClient(create_app())
    _, token = _login(client)
    with stub_rpc(None):
        create = client.post(
            "/api/v1/vaults/create",
            headers={"authorization": f"Bearer {token}"},
            json={
                "agent_name": "Cursor-Helper",
                "daily_cap_usdc": 5.0,
                "per_call_cap_usdc": 1.0,
                "endpoint_allowlist": ["api.acedata.cloud"],
                "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            },
        ).json()

    res = client.post(
        "/api/v1/vaults/finalise",
        headers={"authorization": f"Bearer {token}"},
        json={
            "pending_id": create["pending_id"],
            "tx_signature": "5tx" + "1" * 84,
        },
    )
    assert res.status_code == 200, res.text
    rows = client.get(
        "/api/v1/vaults",
        headers={"authorization": f"Bearer {token}"},
    ).json()["vaults"]
    assert rows[0]["create_tx"] == "5tx" + "1" * 84


def test_pause_resume_clawback_build_unsigned_txs() -> None:
    client = TestClient(create_app())
    _, token = _login(client)

    with stub_rpc(None):
        create = client.post(
            "/api/v1/vaults/create",
            headers={"authorization": f"Bearer {token}"},
            json={
                "agent_name": "Stress-Test-Agent",
                "daily_cap_usdc": 3.0,
                "per_call_cap_usdc": 0.5,
                "endpoint_allowlist": ["api.acedata.cloud"],
                "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        ).json()
        vault_id = create["pending_id"]

        for action in ("pause", "resume", "clawback"):
            res = client.post(
                f"/api/v1/vaults/{vault_id}/{action}",
                headers={"authorization": f"Bearer {token}"},
            )
            assert res.status_code == 200, (action, res.text)
            assert res.json()["tx_b64"]


def test_other_owner_cannot_see_or_act_on_my_vault() -> None:
    client = TestClient(create_app())
    _, token = _login(client)
    with stub_rpc(None):
        create = client.post(
            "/api/v1/vaults/create",
            headers={"authorization": f"Bearer {token}"},
            json={
                "agent_name": "private-agent",
                "daily_cap_usdc": 1.0,
                "per_call_cap_usdc": 0.5,
                "endpoint_allowlist": ["api.acedata.cloud"],
                "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        ).json()
        vid = create["pending_id"]

    # Login as someone else and try to act on the vault.
    _, other_token = _login(client)

    res = client.get(
        "/api/v1/vaults",
        headers={"authorization": f"Bearer {other_token}"},
    )
    assert res.json() == {"vaults": []}

    with stub_rpc(None):
        res = client.post(
            f"/api/v1/vaults/{vid}/pause",
            headers={"authorization": f"Bearer {other_token}"},
        )
    assert res.status_code == 404
