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
//! - `create_vault` ✅ this PR
//! - `spend`        — follow-up PR (policy enforcement + PDA-signed transfer)
//! - `pause` / `resume` / `clawback` / `update_policy` — follow-up PRs
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

declare_id!("Vau1tGuArD11111111111111111111111111111111");

#[program]
pub mod agent_vault {
    use super::*;

    /// Create a new agent vault for the signing owner. Initialises both PDAs and
    /// the vault's SPL USDC associated token account in a single ix.
    pub fn create_vault(ctx: Context<CreateVault>, args: CreateVaultArgs) -> Result<()> {
        instructions::create_vault::handler(ctx, args)
    }
}
