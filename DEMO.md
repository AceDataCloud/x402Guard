# Demo runbook — Colosseum Frontier 2026

> A reproducible 4-minute end-to-end demo of x402guard, suitable for the submission video and live walkthroughs.

## Pre-flight checklist (T-30 minutes)

Run through this in order. Each step is independently verifiable.

### 1. Anchor program is on Solana

```bash
# From the repo root.
solana config set --url devnet     # or mainnet for the final cut
solana-keygen new -o keypairs/program.json --no-bip39-passphrase --force

# Patch the placeholder declare_id! with the real one.
PROGRAM_ID=$(solana address -k keypairs/program.json)
sed -i.bak "s|56TbAziiW8pDHFpRsxfnfBUfimBRTMCHw4gwDGw9uPW6|$PROGRAM_ID|g" \
  programs/agent_vault/src/lib.rs Anchor.toml api/.env.example

anchor build
anchor deploy --program-keypair keypairs/program.json
```

Verify:

```bash
solana program show "$PROGRAM_ID"
```

### 2. Demo wallet is funded

```bash
# Phantom export the seed → solana-keygen recover.
solana balance <ALICE_PUBKEY>     # >= 0.1 SOL
spl-token accounts --owner <ALICE_PUBKEY> | grep -i usdc
                                   # >= 5 USDC at the Circle mint above
```

For devnet, `spl-token mint` from the test mint or use a faucet.

### 3. Backend is reachable

```bash
curl -sS https://x402guard.acedata.cloud/health
# {"status":"ok","version":"0.1.0"}

curl -sS https://x402guard.acedata.cloud/.well-known/x402guard
# {"service":"x402guard", "cluster":"mainnet", "agent_vault_program_id":"...", "usdc_mint":"EPj..."}
```

The `agent_vault_program_id` field must match the on-chain ID from step 1.

### 4. Phantom is on the right cluster

In Phantom: ⚙️ Settings → Developer Settings → Change Network → Mainnet (or Devnet for the dry run). The Dapp reads cluster from `/.well-known` so the wallet must agree.

---

## The 4-minute demo

Times are markers for the final edit; live run is closer to 6 minutes including narration pauses.

### 0:00–0:20 — opening

> Alice opens https://x402guard.acedata.cloud . Phantom in the corner of the screen.

> Voiceover: *"AI agents are about to spend money. Today the only options are 'give it your private key' or 'approve every transaction by hand.' Both are broken. We built a third option."*

### 0:20–0:50 — connect + create vault

1. Click **Connect Phantom** → wallet popup → approve.
2. Click **+ New vault**.
3. Fill the form:

   | Field | Value |
   |---|---|
   | Agent name | `Claude-Birthday-Helper` |
   | Daily cap (USDC) | `2` |
   | Per-call cap (USDC) | `0.5` |
   | Expires in | `7 days` |
   | Allowlist | `api.acedata.cloud` |

4. Click **Create vault** → Phantom popup → approve. ~3s wait for confirmation, then the page redirects to the vault detail.

> Voiceover: *"Alice gives her agent its own wallet — but every spending rule lives on a Solana program, not on the agent's machine."*

### 0:50–1:20 — top up

1. On the detail page → **Top up** card → enter `5` → **Send USDC**.
2. Phantom popup → approve. ~3s confirmation.
3. Click the on-screen tx link → Solscan opens, showing the SPL transfer to the vault PDA.

> Voiceover: *"Vault is now funded with 5 USDC. The vault PDA is just an address — there's no private key to steal."*

### 1:20–1:50 — issue MCP URL + paste into Claude

1. **MCP sessions** card → enter label `claude-desktop` → **+ New MCP URL**.
2. Click **Copy** on the new row.
3. Cut to terminal:

   ```bash
   cat ~/.claude/claude_desktop_config.json
   # paste the URL into mcpServers.aceguard.url, save, relaunch Claude.
   ```

   Example config:

   ```json
   {
     "mcpServers": {
       "aceguard": {
         "url": "https://x402guard.acedata.cloud/mcp/<TOKEN>"
       }
     }
   }
   ```

4. Cut back to Claude Desktop — `aceguard_balance`, `aceguard_history`, `aceguard_spend`, `aceguard_pay_for_api` light up in the tools panel.

> Voiceover: *"Any MCP-compatible client works — Claude, Cursor, Cline, custom agents."*

### 1:50–2:50 — happy-path spend

1. In Claude: *"Make me a birthday card for my mom — watercolor flowers."*
2. Claude calls `aceguard_pay_for_api` with the Midjourney imagine endpoint.
3. **Split screen**:
   - Left: Claude's tool log streaming.
   - Right: vault detail page auto-refreshing — balance ticks 5 → 4.975, a new spend row appears, click → Solscan tx page.
4. Image returns to Claude → renders inline.

> Voiceover: *"Claude pays autonomously. The Solana program signed the transfer with the vault's PDA — no private key was ever exposed to the agent. Every spend is on Solscan."*

### 2:50–3:30 — show the boundary

1. In Claude: *"Now call evil-api.com instead."*
2. Claude calls `aceguard_pay_for_api`. Backend submits `spend()` ix.
3. Tool log shows: `spend rejected: endpoint_not_allowed`. Toast on the Dapp side.
4. In Claude: *"Do 100 of these images."* → first ~80 succeed, then `spend rejected: daily_cap_exceeded` → Dapp progress bar fills + turns red.

> Voiceover: *"The boundary isn't trust. It's the on-chain program. Even if we get pwned, your wallet is still safe."*

### 3:30–3:55 — clawback

1. Click **Clawback**. Confirmation dialog → confirm.
2. Phantom popup → approve. ~3s confirmation.
3. Vault status switches to **Paused**. Balance drops to 0. The owner's USDC ATA balance ticks up by the residual amount in Phantom.

> Voiceover: *"And she's always one click from full clawback."*

### 3:55–4:00 — outro

> Logo + GitHub URL. *"x402guard. Built on Solana, ground up."*

---

## Capturing the video

```bash
# 1080p screen capture using macOS's built-in.
# brew install ffmpeg
ffmpeg -f avfoundation -framerate 30 -i "1:0" \
  -c:v libx264 -preset slow -crf 18 \
  -c:a aac -b:a 192k \
  demo.mp4

# Or use Loom / OBS / Screen Studio. Final upload to YouTube
# unlisted + cross-post to Twitter for the submission.
```

## Failure recovery during the live demo

| Symptom | Recovery |
|---|---|
| Phantom shows "transaction failed" | Page refresh, click Create vault again — backend rebuilds the same tx because the row is keyed off `vault_pda`. |
| Solana RPC times out (mainnet during peak) | Switch `VITE_SOLANA_RPC_URL` env in `web/.env` to a paid RPC (Helius / QuickNode) and rebuild. |
| `aceguard_pay_for_api` returns "on-chain spend rejected: confirm_timeout" | Retry the same prompt; nonce is freshly issued, no replay risk. |
| Claude Desktop doesn't see the tools after relaunch | Close all Claude windows + relaunch. Tool list refresh happens on app boot, not per-conversation. |

## Post-demo cleanup

```bash
# Optional: delete the demo vault to keep the screenshot story clean.
# In the Dapp: Vault → Clawback (sweeps USDC back) → done.
# The on-chain Vault + Policy PDAs remain (deterministic from name +
# owner) but are paused and empty.
```
