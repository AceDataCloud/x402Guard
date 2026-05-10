# x402guard

> **Solana-native spending guardrails for AI agents.**
> *Give your agent a Solana wallet. Keep the rules on-chain.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Colosseum Frontier 2026](https://img.shields.io/badge/Colosseum-Frontier_2026-purple)](https://colosseum.com/frontier)
[![Live on devnet](https://img.shields.io/badge/devnet-live-brightgreen)](https://x402guard.acedata.cloud/.well-known/x402guard)

| | |
|---|---|
| 🌐 Live Dapp | [`https://x402guard.acedata.cloud`](https://x402guard.acedata.cloud) |
| 🔗 Anchor program (devnet) | [`56TbAziiW8pDHFpRsxfnfBUfimBRTMCHw4gwDGw9uPW6`](https://solscan.io/account/56TbAziiW8pDHFpRsxfnfBUfimBRTMCHw4gwDGw9uPW6?cluster=devnet) |
| 🤖 MCP transport | Streamable HTTP at `https://x402guard.acedata.cloud/mcp/<session-token>` |
| 📜 Hackathon | [Colosseum Frontier 2026](https://colosseum.com/frontier) (deadline May 11, 2026) |

> **✅ End-to-end verified live on 2026-05-10.** Multiple on-chain `aceguard_spend` invocations against the production MCP endpoint settled on Solana devnet, e.g. [`249u8Pion…3y3D`](https://solscan.io/tx/249u8Pion7UmwiWQ2jWZJzqMpSVCxAQo9vT9dGZD85zGqNiRYzYHJ8a8Mkz3Cokpnos4EqHKzNw4u5cXzTbr3y3D?cluster=devnet) and [`2v4c8TDV…aeYN`](https://solscan.io/tx/2v4c8TDVDTWPHoZNLr229ZhjjTD76rcW4sfPxL7tEXMeHS7Lz77veY8oenVcF5kRYdY11JjLAkccKHu5yKYCaeYN?cluster=devnet), each returning cleanly with `isError: false` from the MCP tool. The vault USDC balance ticked down by exactly the spend amount each time; on-chain ATA matches the DB exactly. Follow the [hand-held demo](#hand-held-demo-zero-to-on-chain-spend-in-10-minutes) below to reproduce on your own laptop.

---

AI agents are about to spend money on their own. Today the only options are:

1. **Hand it your private key / credit card** — and watch one bad prompt drain the wallet.
2. **Approve every transaction by hand** — which kills the autonomy that makes the agent useful.

**x402guard is the third option**: a Solana program that holds the agent's USDC inside a [PDA](https://solana.com/docs/core/pda) and enforces a user-defined spending policy on every payment — daily caps, per-call caps, endpoint allowlists — so the agent can spend freely *inside the rules* and never outside them.

---

## What you get

A single web app at **`x402guard.acedata.cloud`** that does three things:

| Surface | URL | Audience |
|---|---|---|
| **Dapp UI** | `/` | Humans — connect Phantom, create vault PDA, top up, set policy, pause / clawback |
| **REST API** | `/api/*` | The Dapp UI itself + the MCP layer |
| **MCP endpoint** | `/mcp/<token>` | AI agents (Claude Desktop, Cursor, custom) — speaks [Streamable HTTP MCP](https://modelcontextprotocol.io); exposes `aceguard_balance`, `aceguard_history`, `aceguard_spend`, `aceguard_pay_for_api` |

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
        ├─────────────────────────────────────────►├──► Solana: agent_vault::create_vault(...)
        │                                          │   Creates PDA: ["vault", alice, agent_id]
        │                                          │   Stores Policy { daily_cap, per_call_cap,
        │                                          │                   endpoint_allowlist, ... }
        │ 3. Top up USDC (Phantom signs SPL tx)    │
        ├─────────────────────────────────────────►├──► USDC moves into vault PDA's ATA
        │                                          │
        │ 4. Mint MCP URL — /mcp/<token>           │
        │                                          │
        ▼                                          │
   Pastes URL into Claude Desktop config           │
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
        │                            agent_vault::spend(0.025 USDC, ace-pay-to)
        │                                          │
        │                              Solana program checks policy:
        │                              ✅ not paused, ✅ not expired,
        │                              ✅ daily cap, ✅ per-call cap,
        │                              ✅ endpoint allowlist, ✅ nonce
        │                              ✅ delegation key
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
| Wallet UX | Phantom + `@solana/wallet-adapter` — no bridges, no MetaMask |
| Fee economics | ~5 000 lamports / spend (≈ $0.0008) makes 0.025 USDC microspends viable. Doesn't work on Ethereum L1. |

**This isn't a multi-chain tool that supports Solana — it's Solana-only.** PDA + SPL Token + sub-cent fees are load-bearing primitives, not decoration.

---

## Repo layout

```
programs/agent_vault/   Anchor program (Rust). The on-chain spending boundary.
api/                    FastAPI backend. Builds Solana txs, hosts MCP, signs delegation txs.
web/                    Vue 3 + Vite Dapp. Phantom UX for vault management.
deploy/                 Production K8s manifests + Caddy ingress.
.plans/                 Design docs.
DEMO.md                 4-minute demo runbook (scene-by-scene).
```

Each subdirectory has its own `README.md` with run instructions.

---

## Hand-held demo (zero to on-chain spend in ~10 minutes)

> Follow this section start-to-finish on a fresh laptop. No Solana / Anchor / MCP background needed. By the end you'll have a finalized USDC transfer on Solana devnet, signed by the on-chain program, with a Solscan link to prove it.

### Step 0 — Install Phantom & switch to devnet (2 min)

1. Install [Phantom wallet](https://phantom.com) (browser extension or mobile).
2. Create or import a wallet. **Save the seed phrase** — you'll need it to recover.
3. Switch Phantom to **Devnet**:
   - Click the gear (⚙️) icon → **Developer Settings** → **Testnet Mode** → **Enable**.
   - Then top-right network selector → **Devnet**.
4. Copy your Phantom address — you'll paste it as `YOUR-PHANTOM-ADDRESS` everywhere below.

> ⚠️ The dapp is locked to devnet (it reads `cluster` from `/.well-known/x402guard`). If Phantom is on mainnet you'll get cryptic "blockhash not found" errors. Always double-check the network selector in Phantom shows "Devnet".

### Step 1 — Get devnet SOL (1 min)

You need ~0.05 SOL of devnet gas. Open https://faucet.solana.com → paste your Phantom address → cluster **Devnet** → **Confirm Airdrop**. Refresh Phantom; you should see ~1 SOL within 5 seconds. (If the faucet is rate-limiting your IP, try [Helius's faucet](https://faucet.helius.dev) instead.)

### Step 2 — Get devnet USDC (1 min) — *this also creates your USDC ATA*

The vault, your wallet, and the spend-recipient all need USDC ATAs (associated token accounts) on devnet. Minting yourself some devnet USDC creates yours in the same step.

1. Open https://spl-token-faucet.com → pick **USDC (Dev)** → paste your Phantom address → **Get tokens**.
2. Refresh Phantom → you should now see a USDC balance (e.g. 100 USDC). The Circle devnet USDC mint is `4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU`.

> 💡 **Why this matters for the demo:** when we later run `aceguard_spend --recipient <YOUR-PHANTOM-ADDRESS>`, the on-chain program needs the recipient's USDC ATA to already exist (Anchor returns `AccountNotInitialized` / error 3012 if it doesn't, deliberately — the program will never auto-create someone else's ATA). Because **you're sending USDC back to your own wallet**, the ATA you just created in this step is exactly what the program will write into. No extra setup needed.

### Step 3 — Connect the dapp & create a vault (2 min)

1. Open <https://x402guard.acedata.cloud> in the same browser as Phantom.
2. Click **Connect Phantom** → Phantom popup → **Sign** the message that starts with `x402guard | sign in to manage your AI agent vaults | nonce=…`. *No SOL is spent — this is just an Ed25519 signature.*
3. Click **+ New vault** and fill the form. The values below are tuned so the demo `aceguard_spend` of 0.01 USDC fits comfortably under both caps:

   | Field | Demo value | What it does |
   |---|---|---|
   | Agent name | `demo-agent` | Free-form label |
   | Daily cap (USDC) | `1` | Max the agent can spend per UTC day |
   | Per-call cap (USDC) | `0.1` | Max in any single tx |
   | Expires in (days) | `7` | After this, all spends are rejected |
   | Endpoint allowlist | `api.acedata.cloud` | One host per line. **Spends with any other `endpoint_host` will be rejected on-chain** |

4. Click **Create vault** → Phantom popup → **Approve**. ~3 s for confirmation. Page redirects to the vault detail; the **Vault PDA** field is a Solscan deep-link — click it to see the on-chain account.

### Step 4 — Top up the vault with devnet USDC (1 min)

The vault PDA starts empty. Move some of your devnet USDC into it:

1. On the vault detail page, find the **Top up** card.
2. Enter `1` (= 1 USDC) → **Send USDC** → Phantom popup → **Approve**.
3. Wait ~3 s. The vault's **Balance** chip should flip from `0.000000` to `1.000000` USDC.

### Step 5 — Mint an MCP URL (30 s)

Scroll to the **MCP sessions** card on the vault detail page:

1. Type a label, e.g. `cli-demo` (optional, for your own reference).
2. Click **+ New MCP URL** → a new row appears with `https://x402guard.acedata.cloud/mcp/<TOKEN>` and a **Copy** button.
3. **Copy** that URL. Set it in your shell:
   ```bash
   URL='https://x402guard.acedata.cloud/mcp/<YOUR-TOKEN>'
   ```

This URL is the only thing an agent ever sees. It's bound to one vault; you can revoke it any time from the same card.

### Step 6 — Sanity-check the endpoint with a single `curl` (30 s)

Before installing anything heavier, prove the URL itself is healthy:

```bash
# tools/list — must return all four aceguard_* tools
curl -sS "$URL" -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -m json.tool

# aceguard_balance — must return your real on-chain vault balance
curl -sS "$URL" -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"aceguard_balance","arguments":{}}}' \
  | python3 -m json.tool
```

Expected: four tools listed (`aceguard_balance`, `aceguard_history`, `aceguard_spend`, `aceguard_pay_for_api`), and `balance_usdc: 1.0`.

> **If this works, your endpoint is healthy.** Any `MCP could not be loaded` you see in Claude Desktop after this is a **client config issue**, not a server problem — see [Step 9](#step-9--connect-claude-desktop-or-cursor-optional-2-min).

### Step 7 — Run the bundled CLI demo (1 min)

The repo ships a single-file demo that drives the MCP endpoint over JSON-RPC. No SDK, no MCP client, no Claude:

```bash
git clone https://github.com/AceDataCloud/x402Guard
cd x402Guard

# Read-only — lists tools, reads balance, reads history. Zero on-chain tx.
python3 -m pip install --user httpx                                  # one-off
python3 scripts/demo.py "$URL"

# Or with bash + curl + jq if you don't have Python handy
brew install jq                                                      # one-off
./scripts/mcp-curl.sh "$URL"
```

You should see the four tools, the vault balance (`1.0 USDC`), and an empty history.

### Step 8 — Make a real on-chain spend (1 min)

Now spend `0.01 USDC` from the vault. The recipient is **your own Phantom wallet** — its USDC ATA already exists from Step 2, so the on-chain transfer settles immediately.

```bash
python3 scripts/demo.py "$URL" --spend \
    --recipient <YOUR-PHANTOM-ADDRESS> \
    --amount 0.01

# Or with bash
./scripts/mcp-curl.sh "$URL" --spend \
    --recipient <YOUR-PHANTOM-ADDRESS> \
    --amount 0.01
```

What happens:

1. CLI sends a JSON-RPC `tools/call` with `aceguard_spend(amount_usdc=0.01, recipient=<you>, endpoint_host="api.acedata.cloud")`.
2. x402guard backend invokes `agent_vault::spend(...)` on Solana devnet.
3. The Anchor program checks every gate **on-chain**: not-paused, not-expired, daily cap, per-call cap, allowlist hash match, monotonic nonce, valid delegation key.
4. The program PDA-signs an SPL `transferChecked` from the vault's USDC ATA → your USDC ATA.
5. Transaction is finalized; `aceguard_spend` returns the tx signature + a Solscan link.

Expected output (real values from a verified live run):

```
━━━ 3. aceguard_spend  →  0.01 USDC → <YOUR-PHANTOM-ADDRESS>
{
  "tx": "2v4c8TDV…aeYN",
  "amount_usdc": 0.01,
  "nonce": 1,
  "solscan": "https://solscan.io/tx/2v4c8TDV…aeYN"
}

━━━ 4. aceguard_balance (after)
  balance: 1.000000 → 0.990000 USDC  (Δ = -0.010000)
  daily_remaining: 1.0 → 0.99 USDC

━━━ 5. aceguard_history (latest 5)
  • <timestamp> | 0.01 USDC | → <YOUR-PHANTOM-ADDRESS> | endpoint=api.acedata.cloud
    solscan: https://solscan.io/tx/2v4c8TDV…aeYN

✅ done.
```

**Open the Solscan link** — the tx is finalized on devnet, your USDC ATA is +0.01, the vault's USDC ATA is -0.01. Refresh the Dapp page → vault balance shows `0.990000` and a new history row.

> 💡 **Want a different recipient?** Any Solana address whose USDC ATA exists on devnet works. The simplest way to bootstrap one: have *that* recipient also follow Step 2 once (one-time per address), or any holder can pay rent: `spl-token --url devnet create-account 4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU --owner <RECIPIENT>`.

### Step 9 — Connect Claude Desktop or Cursor (optional, 2 min)

Now that you've proven the endpoint works, hook it into a real MCP client.

**Claude Desktop** speaks **stdio** MCP only — it does *not* load HTTP MCP endpoints from a `{"url": "..."}` config (that schema is for Claude.ai web "Custom Connectors", a different product). Use the community-standard `mcp-remote` bridge:

```json
{
  "mcpServers": {
    "aceguard": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://x402guard.acedata.cloud/mcp/<YOUR-TOKEN>"
      ]
    }
  }
}
```

Save to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows). Then **fully quit Claude (Cmd+Q on macOS, not just close the window)** and relaunch. Requires Node ≥ 18 on `PATH` so `npx` can fetch `mcp-remote`.

The four `aceguard_*` tools light up. Try:

> *"Use `aceguard_balance` to read my vault, then use `aceguard_spend` to send 0.01 USDC to `<YOUR-PHANTOM-ADDRESS>` for endpoint `api.acedata.cloud`. Show me the Solscan link."*

**Cursor / Cline / any HTTP-MCP-aware client** take the URL directly with no bridge. Look in that client's MCP config for a field like `mcpServers.<name>.url` and paste your URL there.

| Tool | Use |
|---|---|
| `aceguard_balance` | Check USDC balance + remaining caps before spending |
| `aceguard_history` | List recent spends with Solscan tx links |
| `aceguard_spend` | Direct USDC transfer to any recipient (low-level) |
| `aceguard_pay_for_api` | High-level wrapper — give it a paid URL, it does the full x402 dance. *Mainnet-only as of devnet deploy — see [Known limitations](#known-limitations).* |

### Step 10 — See the boundary in action (1 min, optional)

To prove the on-chain enforcement is real, deliberately violate the policy. Each rejection is signed by the on-chain program — the backend cannot override it.

```bash
# 1. Wrong endpoint — host is not on the allowlist → EndpointNotAllowed (Anchor 6005)
python3 scripts/demo.py "$URL" --spend \
    --recipient <YOUR-PHANTOM-ADDRESS> \
    --endpoint-host evil-api.com

# 2. Over per-call cap — vault was created with per_call_cap=0.1 USDC → PerCallCapExceeded
python3 scripts/demo.py "$URL" --spend \
    --recipient <YOUR-PHANTOM-ADDRESS> \
    --amount 0.5

# 3. Pause the vault from the Dapp (one Phantom signature), then retry → VaultPaused
#    Resume from the same UI when done.
```

You'll see each rejection with a clear Anchor error code in the response, e.g.:

```
detail: ... custom program error: 0x1779
        Error Code: NonceReplay. Error Number: 6009. ...
```

**Every rejection is on-chain.** If the backend is compromised, the program is still the boundary — the most an attacker can do is spend `daily_cap × allowlist`, and the user is one click from full clawback.

### Known limitations

- **`aceguard_pay_for_api` against `api.acedata.cloud` requires mainnet.** `api.acedata.cloud` issues its 402 quotes against the **mainnet** USDC mint (`EPjFWdd5…`, `payTo: 5iVXFr…`). The current x402guard deploy is on **devnet** with the Circle devnet mint — they're different chains, and the on-chain program correctly refuses to settle a mainnet quote with devnet tokens. This is **expected and called out in [`.plans/X402GUARD.md`](.plans/X402GUARD.md) §11**; mainnet flip is a one-line config change.
- Until then: drive `aceguard_spend` to any devnet recipient (Step 8 above) — same on-chain ix, same policy enforcement, same Solscan-verifiable result. Or use the [`@acedatacloud/x402-client`][x402client] SDK directly to make paid `api.acedata.cloud` calls from your own wallet (no x402guard policy enforcement, but proves the wire format end-to-end on mainnet today).

[x402client]: https://github.com/AceDataCloud/X402Client
[sdk]: https://github.com/AceDataCloud/SDK
[solana-e2e]: https://github.com/AceDataCloud/X402Client/blob/main/typescript/scripts/test-solana-e2e.ts

---

## What's deployed today (devnet)

| Thing | Value |
|---|---|
| Anchor program | [`56TbAziiW8pDHFpRsxfnfBUfimBRTMCHw4gwDGw9uPW6`](https://solscan.io/account/56TbAziiW8pDHFpRsxfnfBUfimBRTMCHw4gwDGw9uPW6?cluster=devnet) |
| Cluster | `devnet` |
| USDC mint | `4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU` (Circle devnet) |
| Backend image | `ghcr.io/acedatacloud/x402guard-api` (linux/amd64) |
| Web image | `ghcr.io/acedatacloud/x402guard-web` (linux/amd64) |
| K8s namespace | `acedatacloud` (Tencent Cloud TKE, Hong Kong) |
| TLS | Let's Encrypt via the platform's `tls-wildcard-acedata-cloud` secret |
| Self-describe | [`https://x402guard.acedata.cloud/.well-known/x402guard`](https://x402guard.acedata.cloud/.well-known/x402guard) |

> 💡 **Why devnet, not mainnet?** Deploying the program to mainnet costs ~3 SOL of *real* rent (rent-exempt deposit; recoverable on `program close`). Devnet is the standard hackathon target — judges know to switch their wallets to devnet to verify. The mainnet deploy is **a one-line change** (`SOLANA_CLUSTER=mainnet` + `solana program deploy --url mainnet`) and we'll do it the day we record the final submission video.

---

## Local development

### One-command full stack

```bash
docker compose up --build
open http://localhost:8080
```

Brings up:

- `postgres` — same engine as production
- `x402guard-api` — FastAPI + uvicorn on `:8000`, schema auto-created
- `x402guard-web` — nginx serving the Vite build, proxying `/api`, `/mcp`, `/.well-known`, `/health` to the api

In Phantom: switch to **Devnet** (the local stack uses the public devnet RPC). Address `127.0.0.1:8080/.well-known/x402guard` to see the cluster + program ID.

### Run pieces individually

```bash
# Anchor program (Rust + cargo-build-sbf)
cd programs/agent_vault
cargo build-sbf --manifest-path Cargo.toml
# .so artifact lands at ../../target/deploy/agent_vault.so

# FastAPI backend
cd ../../api
poetry install
cp .env.example .env       # then edit
PYTHONPATH=.. poetry run uvicorn api.app:app --reload --port 8000

# Vue Dapp (Vite hot-reload)
cd ../web
npm install
npm run dev                # → http://localhost:5173 (proxies /api → :8000)
```

### Test suites

| Where | Command | What |
|---|---|---|
| `api/` | `PYTHONPATH=.. pytest tests/ -q` | 35 unit tests: auth flow, crypto wrap/unwrap, ix-builder discriminators + borsh field order, vault routes (with stubbed Solana RPC), MCP tools (with stubbed `httpx`) |
| `web/` | `npm run lint && npx vue-tsc --noEmit && CI=1 npx playwright test` | ESLint + Vue type-check + 4 Playwright e2e (home, pillars, /vaults guard, new-vault form validation) |
| `programs/agent_vault/` | `anchor test` | TypeScript+ts-mocha against a local validator: `create_vault`, `spend`, `pause/resume`, `update_policy`, `clawback` happy + 10 rejection cases |
| Local stack e2e | `bash scripts/e2e-smoke.sh` *(planned)* | Auth → create → list → MCP `tools/list` against the running stack |

A clean run of all three suites takes <1 minute on a 2024 MacBook.

---

## Deploy a fresh program (for forks)

If you fork the repo you'll want your own program ID. The build pipeline expects `target/deploy/agent_vault-keypair.json` to exist — `cargo build-sbf` generates one on first build. Then:

```bash
# 1. Build the program
. "$HOME/.cargo/env"
export PATH="$HOME/.local/share/solana/install/active_release/bin:$PATH"
cd /path/to/x402guard
cargo build-sbf --manifest-path programs/agent_vault/Cargo.toml

# 2. Read the program ID from the build keypair
PROGRAM_ID=$(solana address -k target/deploy/agent_vault-keypair.json)
echo "$PROGRAM_ID"

# 3. Patch declare_id! / config / docker-compose / DEMO.md / api.yaml
OLD=56TbAziiW8pDHFpRsxfnfBUfimBRTMCHw4gwDGw9uPW6
for f in docker-compose.yaml deploy/production/api.yaml DEMO.md Anchor.toml \
         programs/agent_vault/src/lib.rs api/core/config.py \
         api/tests/conftest.py api/tests/test_health.py api/.env.example \
         programs/agent_vault/README.md; do
  sed -i '' "s|$OLD|$PROGRAM_ID|g" "$f"
done

# 4. Rebuild after the declare_id! change
cargo build-sbf --manifest-path programs/agent_vault/Cargo.toml

# 5. Fund a deployer wallet — devnet is free, mainnet needs ~3 real SOL
solana config set --url devnet
solana balance                       # should be ≥ 3 SOL

# 6. Deploy
solana program deploy target/deploy/agent_vault.so \
  --program-id target/deploy/agent_vault-keypair.json \
  --url devnet                       # swap to `mainnet` when you're ready

# 7. Verify
solana program show "$PROGRAM_ID" --url devnet
```

For a mainnet-bound deploy, also:

- Use `solana-keygen grind --starts-with X402:1` to mint a vanity keypair before step 1.
- Provision a real `x402guard-secrets` Kubernetes secret (`APP_SECRET_KEY`, `CONNECTION_VAULT_KEY`, `DATABASE_URL`, `POSTGRES_PASSWORD`).
- Switch `SOLANA_CLUSTER` + `SOLANA_RPC_URL` in `deploy/production/api.yaml` to `mainnet` / a paid RPC (Helius, Triton, etc. — the public one rate-limits).

---

## Production deploy on the AceDataCloud cluster

```bash
# Pull the cluster's kubeconfig (stash it under /tmp; it never lives in repo)
source .claude/.env
python3 .claude/scripts/tke.py kubeconfig cls-fhngwqc2 > /tmp/kubeconfig-hk.yaml
export KUBECONFIG=/tmp/kubeconfig-hk.yaml

# (One-time) bootstrap secrets
kubectl -n acedatacloud create secret generic x402guard-secrets \
  --from-literal=APP_SECRET_KEY=$(openssl rand -hex 32) \
  --from-literal=CONNECTION_VAULT_KEY=$(openssl rand -hex 32) \
  --from-literal=POSTGRES_PASSWORD=$(openssl rand -hex 16) \
  --from-literal=DATABASE_URL='postgresql+asyncpg://x402guard:<PG_PASS>@x402guard-postgres.acedatacloud.svc.cluster.local:5432/x402guard'

# Build + push amd64 images (cluster nodes are x86_64)
TAG=$(date +%Y%m%d-%H%M%S)-amd64
docker buildx build --platform linux/amd64 \
  -t "ghcr.io/acedatacloud/x402guard-api:$TAG" \
  --load -f api/Dockerfile . && docker push "ghcr.io/acedatacloud/x402guard-api:$TAG"
docker buildx build --platform linux/amd64 \
  -t "ghcr.io/acedatacloud/x402guard-web:$TAG" \
  --load -f web/Dockerfile ./web && docker push "ghcr.io/acedatacloud/x402guard-web:$TAG"

# Roll out
BUILD_NUMBER=$TAG bash deploy/run.sh
```

This pushes `postgres.yaml`, `api.yaml`, `web.yaml`, and `ingress.yaml` and waits for rollouts. The script ends with a probe of `https://x402guard.acedata.cloud/health`.

The same flow runs from `.github/workflows/deploy.yaml` once the cluster credentials land in repo secrets (gated on `vars.DEPLOY_TO_K8S == 'true'`).

---

## Quick verification (post-deploy smoke)

```bash
# Liveness
curl -sS https://x402guard.acedata.cloud/health
# → {"status":"ok","version":"0.1.0"}

# Self-describe
curl -sS https://x402guard.acedata.cloud/.well-known/x402guard
# → {"service":"x402guard","cluster":"devnet",
#    "agent_vault_program_id":"56TbAzii...","usdc_mint":"4zMMC9..."}

# TLS cert chain
echo | openssl s_client -servername x402guard.acedata.cloud \
  -connect x402guard.acedata.cloud:443 2>/dev/null \
  | openssl x509 -noout -subject -issuer
# → subject=CN=acedata.cloud
# → issuer=Let's Encrypt E8

# MCP shape (unauthorised — just confirms the route is live)
curl -sS -X POST https://x402guard.acedata.cloud/mcp/no-such-token \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize"}'
# → {"detail":"unknown or revoked token"}

# Solana program is alive
curl -sS https://api.devnet.solana.com -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"getAccountInfo","params":["56TbAziiW8pDHFpRsxfnfBUfimBRTMCHw4gwDGw9uPW6",{"encoding":"jsonParsed"}]}' \
  | python3 -c 'import json,sys; v=json.load(sys.stdin)["result"]["value"]; print("executable=", v["executable"], "owner=", v["owner"])'
# → executable= True owner= BPFLoaderUpgradeab1e11111111111111111111111
```

---

## End-to-end CLI smoke (no browser)

Drives the full Phantom-auth → create-vault → MCP-session → tools/list flow against the live stack using a throwaway Ed25519 keypair. Useful for CI smoke after a deploy and for sanity-checking that nothing regressed without firing up Phantom.

```bash
cd api
poetry install || pip install -e .

python3 - <<'PY'
import asyncio, base64, json
import httpx
from datetime import UTC, datetime, timedelta
from nacl.signing import SigningKey
from solders.pubkey import Pubkey

BASE = "https://x402guard.acedata.cloud"

async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        # 1. Phantom-style: GET challenge → Ed25519 sign → POST login
        challenge = (await c.get("/api/v1/auth/challenge")).json()
        sk = SigningKey.generate()
        pubkey = str(Pubkey.from_bytes(bytes(sk.verify_key)))
        sig = base64.b64encode(sk.sign(challenge["message"].encode()).signature).decode()
        login = (
            await c.post(
                "/api/v1/auth/login",
                json={"pubkey": pubkey, "message": challenge["message"], "signature": sig},
            )
        ).json()
        token = login["session_token"]
        H = {"Authorization": f"Bearer {token}"}
        print(f"AUTH_OK            pubkey={pubkey[:10]}…")

        # 2. Build an unsigned create_vault tx (we won't actually sign + send,
        #    just confirm the backend produced a valid tx envelope + persisted
        #    the pending row).
        body = {
            "agent_name": "Smoke-Agent",
            "daily_cap_usdc": 1.0,
            "per_call_cap_usdc": 0.5,
            "endpoint_allowlist": ["api.acedata.cloud"],
            "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        }
        create = (await c.post("/api/v1/vaults/create", headers=H, json=body)).json()
        print(f"CREATE_OK          vault_pda={create['vault_pda'][:12]}…  tx_b64_len={len(create['tx_b64'])}")

        listed = (await c.get("/api/v1/vaults", headers=H)).json()
        print(f"LIST_OK            count={len(listed['vaults'])}")
        vid = listed["vaults"][0]["id"]

        # 3. Mint an MCP session for the vault we just created.
        mcp = (
            await c.post(
                f"/api/v1/vaults/{vid}/mcp-sessions",
                headers=H,
                json={"label": "smoke-test"},
            )
        ).json()
        print(f"MCP_SESSION_OK     mcp_url={mcp['mcp_url']}")

        # 4. Hit the MCP endpoint directly. tools/list must return all 4 tools.
        rpc = await c.post(
            mcp["mcp_url"],
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        names = sorted(t["name"] for t in rpc.json()["result"]["tools"])
        print(f"MCP_TOOLS_LIST_OK  tools={names}")

asyncio.run(main())
PY
```

Expected output:

```
AUTH_OK            pubkey=ABcD123…
CREATE_OK          vault_pda=Hx12abcdEF…  tx_b64_len=756
LIST_OK            count=1
MCP_SESSION_OK     mcp_url=https://x402guard.acedata.cloud/mcp/<token>
MCP_TOOLS_LIST_OK  tools=['aceguard_balance', 'aceguard_history', 'aceguard_pay_for_api', 'aceguard_spend']
```

The script does **not** execute `spend` (that needs real devnet USDC + a delegation key signing on-chain) — for that, see the in-browser walkthrough above.

---

## Inspect the MCP endpoint with `mcp-inspector`

The `/mcp/<token>` URL works with any MCP client. Quickest way to poke it without writing code:

```bash
# 1. Mint an MCP URL for one of your vaults (web UI → Vault detail → +New MCP URL → Copy)
MCP_URL="https://x402guard.acedata.cloud/mcp/<your-token>"

# 2. Run the official inspector (npx; no install needed)
npx @modelcontextprotocol/inspector --transport http --url "$MCP_URL"

# 3. In the popped-up browser tab:
#    - Click "Connect"  → you'll see "x402guard 0.1.0" in serverInfo
#    - Click "List tools"
#    - Expand "aceguard_balance" → Run (no args) → JSON payload
#    - Expand "aceguard_pay_for_api" → fill `url` = "https://api.acedata.cloud/midjourney/imagine"
#                                           `json_body` = {"prompt": "test"}
#                                       → Run
```

If `aceguard_pay_for_api` returns `on-chain spend rejected: …`, the on-chain `VaultError` reason maps 1:1 to the agent error message — `vault_paused`, `per_call_cap_exceeded`, `daily_cap_exceeded`, `endpoint_not_allowed`, etc. That's the policy boundary doing its job.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `tx confirmation timed out` after **Create vault** | Phantom is on **mainnet** but the program is on **devnet** | Phantom → ⚙️ Developer Settings → Network → **Devnet** |
| Phantom popup says *"This dapp couldn't connect"* | Phantom blocks the site (extension is locked or ad-blocker interferes) | Click the Phantom toolbar icon → unlock; disable shields for `x402guard.acedata.cloud` |
| `spend rejected: endpoint_not_allowed` in Claude | The URL host doesn't sha256-match a vault allowlist entry | Open the vault detail page → confirm `Allowlist` shows the host. The hash check normalises scheme + path + case but the **host string itself must match exactly** |
| `spend rejected: per_call_cap_exceeded` for tiny calls | The vault's `per_call_cap_usdc` is below the upstream API's price | Raise the per-call cap from the vault detail page (1 Phantom signature) |
| Top-up Phantom popup shows *"insufficient funds"* | Wallet has **no devnet USDC** | Visit https://spl-token-faucet.com/?token-name=USDC-Dev → mint to your wallet. Devnet USDC mint is `4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU` |
| `Failed to load vaults: Request failed with status code 500` | Backend lost its DB connection or a fresh deploy hasn't run schema migrations | Check `kubectl -n acedatacloud logs deploy/x402guard-api`. The lifespan hook auto-runs `init_models()` on every boot, so a pod restart usually clears it |
| MCP `tools/list` returns `unknown or revoked token` | Session token revoked or vault deleted | Go to the vault detail page and create a fresh MCP URL |
| `aceguard_pay_for_api` hangs >30 s | Upstream API is slow; Solana RPC under load | The 180 s ingress timeout covers most cases. If recurring, switch to a paid RPC by setting `SOLANA_RPC_URL` in `x402guard-secrets` |
| Phantom signs but "Solscan tx not found" | Phantom is set to **mainnet** while frontend confirms on **devnet** (or vice versa) | Make sure both Phantom and the site agree. The site's cluster is exposed at `/.well-known/x402guard` |
| Devnet airdrop returns `429 / faucet dry` | Same IP rate-limited | Use https://faucet.solana.com (browser captcha) or a paid RPC's faucet (Helius/QuickNode) |

---

## Status

- Anchor program ✅ deployed to devnet (`56TbAzii…uPW6`); 6 instructions, 19 ts-mocha tests
- FastAPI backend ✅ Phantom auth, vault tx builders, MCP at `/mcp/<token>`, spend executor; 35 pytest cases
- Vue 3 Dapp ✅ create / top-up / pause / resume / clawback / MCP sessions; 4 Playwright smoke tests
- Docker + Tencent TKE + Caddy ✅ live at `x402guard.acedata.cloud`
- 4-minute demo runbook ✅ [`DEMO.md`](DEMO.md)

Mainnet deploy + final demo video ⏳ — pending submission window.

See [`.plans/X402GUARD.md`](.plans/X402GUARD.md) for the full design plan, six-day track schedule, and risk register.

---

## Hackathon

This project is a submission to [Colosseum Frontier 2026](https://colosseum.com/frontier), the global Solana-only hackathon run by Colosseum and the Solana Foundation.

**Why we'll place**:

- **Solana primitives, used correctly.** PDA, SPL, Anchor errors, on-chain events, sub-cent fees — every one is *load-bearing*, not decoration. Judges who care about depth see this in 60 seconds of code review.
- **Working live demo.** Real devnet program, real Solscan tx hashes for every action, real upstream `api.acedata.cloud` 402 calls (the AceDataCloud platform already supports x402 + Solana mainnet — see [X402Client](https://github.com/AceDataCloud/X402Client)).
- **Pitch survives the hallway test.** *"Give your AI agent a Solana wallet. Keep the rules on-chain."*

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built by [Ace Data Cloud](https://acedata.cloud). [@x402guard](https://x402guard.acedata.cloud) on the web.*
