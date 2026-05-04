//! On-chain account types for x402guard.
//!
//! Two PDAs per agent:
//! - **Vault**  (`["vault", owner, agent_id]`)        — owns the SPL USDC ATA, no private key
//! - **Policy** (`["policy", vault]`)                  — the rules + spend bookkeeping
//!
//! The associated token account holding USDC is owned by the vault PDA;
//! the program is therefore the only authority that can move funds out of it.

use anchor_lang::prelude::*;

/// Maximum number of endpoint hashes (sha256(host)) the policy can allow.
/// 8 covers the realistic spread (`*.acedata.cloud`, vendor-specific endpoints, etc.)
/// while keeping account size predictable.
pub const MAX_ALLOWLIST: usize = 8;

/// PDA seeds.
pub const SEED_VAULT: &[u8] = b"vault";
pub const SEED_POLICY: &[u8] = b"policy";

#[account]
#[derive(Debug)]
pub struct Vault {
    /// User who owns this vault. Only this signer can pause / resume / clawback / update policy.
    pub owner: Pubkey,
    /// Application-defined agent identifier, supplied by the owner at creation.
    /// Lets one user own multiple distinct vaults (e.g. one per agent persona).
    pub agent_id: [u8; 32],
    /// USDC mint this vault holds. Locked at creation so the policy can't be evaded
    /// by swapping in a different SPL mint later.
    pub usdc_mint: Pubkey,
    pub bump: u8,
    pub created_at: i64,
}

impl Vault {
    /// 8-byte discriminator + struct fields.
    pub const SIZE: usize = 8 + 32 + 32 + 32 + 1 + 8;
}

#[account]
#[derive(Debug)]
pub struct Policy {
    pub vault: Pubkey,
    /// Ed25519 public key allowed to authorise `spend` ixs. Held by the x402guard
    /// backend session for the hackathon; v2 will move this to user-side WebAuthn.
    pub delegation_key: Pubkey,
    /// Spending caps in USDC base units (1_000_000 = 1 USDC).
    pub daily_cap: u64,
    pub per_call_cap: u64,
    /// `sha256(host)` of each allowed endpoint. Fixed-size array for predictable
    /// account size; `allowlist_len` tells the program how many slots are populated.
    pub endpoint_allowlist: [[u8; 32]; MAX_ALLOWLIST],
    pub allowlist_len: u8,
    pub expires_at: i64,
    pub paused: bool,
    /// `unix_ts / 86_400` of the day represented by `used_today`.
    /// When the program advances to a new day, `used_today` is reset to 0.
    pub day_index: i64,
    pub used_today: u64,
    /// Strictly-monotonic spend nonce for replay protection.
    pub last_nonce: u64,
    pub bump: u8,
}

impl Policy {
    pub const SIZE: usize = 8        // anchor discriminator
        + 32                          // vault
        + 32                          // delegation_key
        + 8 + 8                       // daily_cap + per_call_cap
        + 32 * MAX_ALLOWLIST          // endpoint_allowlist
        + 1                           // allowlist_len
        + 8                           // expires_at
        + 1                           // paused
        + 8                           // day_index
        + 8                           // used_today
        + 8                           // last_nonce
        + 1;                          // bump
}
