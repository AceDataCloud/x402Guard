# x402guard — Solana-Native Spending Guardrails for AI Agents

> **Hackathon entry**: Colosseum Frontier 2026 (Apr 6 – May 11, 2026).
> **Live URL**: `https://x402guard.acedata.cloud`
> **Tagline**: *Give your AI agent a Solana wallet. Keep the rules on-chain.*

---

## 1. Why this exists

AI agents are about to spend money on their own. Today the only way to fund one is:

1. **Hand it your private key / credit card** — and watch a single bad prompt drain the wallet.
2. **Approve every transaction by hand** — which kills the autonomy that makes the agent valuable in the first place.

Neither is acceptable. We need a **third option**:

> A wallet whose spending rules live on-chain, not on the agent. The agent can spend freely *inside the rules*, and never outside them — enforced by a Solana program, not by trust.

That's x402guard.

---

## 2. What it is, in one breath

A web app at `x402guard.acedata.cloud` where a user:

1. Connects Phantom.
2. Creates an **AgentVault** — a Solana PDA that holds USDC and stores a spending policy on-chain.
3. Tops it up.
4. Gets a **personal MCP endpoint URL** they paste into Claude Desktop / Cursor / any MCP-compatible agent.
5. Watches the agent autonomously pay for `api.acedata.cloud` calls (or any x402 endpoint) — bounded by the on-chain rules they wrote.

Every component lives on Solana from the ground up. There is **no multi-chain story** in the pitch — Base/SKALE in `@acedatacloud/x402-client` are an irrelevant implementation detail of the upstream payment library.

---

## 3. The product is the website

Single domain, three surfaces, one Anchor program:

```
                       https://x402guard.acedata.cloud
                                      │
       ┌──────────────────────────────┼──────────────────────────────┐
       ▼                              ▼                              ▼
   Vue Dapp UI                   Backend API                    /mcp/<token>
   (vault management)            (signs Solana txs)             (Streamable HTTP MCP)
       │                              │                              │
       │  user actions                │  agent actions               │
       ▼                              ▼                              ▼
       └──────────────────────────────┼──────────────────────────────┘
                                      │
                                      ▼
                         AgentVault Anchor Program (Solana mainnet)
                              ▲                           │
                              │ verify policy             │ on-chain transfer
                              │                           ▼
                              │                   USDC SPL → x402 payTo
                              │                           │
                              │                           ▼
                              │              api.acedata.cloud (50+ AI APIs)
                              │                           │
                              └──────── x402 settlement ──┘
                                  via @acedatacloud/x402-client
                                  (bundled, Solana-only path used)
```

**One website does three jobs**:

| Surface | URL | Who talks to it | Purpose |
|---|---|---|---|
| **Dapp UI** | `https://x402guard.acedata.cloud/` | Human (browser + Phantom) | Create vault, top up, set policy, audit, pause, clawback |
| **Backend API** | `https://x402guard.acedata.cloud/api/*` | The Dapp UI + the MCP layer | Stateless API that builds Solana txs and persists vault metadata |
| **MCP endpoint** | `https://x402guard.acedata.cloud/mcp/<session-token>` | The agent (Claude / Cursor / etc.) | Streamable HTTP MCP server. Tools: `aceguard.spend`, `aceguard.balance`, `aceguard.history`. Each token is bound to one vault. |

The agent never knows what x402guard is doing. It just sees an MCP tool called `aceguard.spend` and one called `aceguard.pay_for_api` (which wraps spend + x402 retry).

---

## 4. End-to-end flow (the demo)

