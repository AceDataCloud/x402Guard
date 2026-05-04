"""Tests for the health + .well-known endpoints + the FastAPI app factory."""

from __future__ import annotations

import pytest
from api.app import create_app
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_health_returns_ok(client: TestClient) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_well_known_describes_service(client: TestClient) -> None:
    res = client.get("/.well-known/x402guard")
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "x402guard"
    # Hardcoded in conftest
    assert body["agent_vault_program_id"] == "56TbAziiW8pDHFpRsxfnfBUfimBRTMCHw4gwDGw9uPW6"
    assert body["usdc_mint"] == "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"
    assert body["cluster"] in {"devnet", "mainnet"}
