//! # x402guard — `agent_vault` Anchor program
//!
//! Solana-native spending guardrails for AI agents.
//! Hackathon submission for [Colosseum Frontier 2026](https://colosseum.com/frontier).
//!
//! ## Account model
//!
//! Two PDAs per `(owner, agent_id)`:
//!
//! | PDA      | Seeds                              | Holds                            |
//! |----------|------------------------------------|----------------------------------|
//! | `Vault`  | `["vault", owner, agent_id]`       | metadata + USDC ATA authority    |
//! | `Policy` | `["policy", vault]`                | spending rules + bookkeeping     |
//!
//! The vault's USDC is held in a standard SPL associated token account whose
//! authority is the `Vault` PDA — i.e. only this program can move it out, and only
//! through `spend` (added in a follow-up PR).
//!
//! ## Instructions
//!
//! - `create_vault`  ✅
//! - `spend`         ✅ (policy enforcement + PDA-signed transfer)
//! - `pause`         ✅ this PR
//! - `resume`        ✅ this PR
//! - `update_policy` ✅ this PR
//! - `clawback`      ✅ this PR
//!
//! See [`README`](https://github.com/AceDataCloud/x402guard) and
//! [`.plans/X402GUARD.md`](https://github.com/AceDataCloud/x402guard/blob/main/.plans/X402GUARD.md)
//! for the architectural picture.

use anchor_lang::prelude::*;

pub mod errors;
pub mod instructions;
pub mod state;

pub use errors::*;
pub use instructions::*;
pub use state::*;

declare_id!("5s9rscxcoXZMLwn2cenGYhj6zd5voyMHAmFBe4qhZQxH");

#[program]
pub mod agent_vault {
    use super::*;

    /// Create a new agent vault for the signing owner. Initialises both PDAs and
    /// the vault's SPL USDC associated token account in a single ix.
    pub fn create_vault(ctx: Context<CreateVault>, args: CreateVaultArgs) -> Result<()> {
        instructions::create_vault::handler(ctx, args)
    }

    /// Spend USDC out of a vault. Authorised by the vault's delegation key,
    /// not the owner. The program enforces every policy gate (paused, expired,
    /// daily cap, per-call cap, allowlist, nonce replay) before transferring.
    pub fn spend(ctx: Context<Spend>, args: SpendArgs) -> Result<()> {
        instructions::spend::handler(ctx, args)
    }

    /// Owner-only: temporarily disable spends without changing any policy values.
    /// Idempotent; calling on an already-paused vault is a no-op.
    pub fn pause(ctx: Context<OwnerOnly>) -> Result<()> {
        instructions::owner_ops::pause(ctx)
    }

    /// Owner-only: clear the paused flag set by `pause`.
    pub fn resume(ctx: Context<OwnerOnly>) -> Result<()> {
        instructions::owner_ops::resume(ctx)
    }

    /// Owner-only: mutate any subset of the policy's tunable fields. Re-validates
    /// per_call <= daily and expires_at > now whenever those are touched.
    pub fn update_policy(
        ctx: Context<OwnerOnly>,
        args: UpdatePolicyArgs,
    ) -> Result<()> {
        instructions::owner_ops::update_policy(ctx, args)
    }

    /// Owner-only: sweep the entire vault USDC balance back to the owner and
    /// pause the vault atomically. Closing-the-door semantics, not just drain.
    pub fn clawback(ctx: Context<OwnerClawback>) -> Result<()> {
        instructions::owner_ops::clawback(ctx)
    }
}