```
┌────────────┐       ┌──────────────────────┐       ┌────────────────────┐
│ Alice      │       │ x402guard.acedata    │       │ Solana Mainnet     │
│ + Phantom  │──(1)─▶│ Dapp UI              │──(2)─▶│ AgentVault Program │
└────────────┘       └──────────────────────┘       └────────────────────┘
       │                       │                              │
       │                       ▼                              │
       │             generates (3) personal MCP URL           │
       │           https://x402guard.acedata.cloud/mcp/abc123 │
       │                                                      │
       └──(4)──pasted into Claude Desktop config─────────┐    │
                                                         ▼    │
                                              ┌──────────────────┐
                                              │ Claude Desktop   │
                                              │   + aceguard MCP │
                                              └──────────────────┘
                                                         │
                                                         │ "make me a
                                                         │  birthday card"
                                                         ▼
                                              ┌──────────────────┐
                                              │ aceguard.        │
                                              │ pay_for_api(     │
                                              │   "midjourney/   │
                                              │    imagine",     │
                                              │   prompt)        │
                                              └──────────────────┘
                                                         │
        ┌────────────────────────────────────────────────┘
        ▼
    POST api.acedata.cloud/midjourney/imagine     (no auth)
        │
        ▼ HTTP 402 {accepts: [{network: solana, asset: USDC, amount: 0.025, payTo: ...}]}
        │
        ▼ x402guard backend:
        │   ① Calls AgentVault.spend(vault, 0.025, payTo) on Solana
        │   ② On-chain program verifies policy:
        │        - delegation key still active? ✅
        │        - daily cap (2 USDC) — used 0, remaining 2 ✅
        │        - per-call cap (0.5 USDC) — 0.025 ≤ 0.5 ✅
        │        - endpoint allowlist *.acedata.cloud ✅
        │   ③ Program signs PDA → USDC transfers on-chain
        │   ④ tx hash: 4fsVAukg…D1Gd3t
        │
        ▼ x402guard backend constructs X-Payment header from tx, retries:
        │
        ▼ POST api.acedata.cloud/midjourney/imagine
            X-Payment: <signed envelope referencing tx 4fsV…3t>
        │
        ▼ 200 OK → image URL returned to Claude → shown to Alice
```

**Then we demo the rejections** (this is the fun part):

| Test | Expected | What evaluators see |
|---|---|---|
| Agent tries to pay `evil-api.com` (not on allowlist) | program rejects | red toast in UI, on-chain `Custom Error: 0x1771` (PolicyViolation) |
| Agent tries to spend 1.5 USDC in one shot (per-call cap = 0.5) | program rejects | same |
| Agent makes 100 micro-spends to drain daily cap | first ~80 succeed, rest rejected | budget bar in UI fills, then turns red |
| Alice clicks **Pause Vault** in the UI mid-demo | residual USDC clawed back to her main wallet, agent's next call gets `VaultPaused` | live tx on Solscan |

Every rejection happens **on-chain**, not in the backend. That's the whole point. If the backend gets pwned, the on-chain program is still the spend boundary.

---

## 5. Solana-native, ground-up — defense for judges

| Component | Solana-native primitive used | Why no other chain works |
|---|---|---|
| Vault account | **PDA** (`["vault", owner, agent_id]`) | EVM has no keyless deterministic accounts. ERC-4337 is a multi-tx orchestration; PDA is a single primitive baked into runtime. |
| Vault holds USDC | **Token-2022 mint** (preserve future hooks) + standard SPL fallback | EVM has no equivalent of transfer hooks at the token layer; you'd need a custom token wrapper. |
| Policy enforcement | **Anchor `#[account]` + custom `PolicyAccount` PDA** sibling | Same struct on EVM = a contract per vault = factory pattern + 100x gas |
| Atomic spend + ledger update | One Solana ix updates `used_today`, transfers USDC, emits `SpendEvent` | EVM would need 3 separate calls or a single bloated function |
| Sub-cent fee economics | ~5000 lamports / spend ≈ $0.0008 at SOL ~$160 | A 0.025 USDC spend on Ethereum L1 costs more in gas than the spend itself |
| Wallet UX | Phantom wallet adapter, native SPL, no bridges | Every other chain needs MetaMask + bridge UX |

