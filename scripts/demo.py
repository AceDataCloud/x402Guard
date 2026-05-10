#!/usr/bin/env python3
"""Drive an x402guard MCP endpoint from the command line.

Why this exists
---------------
The MCP endpoint at ``/mcp/<token>`` is plain JSON-RPC over HTTP POST.
Claude Desktop is one client; it is not the only one. If your client
is misconfigured (Claude Desktop only speaks stdio MCP, not HTTP MCP —
you need the `mcp-remote` bridge for that) you cannot tell whether the
fault is on the client or the server.

This script answers that question by speaking JSON-RPC to the MCP
endpoint directly. No Claude, no Cursor, no client-side config.

It will, in order:

1.  ``tools/list``      — confirm the four tools are registered
2.  ``aceguard_balance`` — read on-chain USDC + remaining caps
3.  ``aceguard_pay_for_api`` — full x402 dance against an acedata API:
    * upstream returns 402
    * x402guard backend invokes ``agent_vault.spend()`` on Solana
    * Anchor program checks daily / per-call / allowlist / paused / nonce
    * PDA-signed SPL transfer goes on chain
    * x402guard rebuilds the X-Payment header from the tx signature
    * upstream is retried, returns 200
4.  ``aceguard_balance`` — confirm the vault balance ticked down
5.  ``aceguard_history`` — show the new spend with Solscan link

Usage
-----
::

    python scripts/demo.py \\
        https://x402guard.acedata.cloud/mcp/<TOKEN>

    # or against a local stack
    python scripts/demo.py http://localhost:8000/mcp/<TOKEN>

    # use a non-default API endpoint (must be on the vault allowlist)
    python scripts/demo.py <MCP-URL> \\
        --url https://api.acedata.cloud/openai/chat/completions \\
        --body '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'

Requires only ``httpx`` (already in the api package's pyproject) and the
Python stdlib. No SDK, no MCP libraries.
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


def _unwrap_tool_result(rpc_response: dict[str, Any]) -> dict[str, Any]:
    """Return the JSON object embedded in the first ``content[0].text``.

    The MCP tools wrap their JSON output in ``{content: [{type: "text",
    text: "<json>"}], isError: bool}``; for this demo we always want the
    JSON inside.
    """
    if "error" in rpc_response:
        sys.exit(
            f"❌ MCP RPC error: code={rpc_response['error'].get('code')} "
            f"message={rpc_response['error'].get('message')!r} "
            f"data={rpc_response['error'].get('data')!r}"
        )
    result = rpc_response.get("result") or {}
    content = result.get("content") or []
    if not content:
        return result
    text = content[0].get("text") or ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"_raw_text": text, "_isError": result.get("isError", False)}


def _hr(title: str) -> None:
    print()
    print(f"━━━ {title} " + "━" * max(0, 60 - len(title)))


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__.split("\n\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("mcp_url", help="Full MCP URL e.g. https://x402guard.acedata.cloud/mcp/<TOKEN>")
    p.add_argument(
        "--url",
        default=DEFAULT_API_URL,
        help=f"API to pay for (must be on vault allowlist). default: {DEFAULT_API_URL}",
    )
    p.add_argument(
        "--body",
        default=json.dumps(DEFAULT_BODY),
        help="JSON request body for the API call.",
    )
    p.add_argument(
        "--method",
        default="POST",
        choices=["GET", "POST"],
        help="HTTP method for the API call. default: POST",
    )
    p.add_argument(
        "--skip-pay",
        action="store_true",
        help="Only call balance + history; do not actually spend.",
    )
    args = p.parse_args()

    try:
        body_json = json.loads(args.body)
    except json.JSONDecodeError as exc:
        sys.exit(f"--body is not valid JSON: {exc}")

    rpc_id = 0

    def next_id() -> int:
        nonlocal rpc_id
        rpc_id += 1
        return rpc_id

    print(f"x402guard CLI demo — driving MCP at {args.mcp_url!r}")
    with httpx.Client(timeout=180.0) as client:
        _hr("1. tools/list")
        resp = _post(
            client,
            args.mcp_url,
            {"jsonrpc": "2.0", "id": next_id(), "method": "tools/list"},
        )
        if "error" in resp:
            sys.exit(f"❌ tools/list failed: {resp['error']}")
        tools = (resp.get("result") or {}).get("tools") or []
        for t in tools:
            print(f"  • {t.get('name'):28s} — {t.get('description', '')[:80]}")
        if not tools:
            sys.exit("❌ tools/list returned no tools — the endpoint is unhealthy.")

        _hr("2. aceguard_balance")
        bal_before = _unwrap_tool_result(
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
        print(json.dumps(bal_before, indent=2, ensure_ascii=False))

        if args.skip_pay:
            print("\n--skip-pay set; stopping after balance read.")
            return 0

        if bal_before.get("paused"):
            sys.exit("❌ vault is paused. Resume it in the Dapp before retrying.")
        if (bal_before.get("balance_usdc") or 0) <= 0:
            sys.exit(
                "❌ vault balance is 0 USDC. Top up via the Dapp first "
                "(Step 2 of the README)."
            )

        _hr(f"3. aceguard_pay_for_api  →  {args.method} {args.url}")
        pay_result = _unwrap_tool_result(
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
                            "url": args.url,
                            "method": args.method,
                            "json_body": body_json,
                        },
                    },
                },
            )
        )
        # Only print the metadata block + a short preview of the upstream
        # response — the upstream JSON can be large.
        meta = {k: v for k, v in pay_result.items() if k != "upstream_response"}
        print(json.dumps(meta, indent=2, ensure_ascii=False))
        upstream = pay_result.get("upstream_response")
        if upstream is not None:
            preview = json.dumps(upstream, ensure_ascii=False)
            print(f"  upstream_response (preview): {preview[:300]}")
            if len(preview) > 300:
                print(f"  …[{len(preview) - 300} more chars]")
        if pay_result.get("_isError"):
            print(
                "\n⚠️  pay_for_api flagged isError. Common causes:\n"
                "    - endpoint host not on vault allowlist (EndpointNotAllowed)\n"
                "    - per_call_cap / daily_cap exceeded\n"
                "    - vault paused / expired\n"
                "    - upstream returned non-200 even after payment landed"
            )
            return 2

        _hr("4. aceguard_balance (after spend)")
        bal_after = _unwrap_tool_result(
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
        print(
            f"  balance: {bb:.6f} → {ba:.6f} USDC  (Δ = {ba - bb:+.6f})\n"
            f"  daily_remaining: {bal_before.get('daily_remaining_usdc')} "
            f"→ {bal_after.get('daily_remaining_usdc')} USDC"
        )

        _hr("5. aceguard_history (latest 3)")
        hist = _unwrap_tool_result(
            _post(
                client,
                args.mcp_url,
                {
                    "jsonrpc": "2.0",
                    "id": next_id(),
                    "method": "tools/call",
                    "params": {
                        "name": "aceguard_history",
                        "arguments": {"limit": 3},
                    },
                },
            )
        )
        for sp in (hist.get("spends") or [])[:3]:
            print(
                f"  {sp.get('block_time')} | {sp.get('amount_usdc'):.6f} USDC | "
                f"{sp.get('endpoint')}{sp.get('api_path') or ''}"
            )
            print(f"    → {sp.get('solscan')}")

    print("\n✅ done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
