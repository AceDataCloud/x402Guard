# `agent_vault` — x402guard Anchor program

The on-chain spending boundary for x402guard. Holds an agent's USDC inside a PDA-owned associated token account and refuses to release it unless the on-chain `Policy` says yes.

## Build

```bash
# from repo root
anchor build
```

Anchor 0.30.1 + Solana 1.18.x. See [`Anchor.toml`](../../Anchor.toml).

## Deploy

```bash
# devnet
anchor deploy --provider.cluster devnet

# mainnet (production target — only after end-to-end devnet verification)
anchor deploy --provider.cluster mainnet
```

## Test

```bash
# spawns a local validator with USDC mint cloned from devnet
anchor test
```

Tests live under [`../../tests/`](../../tests/) at the workspace root and use `@coral-xyz/anchor` from TypeScript.

## Account model

| PDA | Seeds | Purpose |
|---|---|---|
| `Vault` | `["vault", owner, agent_id]` | Owns the USDC ATA. Holds metadata. No private key. |
| `Policy` | `["policy", vault]` | The rules — caps, allowlist, expiry — plus bookkeeping (used_today, last_nonce). |

The agent's USDC sits in a standard SPL associated token account whose authority is the `Vault` PDA. Only the program can move it, and only through `spend` (next PR).

## Instructions

| Ix | Status | Purpose |
|---|---|---|
| `create_vault` | ✅ | Init both PDAs + USDC ATA in one tx |
| `spend` | ✅ | Validate policy → PDA-sign SPL transfer |
| `pause` / `resume` | ✅ | Owner toggles `policy.paused` |
| `update_policy` | ✅ | Owner-only policy mutation (partial updates allowed) |
| `clawback` | ✅ | Sweep vault back to owner + pause atomically |

## Errors

All custom errors are declared in [`src/errors.rs`](src/errors.rs). Each variant maps directly to a UI toast / MCP error message so the same identifier travels from on-chain → backend logs → user surface.

## Security notes

- The vault's USDC ATA is locked at creation (`vault.usdc_mint`). The policy can't be evaded by swapping in a different SPL mint later.
- `delegation_key` is the *only* signer the upcoming `spend` ix will accept; `Vault.owner` retains full control via `pause` / `clawback` / `update_policy`. There is intentionally no path for `delegation_key` to escalate to owner privileges.
- Replay protection is enforced via a strictly-monotonic per-vault `last_nonce`.
- `MAX_ALLOWLIST = 8` is constant; `Policy::SIZE` is therefore fixed and rent-exempt amounts are predictable.

## Program ID

`Vau1tGuArD11111111111111111111111111111111` — placeholder vanity ID. Will be replaced with a real one generated via `solana-keygen grind` before mainnet deploy.