We never say "we support Solana, Base, and SKALE." We say **"we are built on Solana."** The fact that the underlying x402 payment library happens to also have non-Solana settlement paths is upstream-library trivia and not part of the x402guard pitch.

---

## 6. The Anchor program (≈ 200 LoC)

`programs/agent_vault/src/lib.rs`:

```rust
#[program]
pub mod agent_vault {
    pub fn create_vault(
        ctx: Context<CreateVault>,
        agent_id: [u8; 32],
        policy: Policy,
    ) -> Result<()> {
        // PDAs: ["vault", owner, agent_id], ["policy", vault]
        // Init associated token account for USDC mint owned by vault PDA.
    }

    pub fn top_up(ctx: Context<TopUp>, amount: u64) -> Result<()> {
        // Anyone can SPL-transfer USDC into the vault's ATA.
        // We expose this for completeness; users can also just use Phantom directly.
    }

    pub fn spend(
        ctx: Context<Spend>,
        amount: u64,
        recipient: Pubkey,
        endpoint_hash: [u8; 32],
        nonce: u64,
    ) -> Result<()> {
        let policy = &mut ctx.accounts.policy;
        let clock = Clock::get()?;

        require!(!policy.paused, VaultError::VaultPaused);
        require!(clock.unix_timestamp < policy.expires_at, VaultError::VaultExpired);
        require!(amount <= policy.per_call_cap, VaultError::PerCallCapExceeded);

        // Reset daily counter if a new UTC day has started.
        let today = clock.unix_timestamp / 86_400;
        if policy.day_index != today {
            policy.day_index = today;
            policy.used_today = 0;
        }
        require!(
            policy.used_today + amount <= policy.daily_cap,
            VaultError::DailyCapExceeded
        );

        require!(
            policy.endpoint_allowlist.iter().any(|h| h == &endpoint_hash),
            VaultError::EndpointNotAllowed
        );

        require!(
            ctx.accounts.delegation.signer == policy.delegation_key,
            VaultError::DelegationKeyMismatch
        );
        // Replay protection
        require!(nonce > policy.last_nonce, VaultError::NonceReplay);
        policy.last_nonce = nonce;

        // PDA-signed SPL transfer.
        let seeds: &[&[&[u8]]] = &[&[
            b"vault",
            ctx.accounts.owner.as_ref(),
            &policy.agent_id,
            &[ctx.accounts.vault.bump],
        ]];
        token::transfer(
            CpiContext::new_with_signer(
                ctx.accounts.token_program.to_account_info(),
                token::Transfer {
                    from: ctx.accounts.vault_ata.to_account_info(),
                    to: ctx.accounts.recipient_ata.to_account_info(),
                    authority: ctx.accounts.vault.to_account_info(),
                },
                seeds,
            ),
            amount,
        )?;

        policy.used_today += amount;

        emit!(SpendEvent {
            vault: ctx.accounts.vault.key(),
            amount,
            recipient,
            endpoint_hash,
            ts: clock.unix_timestamp,
        });
        Ok(())
    }

    pub fn pause(ctx: Context<OwnerOnly>) -> Result<()> { /* policy.paused = true */ }
    pub fn resume(ctx: Context<OwnerOnly>) -> Result<()> { /* policy.paused = false */ }
    pub fn update_policy(ctx: Context<OwnerOnly>, new_policy: PolicyUpdate) -> Result<()> { /* … */ }

    pub fn clawback(ctx: Context<OwnerOnly>) -> Result<()> {
        // PDA-signed transfer of full balance back to owner's USDC ATA.
    }
}

#[account]
pub struct Policy {
    pub owner: Pubkey,
    pub agent_id: [u8; 32],
    pub delegation_key: Pubkey,        // Ed25519 pubkey held by x402guard backend session
    pub daily_cap: u64,                // in USDC base units (1_000_000 = 1 USDC)
    pub per_call_cap: u64,
    pub endpoint_allowlist: Vec<[u8; 32]>, // sha256(host) up to 8 entries
    pub expires_at: i64,
    pub paused: bool,
    pub day_index: i64,
    pub used_today: u64,
    pub last_nonce: u64,
}
```

