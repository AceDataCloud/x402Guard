#!/usr/bin/env python3
"""Drive an x402guard MCP endpoint from the command line — hand-held demo.

Why this exists
---------------
The MCP endpoint at ``/mcp/<token>`` is plain JSON-RPC over HTTP POST.
Claude Desktop is one client; it is not the only one. If your client
is misconfigured (Claude Desktop only speaks stdio MCP, not HTTP MCP —
you need the ``mcp-remote`` bridge for that) you cannot tell whether
the fault is on the client or the server.

This script answers that question by speaking JSON-RPC to the MCP
endpoint directly. No Claude, no Cursor, no client-side config.

Modes
-----
**Read-only (default)** — confirms the endpoint is healthy:

    python scripts/demo.py https://x402guard.acedata.cloud/mcp/<TOKEN>

  1.  ``tools/list``         — confirm the four aceguard tools are registered
  2.  ``aceguard_balance``   — read on-chain USDC + remaining caps
  3.  ``aceguard_history``   — list recent on-chain spends

**Spend mode** — moves USDC on Solana devnet:

    python scripts/demo.py https://x402guard.acedata.cloud/mcp/<TOKEN> \\
        --spend --recipient <YOUR-PHANTOM-ADDRESS>

  Adds an ``aceguard_spend`` step *between* balance and history. The
  recipient must already have a USDC ATA on devnet (the easiest way:
  use **your own Phantom wallet address** — you created that ATA when
  you minted devnet USDC in README Step 2).

**Pay-for-API mode** — full x402 dance against an upstream API:

    python scripts/demo.py https://x402guard.acedata.cloud/mcp/<TOKEN> \\
        --pay-for-api

  Same shape as ``--spend`` but driven by HTTP-402: upstream returns
  402 → backend invokes ``agent_vault.spend()`` → X-Payment header
  rebuilt from the tx → upstream retried.

  ⚠️  ``api.acedata.cloud`` issues mainnet quotes. The current x402guard
      deploy is on **devnet**, so this mode will fail until the
      mainnet flip (V2 per .plans/X402GUARD.md). It's wired up so
      the moment we flip cluster, this command starts working.

Requires only ``httpx`` and the Python stdlib.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

try:
    import httpx
except ImportError:
    sys.exit(
        "httpx is required. install with: pip install httpx\n"
        "(or run from the api venv: cd api && poetry shell && python ../scripts/demo.py ...)"
    )


DEFAULT_API_URL = "https://api.acedata.cloud/openai/chat/completions"
DEFAULT_BODY: dict[str, Any] = {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "Say hi in 5 words."}],
    "max_tokens": 20,
}
DEFAULT_ENDPOINT_HOST = "api.acedata.cloud"
DEFAULT_SPEND_AMOUNT = 0.01


def _post(client: httpx.Client, mcp_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send one JSON-RPC request, return the parsed response object."""
    resp = client.post(mcp_url, json=payload)
    if resp.status_code == 401:
        sys.exit(
            f"❌ MCP endpoint returned 401 (unknown or revoked token).\n"
            f"   {mcp_url}\n"
            f"   Generate a fresh token in the vault detail page → "
            f"+ New MCP URL → Copy."
        )
    resp.raise_for_status()
    return resp.json()


