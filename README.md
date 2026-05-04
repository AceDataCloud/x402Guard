# x402guard

> **Solana-native spending guardrails for AI agents.**
> *Give your agent a Solana wallet. Keep the rules on-chain.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Colosseum Frontier 2026](https://img.shields.io/badge/Colosseum-Frontier_2026-purple)](https://colosseum.com/frontier)

---

## Why

AI agents are about to spend money on their own. Today the only options are:

1. **Hand it your private key / credit card** — and watch one bad prompt drain the wallet.
2. **Approve every transaction by hand** — which kills the autonomy that makes the agent useful.

**x402guard is the third option**: a Solana program that holds the agent's USDC inside a [PDA](https://solana.com/docs/core/pda) and enforces user-defined spending policy on every payment — daily caps, per-call caps, endpoint allowlists — so the agent can spend freely *inside the rules* and never outside them.

---

## What you get

A single web app at **`x402guard.acedata.cloud`** that does three things:

| Surface | URL | Audience |
|---|---|---|
| **Dapp UI** | `/` | Humans — connect Phantom, create vault PDA, top up, set policy, pause / clawback |
| **REST API** | `/api/*` | The Dapp UI itself + the MCP layer |
| **MCP endpoint** | `/mcp/<token>` | AI agents (Claude Desktop, Cursor, custom) — speaks [Streamable HTTP MCP](https://modelcontextprotocol.io); exposes `aceguard.spend`, `aceguard.balance`, `aceguard.history`, `aceguard.pay_for_api` |

…all backed by one Anchor program that is the only thing capable of moving USDC out of the vault.

---

## How it works (90-second tour)

```
   Alice (Phantom)                      x402guard.acedata.cloud
        │                                          │
        │ 1. Connect & sign challenge              │
        ├─────────────────────────────────────────►│
        │                                          │
        │ 2. Create AgentVault (Phantom signs)     │
        ├─────────────────────────────────────────►├──► Solana: AgentVault::create_vault(...)
        │                                          │   Creates PDA: ["vault", alice, agent_id]
        │                                          │   Stores Policy { daily_cap, per_call_cap,
        │                                          │                   endpoint_allowlist, ... }
        │ 3. Top up 5 USDC (Phantom signs SPL tx)  │
        ├─────────────────────────────────────────►├──► USDC moves into vault PDA's ATA
        │                                          │
        │ 4. Copies MCP URL: /mcp/abc123           │
        │                                          │
        ▼                                          │
   Pastes into Claude Desktop config               │
        │                                          │
        ▼                                          │
   "Make me a birthday card"                       │
        │                                          │
   Claude → MCP "aceguard"                         │
        │   tool: pay_for_api(midjourney/imagine)  │
        ├─────────────────────────────────────────►│
        │                                          │
        │                                  api.acedata.cloud → 402 Payment Required
        │                                          │
        │                            x402guard backend invokes
        │                            AgentVault::spend(0.025 USDC, ace-pay-to)
        │                                          │
        │                              Solana program checks policy:
        │                              ✅ daily cap, ✅ per-call cap,
        │                              ✅ endpoint allowlist, ✅ nonce
        │                              → PDA-signs SPL transfer → tx 4fsV…3t
        │                                          │
        │                            Backend builds X-Payment header from tx,
        │                            retries the API → 200 OK + image URL
        │                                          │
        ◄──────────────────────────────────────────┤
   Image returned to Claude → shown to Alice       │
        │                                          │
        │  Vault page live-updates: balance 5 → 4.975, new spend on Solscan
```

Every spend is on-chain. Every rejection is on-chain. If the backend gets pwned, the program is still the boundary — attackers can spend at most `daily_cap × allowlist`, and Alice is one click from full clawback.

---

## Built on Solana, ground up

| Component | Solana primitive |
|---|---|
| Vault account holding USDC | **PDA** (no private key — only the program can move funds) |
| Spending policy storage | Anchor `#[account]` PDA, sibling to the vault |
| Atomic spend + ledger update | One `spend()` ix updates `used_today`, transfers USDC, emits a `SpendEvent` |
| Wallet UX | Phantom + `@solana/wallet-adapter-react` — no bridges, no MetaMask |
| Fee economics | ~5000 lamports / spend (≈ $0.0008) makes 0.025 USDC microspends viable. Doesn't work on Ethereum L1. |

**This isn't a multi-chain tool that supports Solana — it's only Solana.** PDA + Token-2022 + sub-cent fees are load-bearing primitives, not decoration.

---

## Repo layout

```
programs/agent_vault/    Anchor program (Rust). The on-chain spending boundary.
api/                     FastAPI backend. Builds Solana txs, hosts MCP, signs delegation txs.
web/                     Vue 3 + Vite Dapp. Phantom UX for vault management.
deploy/                  Production K8s manifests + Caddy ingress.
.plans/                  Design docs (the public ones live here; private ones in monorepo).
```

Each directory has its own `README.md` with run instructions.

---

## Quick start (devnet)

```bash
# 1. Anchor program
cd programs/agent_vault
anchor build && anchor deploy --provider.cluster devnet

# 2. Backend
cd ../../api
poetry install && poetry run uvicorn core.asgi:app --reload --port 8000

# 3. Web
cd ../web
npm install && npm run dev   # → http://localhost:5173
```

Connect Phantom on devnet, request airdrop, mint some devnet USDC, and you're off.

---

## Status

🚧 **Active build for Colosseum Frontier 2026** (submission deadline May 11, 2026).

See [`.plans/X402GUARD.md`](.plans/X402GUARD.md) for the full plan, six-day track schedule, demo script, and risk register.

---

## Hackathon

This project is a submission to [Colosseum Frontier 2026](https://colosseum.com/frontier), the global Solana-only hackathon run by Colosseum and the Solana Foundation.

**Why we'll place**:
- Working live demo on **Solana mainnet** — real USDC, real `api.acedata.cloud` 402 calls, real Solscan tx hashes.
- Solana primitives used correctly, not as decoration. PDA-signed transfers, Anchor errors, on-chain events.
- A pitch one judge can repeat to another in the hallway: *"give your AI agent a Solana wallet, keep the rules on-chain."*

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built by [Ace Data Cloud](https://acedata.cloud).*