Errors that map directly to UI toasts:

```rust
#[error_code]
pub enum VaultError {
    VaultPaused, VaultExpired,
    PerCallCapExceeded, DailyCapExceeded,
    EndpointNotAllowed, DelegationKeyMismatch,
    NonceReplay,
}
```

---

## 7. Where does the delegation key live?

The thing the agent uses to authorise a `spend()` ix is **not Alice's private key**. It's a fresh Ed25519 keypair generated when the vault is created — the `delegation_key` field in `Policy`.

For the hackathon, we put it in **server-side custody, encrypted at rest with a key Alice signs once**:

1. On vault creation, the backend generates `delegation_key` (Ed25519).
2. Alice signs a fixed challenge with Phantom; we use HKDF on her signature to derive `K_alice`.
3. Backend stores `enc(K_alice, delegation_priv)` in Postgres + the public key `delegation_pub` is set as `policy.delegation_key` on-chain.
4. The MCP session token Alice gets (`/mcp/abc123`) is opaque; it grants permission to *use* the delegation key to sign Solana txs that call `agent_vault.spend(...)`.
5. **Defense-in-depth**: even if our DB is dumped, attackers can only spend within `daily_cap` × `endpoint_allowlist` until Alice clicks Pause. The on-chain program is the actual security boundary, not us.

V2 (post-hackathon) replaces server custody with browser-held WebAuthn passkeys. Out of scope for May 11.

---

## 8. Repos and ownership

This is a **brand-new public GitHub repo**. Submitted as the hackathon entry.

```
github.com/AceDataCloud/x402guard
├── programs/agent_vault/        Anchor program (Rust, Solana mainnet)
├── tests/                       Anchor tests + a localnet end-to-end test
├── api/                         FastAPI backend (Python 3.11)
│   ├── core/                    settings, db, solana RPC client
│   ├── routes/
│   │   ├── auth.py              Phantom signature → session
│   │   ├── vaults.py            CRUD over vaults + tx builders
│   │   └── mcp.py               Streamable HTTP MCP per /mcp/<token>
│   └── crypto/                  Phantom signature verify, key wrapping
├── web/                         Vue 3 + Vite (cribbed from Nexior layout)
│   ├── src/pages/               Home, Connect, NewVault, VaultDetail, History
│   ├── src/components/wallet/   Phantom adapter (lifted from Nexior)
│   └── src/composables/         useVault, useSpendHistory
├── docker-compose.yaml          Postgres + api + web for local dev
├── deploy/production/           K8s manifests, mirrors AceDataCloud conventions
└── README.md                    The pitch + reproduce-the-demo runbook
```

Reuses (as dependencies, not vendored code):
- `@acedatacloud/x402-client` — npm dep in `web/`. We use *only* the Solana path.
- `@solana/web3.js`, `@coral-xyz/anchor`, `@solana/spl-token`
- `@solana/wallet-adapter-react` for the Phantom plumbing

We do **not** import `FacilitatorX402` directly. The x402-client routes settlement through `https://facilitator.acedata.cloud` (which we operate); that's a runtime configuration of the SDK, not code we ship in this repo.

---

## 9. Six-day build plan

D-day = May 5 (today). Submission cutoff = May 11.