def _unwrap_tool_result(rpc_response: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return ``(payload, is_error)`` from a tools/call response."""
    if "error" in rpc_response:
        sys.exit(
            f"❌ MCP RPC error: code={rpc_response['error'].get('code')} "
            f"message={rpc_response['error'].get('message')!r} "
            f"data={rpc_response['error'].get('data')!r}"
        )
    result = rpc_response.get("result") or {}
    is_error = bool(result.get("isError"))
    content = result.get("content") or []
    if not content:
        return result, is_error
    text = content[0].get("text") or ""
    try:
        return json.loads(text), is_error
    except json.JSONDecodeError:
        return {"_raw_text": text}, is_error


def _hr(title: str) -> None:
    print()
    print(f"━━━ {title} " + "━" * max(0, 60 - len(title)))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "mcp_url",
        help="Full MCP URL e.g. https://x402guard.acedata.cloud/mcp/<TOKEN>",
    )
    p.add_argument(
        "--spend",
        action="store_true",
        help="Add an aceguard_spend step (requires --recipient).",
    )
    p.add_argument(
        "--recipient",
        help="Solana wallet to receive the spend. Required with --spend. "
        "Tip: use your own Phantom wallet address — its USDC ATA was "
        "already created when you minted devnet USDC, so the spend "
        "won't fail with AccountNotInitialized.",
    )
    p.add_argument(
        "--amount",
        type=float,
        default=DEFAULT_SPEND_AMOUNT,
        help=f"Spend amount in USDC. default: {DEFAULT_SPEND_AMOUNT}",
    )
    p.add_argument(
        "--endpoint-host",
        default=DEFAULT_ENDPOINT_HOST,
        help=f"Endpoint host the spend is for (must be on the vault "
        f"allowlist). default: {DEFAULT_ENDPOINT_HOST}",
    )
    p.add_argument(
        "--pay-for-api",
        action="store_true",
        help="Run the aceguard_pay_for_api flow against --api-url. "
        "NOTE: api.acedata.cloud is mainnet-only as of devnet deploy.",
    )
    p.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"API to pay for in --pay-for-api mode. default: {DEFAULT_API_URL}",
    )
    p.add_argument(
        "--body",
        default=json.dumps(DEFAULT_BODY),
        help="JSON request body for the --pay-for-api call.",
    )
    p.add_argument(
        "--method",
        default="POST",
        choices=["GET", "POST"],
        help="HTTP method for the --pay-for-api call. default: POST",
    )
    return p


def _print_balance(label: str, payload: dict[str, Any]) -> None:
    print(f"  {label}:")
    print(f"    balance_usdc:         {payload.get('balance_usdc')}")
    print(f"    daily_cap_usdc:       {payload.get('daily_cap_usdc')}")
    print(f"    spent_today_usdc:     {payload.get('spent_today_usdc')}")
    print(f"    daily_remaining_usdc: {payload.get('daily_remaining_usdc')}")
    print(f"    per_call_cap_usdc:    {payload.get('per_call_cap_usdc')}")
    print(f"    paused:               {payload.get('paused')}")
    print(f"    vault_pda:            {payload.get('vault_pda')}")
    print(f"    endpoint_allowlist:   {payload.get('endpoint_allowlist')}")


def _print_history(payload: dict[str, Any], limit: int = 5) -> None:
    spends = payload.get("spends") or []
    if not spends:
        print("  (no spends yet — vault has not been used)")
        return
    for sp in spends[:limit]:
        print(
            f"  • {sp.get('block_time')} | {sp.get('amount_usdc')} USDC | "
            f"→ {sp.get('recipient')} | endpoint={sp.get('endpoint')}"
        )
        print(f"    solscan: {sp.get('solscan')}")


def main() -> int:
    args = _build_parser().parse_args()

    if args.spend and not args.recipient:
        sys.exit("❌ --spend requires --recipient <SOLANA-PUBKEY>.")
    if args.amount <= 0:
        sys.exit("❌ --amount must be positive.")

    if args.pay_for_api:
        try:
            body_json = json.loads(args.body)
        except json.JSONDecodeError as exc:
            sys.exit(f"--body is not valid JSON: {exc}")
    else:
        body_json = None

    rpc_id = 0

    def next_id() -> int:
        nonlocal rpc_id
        rpc_id += 1
        return rpc_id

    print(f"x402guard CLI demo — driving MCP at {args.mcp_url!r}")
    if args.spend:
        print(
            f"  mode: --spend  recipient={args.recipient}  "
            f"amount={args.amount} USDC  endpoint={args.endpoint_host}"
        )
    elif args.pay_for_api:
        print(f"  mode: --pay-for-api  url={args.api_url}")
    else:
        print(
            "  mode: read-only "
            "(no on-chain tx; pass --spend or --pay-for-api to do one)"
        )

    with httpx.Client(timeout=180.0) as client:
        # === 1. tools/list — endpoint healthy + auth recognized =============
        _hr("1. tools/list")
        resp = _post(
            client,
            args.mcp_url,
            {"jsonrpc": "2.0", "id": next_id(), "method": "tools/list"},
        )
        tools = (resp.get("result") or {}).get("tools") or []
        if not tools:
            sys.exit("❌ tools/list returned no tools — the endpoint is unhealthy.")
        for t in tools:
            print(f"  • {t.get('name'):28s} — {(t.get('description') or '')[:80]}")

        # === 2. aceguard_balance — read on-chain USDC =======================
        _hr("2. aceguard_balance (before)")
        bal_before, _ = _unwrap_tool_result(
            _post(
                client,
                args.mcp_url,
                {
                    "jsonrpc": "2.0",
                    "id": next_id(),
                    "method": "tools/call",
                    "params": {"name": "aceguard_balance", "arguments": {}},
                },
            )
        )
        _print_balance("vault state", bal_before)

        # === 3. (optional) aceguard_spend OR aceguard_pay_for_api ===========
        spent_ok = False
        if args.spend:
            if bal_before.get("paused"):
                sys.exit("❌ vault is paused. Resume it in the Dapp before retrying.")
            if (bal_before.get("balance_usdc") or 0) < args.amount:
                sys.exit(
                    f"❌ vault balance ({bal_before.get('balance_usdc')} USDC) "
                    f"is below --amount ({args.amount} USDC). Top up via the Dapp."
                )
            _hr(f"3. aceguard_spend  →  {args.amount} USDC → {args.recipient}")
            spend_payload, is_err = _unwrap_tool_result(
                _post(
                    client,
                    args.mcp_url,
                    {
                        "jsonrpc": "2.0",
                        "id": next_id(),
                        "method": "tools/call",
                        "params": {
                            "name": "aceguard_spend",
                            "arguments": {
                                "amount_usdc": args.amount,
                                "recipient": args.recipient,
                                "endpoint_host": args.endpoint_host,
                            },
                        },
                    },
                )
            )
            print(json.dumps(spend_payload, indent=2, ensure_ascii=False))
            if is_err:
                print(
                    "\n⚠️  aceguard_spend flagged isError. Likely causes:\n"
                    "    - recipient USDC ATA does not exist on devnet "
                    "(use your own Phantom address as recipient — its ATA was\n"
                    "      created when you minted devnet USDC)\n"
                    "    - endpoint_host not on the vault allowlist (EndpointNotAllowed)\n"
                    "    - per_call_cap / daily_cap exceeded\n"
                    "    - vault paused / expired"
                )
                return 2
            spent_ok = True

        elif args.pay_for_api:
            _hr(f"3. aceguard_pay_for_api  →  {args.method} {args.api_url}")
            pay_payload, is_err = _unwrap_tool_result(
                _post(
                    client,
                    args.mcp_url,
                    {
                        "jsonrpc": "2.0",
                        "id": next_id(),
                        "method": "tools/call",
                        "params": {
                            "name": "aceguard_pay_for_api",
                            "arguments": {
                                "url": args.api_url,
                                "method": args.method,
                                "json_body": body_json,
                            },
                        },
                    },
                )
            )
            meta = {k: v for k, v in pay_payload.items() if k != "upstream_response"}
            print(json.dumps(meta, indent=2, ensure_ascii=False))
            upstream = pay_payload.get("upstream_response")
            if upstream is not None:
                preview = json.dumps(upstream, ensure_ascii=False)
                print(f"  upstream_response (preview): {preview[:300]}")
                if len(preview) > 300:
                    print(f"  …[{len(preview) - 300} more chars]")
            if is_err:
                print(
                    "\n⚠️  aceguard_pay_for_api flagged isError. As of the devnet "
                    "deploy api.acedata.cloud quotes are mainnet-only — see\n"
                    "    the 'mainnet-only' note in README. Run --spend instead "
                    "to verify the chain-level path on devnet."
                )
                return 2
            spent_ok = True

        # === 4. aceguard_balance (after) ====================================
        if spent_ok:
            _hr("4. aceguard_balance (after)")
            bal_after, _ = _unwrap_tool_result(
                _post(
                    client,
                    args.mcp_url,
                    {
                        "jsonrpc": "2.0",
                        "id": next_id(),
                        "method": "tools/call",
                        "params": {"name": "aceguard_balance", "arguments": {}},
                    },
                )
            )
            bb = bal_before.get("balance_usdc") or 0
            ba = bal_after.get("balance_usdc") or 0
            print(f"  balance: {bb:.6f} → {ba:.6f} USDC  (Δ = {ba - bb:+.6f})")
            print(
                f"  daily_remaining: {bal_before.get('daily_remaining_usdc')} "
                f"→ {bal_after.get('daily_remaining_usdc')} USDC"
            )

        # === 5. aceguard_history — confirm spend was recorded ===============
        _hr("5. aceguard_history (latest 5)")
        hist, _ = _unwrap_tool_result(
            _post(
                client,
                args.mcp_url,
                {
                    "jsonrpc": "2.0",
                    "id": next_id(),
                    "method": "tools/call",
                    "params": {
                        "name": "aceguard_history",
                        "arguments": {"limit": 5},
                    },
                },
            )
        )
        _print_history(hist, limit=5)

    print("\n✅ done.")
    if not (args.spend or args.pay_for_api):
        print(
            "   (Endpoint is healthy. To do a real spend, re-run with\n"
            "    --spend --recipient <your Phantom wallet address>.)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
