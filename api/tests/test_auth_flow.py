"""Auth round-trip: challenge → Phantom-style sign → login → verify session."""

from __future__ import annotations

import base64

from api.app import create_app
from fastapi.testclient import TestClient
from nacl.signing import SigningKey
from solders.pubkey import Pubkey


def test_full_login_flow_round_trips() -> None:
    client = TestClient(create_app())

    # 1. challenge
    res = client.get("/api/v1/auth/challenge")
    assert res.status_code == 200
    msg = res.json()["message"]
    assert "x402guard" in msg

    # 2. simulate Phantom: a fresh Ed25519 keypair signs the message
    sk = SigningKey.generate()
    vk = sk.verify_key
    pubkey = str(Pubkey.from_bytes(bytes(vk)))
    sig = sk.sign(msg.encode("utf-8")).signature
    sig_b64 = base64.b64encode(sig).decode()

    res = client.post(
        "/api/v1/auth/login",
        json={"pubkey": pubkey, "message": msg, "signature": sig_b64},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pubkey"] == pubkey
    token = body["session_token"]
    assert token

    # 3. token works on a protected route
    res = client.get(
        "/api/v1/vaults",
        headers={"authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json() == {"vaults": []}


def test_login_rejects_bogus_signature() -> None:
    client = TestClient(create_app())

    challenge = client.get("/api/v1/auth/challenge").json()
    pubkey = str(Pubkey.from_bytes(bytes(SigningKey.generate().verify_key)))
    res = client.post(
        "/api/v1/auth/login",
        json={
            "pubkey": pubkey,
            "message": challenge["message"],
            "signature": base64.b64encode(b"\x00" * 64).decode(),
        },
    )
    assert res.status_code == 401


def test_protected_route_requires_bearer() -> None:
    client = TestClient(create_app())
    res = client.get("/api/v1/vaults")
    assert res.status_code == 401


def test_session_signed_with_wrong_secret_rejected() -> None:
    client = TestClient(create_app())
    res = client.get(
        "/api/v1/vaults",
        headers={"authorization": "Bearer not.a.real.token"},
    )
    assert res.status_code == 401