| Day | Track A — Anchor | Track B — Backend + MCP | Track C — Web UI |
|---|---|---|---|
| **Day 1 (May 5)** | Scaffold Anchor workspace; `create_vault`, `top_up` only; happy-path test on localnet | FastAPI skeleton + Postgres schema (`Vault`, `MCPSession`); Phantom-sig auth; *no Solana yet* | Vue scaffold from Nexior layout; Phantom connect; `Home` + `Connect` pages |
| **Day 2 (May 6)** | `spend` with daily/per-call cap; nonce replay; Anchor errors mapped | tx builders for `create_vault` + `top_up` (returns base64 unsigned tx for Phantom to sign) | `NewVault` form (4 inputs); call backend, push unsigned tx to Phantom, await confirmation |
| **Day 3 (May 7)** | `pause`, `clawback`, `update_policy`; localnet integration test for full lifecycle | Streamable HTTP MCP at `/mcp/<token>`; tools: `aceguard.balance`, `aceguard.history`, `aceguard.spend` | `VaultDetail` page: balance, policy, spend history (server-side fetch + Solana RPC fallback) |
| **Day 4 (May 8)** | Deploy program to **devnet**; mint a fake USDC (or use Circle devnet USDC); fund test wallets | `aceguard.pay_for_api` MCP tool: composes `spend` + x402 retry against `api.acedata.cloud` | `History` page; on-chain event listener (Solana logs subscription) feeds live UI updates |
| **Day 5 (May 9)** | **Mainnet deploy**, real USDC (mint `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v`) | Hosted MCP behind nginx ingress; rate-limit per session; CLS log line per spend | Polishing: error toasts mapped to Anchor error codes; mobile layout; Solscan deep links |
| **Day 6 (May 10)** | Bug-bash from real demo runs; final security pass on `seeds`/PDA derivation; explorer links in tests | Hardening: replay nonce DB → on-chain only; review key custody; e2e script for the demo | Record demo video; landing-page copy; submit |

Cushion of ~24h before May 11 cutoff for whatever inevitably breaks.

---

## 10. Demo script (4 minutes, what we record)

| Time | Camera | Voiceover |
|---|---|---|
| 0:00–0:20 | Open `https://x402guard.acedata.cloud`. Phantom in corner. | *"AI agents are about to spend money. Today the only options are 'give it your private key' or 'approve every transaction by hand.' Both are broken. We built a third option."* |
| 0:20–0:50 | Click Connect → Phantom popup → sign. Page now shows "No vaults yet." Click **New Vault**. Fill: agent name `Claude-Birthday-Helper`, daily 2 USDC, per-call 0.5, allowlist `*.acedata.cloud`, expires in 7 days. Click Create → Phantom signs `create_vault` tx → confirmed. | *"Alice gives her agent its own wallet — but every spending rule lives on a Solana program, not on the agent's machine."* |
| 0:50–1:20 | Top up 5 USDC via the **Top Up** button (Phantom signs an SPL transfer). Page shows balance 5 USDC, MCP URL `https://x402guard.acedata.cloud/mcp/abc123`. **Copy** button. | *"Vault is now funded. Alice copies a per-vault MCP URL — that's the only thing the agent ever sees."* |
| 1:20–1:50 | Cut to Claude Desktop config: paste MCP URL into `~/.claude/config.json`. Restart. Claude shows `aceguard` tools available. | *"Any MCP-compatible client works — Claude, Cursor, Cline, custom agents."* |
| 1:50–2:50 | Type into Claude: *"make me a birthday card for my mom, watercolor style with flowers."* Claude calls `aceguard.pay_for_api(midjourney/imagine, …)`. Split-screen: left = Claude tool log, right = `x402guard.acedata.cloud/vault/<id>` live updating. Watch balance go 5 → 4.975, see new spend row, click → Solscan tx page. Image returns to Claude. | *"Claude pays autonomously. The Solana program signed the transfer with the vault's PDA — no private key was ever exposed to the agent. Every spend is on Solscan."* |
| 2:50–3:30 | Try to break it. Tell Claude: *"call evil-api.com instead."* Claude tries `aceguard.pay_for_api`. Backend submits `spend()` ix. Solana rejects: `EndpointNotAllowed`. Toast in UI. Then: *"do 100 of these"* — first ~80 succeed, day cap fills, rest get `DailyCapExceeded`. | *"The boundary isn't trust. It's the on-chain program. Even if we get pwned, your wallet is still safe."* |
| 3:30–3:55 | Alice clicks **Pause** in UI → Phantom signs → tx confirmed → 4.95 remaining USDC clawed back to her main wallet. | *"And she's always one click from full clawback."* |
| 3:55–4:00 | Logo + GitHub URL. | *"x402guard. Built on Solana, ground up."* |

---

## 11. What we are explicitly **not** doing

- **No browser extension.** A website + MCP endpoint covers every demo flow. Avoids Manifest V3 / store review / cross-platform packaging entirely.
- **No custom token.** USDC only. (V2: any SPL.)
- **No Token-2022 transfer hooks.** We design the program to be hook-compatible later, but for the hackathon the policy check happens in our `spend` ix, not as a hook. Saves ~1.5 days.
- **No DCA / scheduled spends.** Alice can write that as an agent if she wants. Not in scope.
- **No multi-agent / shared vaults.** One owner, one agent per vault. (V2: multiple `agent_id`s per vault.)
- **No mobile.** Desktop web only on May 11.
- **No multi-chain in the pitch.** Anywhere. The fact that the upstream `@acedatacloud/x402-client` library happens to also support Base/SKALE is upstream library trivia and stays out of every README, slide, and tweet associated with the submission.

---

## 12. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Anchor learning curve eats Day 1–2 | medium | Use Anchor's Counter example as scaffold; one of us pre-reads Solana Cookbook tonight |
| Mainnet USDC liquidity for demo wallet | low | We have USDC from FacilitatorX402 ops; pre-fund the demo wallet from there |
| `api.acedata.cloud` x402 path returns wrong settlement on Solana | low | Already verified live (see X402Client README, 2026-04-25 settlements) |
| MCP Streamable HTTP spec drift | low | Use FastMCP stdlib used by our existing MCP servers; same wire format |
| Phantom `signMessage` doesn't survive page reload | medium | Cache derived `K_alice` in IndexedDB with a 24h expiry; require re-sign after that |
| On-chain spend takes >2s and breaks UX | medium | Pre-build & sign the `spend` ix during `pay_for_api` while the x402 server is computing; submit when 402 lands. Localnet RTT <1s, mainnet 2–3s. |
| Domain `x402guard.acedata.cloud` SSL provisioning | low | Same Caddy + ACME pipeline as `caddy-test.germey.tech` (already verified) |

---

## 13. Why we'll win (or at least place)

- **Solana primitives, used correctly.** PDA, SPL, Anchor errors, on-chain events, sub-cent fees — every one is *load-bearing*, not decoration. Judges who care about depth will see this in 60 seconds of code review.
- **Working live demo on mainnet.** Not localnet. Not testnet. Real USDC, real `api.acedata.cloud` 402 calls, real Solscan tx hashes.
- **Narrative judges already believe in.** Anatoly has been saying "agents need wallets" all year. Phantom and Reflect are actively investing in agentic commerce. We're the safety primitive that makes it consumer-safe.
- **One sentence pitch survives the hallway test.** *"Give your AI agent a Solana wallet. Keep the rules on-chain."* Judges, panelists, and Twitter all repeat the same line.
- **Real ownership.** This isn't a fork or a wrapper. It's a new program, a new product, a new brand — and it lives on Solana from byte zero.

---

## 14. Post-hackathon (if we win)

- Move delegation key custody to user-side WebAuthn passkeys.
- Token-2022 transfer hook integration so the policy check happens at the token layer for *any* SPL transfer out of the vault — not just our `spend` ix.
- Open the policy schema (zk allowlists, signed external attestations like "agent has SOC2 cert").
- License the program to other agent platforms; they all need this.
- Apply to Colosseum's accelerator with the $250k pre-seed.

---

*Owner: AceDataCloud. Authors: TBD team for Frontier 2026. Last updated: 2026-05-05.*
