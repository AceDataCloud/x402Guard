//! Owner-only ops: `pause`, `resume`, `update_policy`, `clawback`.
//!
//! Grouped in one file because they share the same `OwnerOnly` accounts struct
//! (no token transfer, just policy mutation) and the same security model:
//! the owner is the *only* signer the program will accept here.
//!
//! `clawback` is the exception — it's owner-signed but does move funds, so it
//! gets its own accounts struct (`OwnerClawback`) plus the SPL transfer plumbing.

use anchor_lang::prelude::*;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

use crate::errors::VaultError;
use crate::state::{Policy, Vault, MAX_ALLOWLIST, SEED_POLICY, SEED_VAULT};

// ─── Shared accounts struct ───────────────────────────────────────────────

#[derive(Accounts)]
pub struct OwnerOnly<'info> {
    pub owner: Signer<'info>,

    #[account(
        seeds = [SEED_VAULT, owner.key().as_ref(), &vault.agent_id],
        bump = vault.bump,
        has_one = owner,
    )]
    pub vault: Account<'info, Vault>,

    #[account(
        mut,
        seeds = [SEED_POLICY, vault.key().as_ref()],
        bump = policy.bump,
        has_one = vault,
    )]
    pub policy: Account<'info, Policy>,
}

// ─── pause / resume ───────────────────────────────────────────────────────

pub fn pause(ctx: Context<OwnerOnly>) -> Result<()> {
    let policy = &mut ctx.accounts.policy;
    policy.paused = true;
    emit!(VaultPaused {
        vault: ctx.accounts.vault.key(),
        ts: Clock::get()?.unix_timestamp,
    });
    Ok(())
}

pub fn resume(ctx: Context<OwnerOnly>) -> Result<()> {
    let policy = &mut ctx.accounts.policy;
    policy.paused = false;
    emit!(VaultResumed {
        vault: ctx.accounts.vault.key(),
        ts: Clock::get()?.unix_timestamp,
    });
    Ok(())
}

// ─── update_policy ────────────────────────────────────────────────────────

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Debug)]
pub struct UpdatePolicyArgs {
    /// All fields are `Option<_>`. Anything left `None` is left unchanged.
    /// Using a single ix keeps the program surface small and lets the UI
    /// batch related edits ("change endpoint allowlist + extend expiry") into
    /// one Phantom signature.
    pub delegation_key: Option<Pubkey>,
    pub daily_cap: Option<u64>,
    pub per_call_cap: Option<u64>,
    pub endpoint_allowlist: Option<Vec<[u8; 32]>>,
    pub expires_at: Option<i64>,
}

pub fn update_policy(ctx: Context<OwnerOnly>, args: UpdatePolicyArgs) -> Result<()> {
    let policy = &mut ctx.accounts.policy;

    if let Some(k) = args.delegation_key {
        policy.delegation_key = k;
    }

    // Stage candidate caps so we can validate the per_call <= daily invariant
    // against whichever ones are actually being changed.
    let new_daily = args.daily_cap.unwrap_or(policy.daily_cap);
    let new_per_call = args.per_call_cap.unwrap_or(policy.per_call_cap);
    require!(
        new_per_call <= new_daily,
        VaultError::PerCallExceedsDaily
    );
    policy.daily_cap = new_daily;
    policy.per_call_cap = new_per_call;

    if let Some(allow) = args.endpoint_allowlist {
        require!(
            allow.len() <= MAX_ALLOWLIST,
            VaultError::AllowlistTooLong
        );
        let mut buf = [[0u8; 32]; MAX_ALLOWLIST];
        for (i, h) in allow.iter().enumerate() {
            buf[i] = *h;
        }
        policy.endpoint_allowlist = buf;
        policy.allowlist_len = allow.len() as u8;
    }

    if let Some(expires_at) = args.expires_at {
        let now = Clock::get()?.unix_timestamp;
        require!(expires_at > now, VaultError::ExpirationInPast);
        policy.expires_at = expires_at;
    }

    emit!(PolicyUpdated {
        vault: ctx.accounts.vault.key(),
        delegation_key: policy.delegation_key,
        daily_cap: policy.daily_cap,
        per_call_cap: policy.per_call_cap,
        allowlist_len: policy.allowlist_len,
        expires_at: policy.expires_at,
    });
    Ok(())
}

// ─── clawback ─────────────────────────────────────────────────────────────

#[derive(Accounts)]
pub struct OwnerClawback<'info> {
    #[account(mut)]
    pub owner: Signer<'info>,

    #[account(
        seeds = [SEED_VAULT, owner.key().as_ref(), &vault.agent_id],
        bump = vault.bump,
        has_one = owner,
    )]
    pub vault: Account<'info, Vault>,

    /// Policy isn't strictly needed for the transfer, but we touch it to set
    /// `paused = true` atomically with the sweep so an in-flight `spend` from
    /// the agent can't sneak in between clawback and pause.
    #[account(
        mut,
        seeds = [SEED_POLICY, vault.key().as_ref()],
        bump = policy.bump,
        has_one = vault,
    )]
    pub policy: Account<'info, Policy>,

    #[account(address = vault.usdc_mint)]
    pub usdc_mint: Account<'info, Mint>,

    #[account(
        mut,
        associated_token::mint = usdc_mint,
        associated_token::authority = vault,
    )]
    pub vault_usdc_ata: Account<'info, TokenAccount>,

    /// Owner's USDC ATA — must already exist. Frontend ensures this before
    /// submitting (uses `getOrCreateAssociatedTokenAccount` in the same tx
    /// pre-flight).
    #[account(
        mut,
        token::mint = usdc_mint,
        token::authority = owner,
    )]
    pub owner_usdc_ata: Account<'info, TokenAccount>,

    pub token_program: Program<'info, Token>,
}

pub fn clawback(ctx: Context<OwnerClawback>) -> Result<()> {
    let amount = ctx.accounts.vault_usdc_ata.amount;
    let policy = &mut ctx.accounts.policy;

    // Always pause atomically with the sweep — even on a 0-balance clawback.
    // This is "shut the vault down NOW" semantics, not just "drain it."
    policy.paused = true;

    if amount > 0 {
        let owner_key = ctx.accounts.vault.owner;
        let agent_id = ctx.accounts.vault.agent_id;
        let vault_bump = ctx.accounts.vault.bump;
        let signer_seeds: &[&[&[u8]]] =
            &[&[SEED_VAULT, owner_key.as_ref(), &agent_id, &[vault_bump]]];

        token::transfer(
            CpiContext::new_with_signer(
                ctx.accounts.token_program.to_account_info(),
                Transfer {
                    from: ctx.accounts.vault_usdc_ata.to_account_info(),
                    to: ctx.accounts.owner_usdc_ata.to_account_info(),
                    authority: ctx.accounts.vault.to_account_info(),
                },
                signer_seeds,
            ),
            amount,
        )?;
    }

    emit!(VaultClawback {
        vault: ctx.accounts.vault.key(),
        amount,
        ts: Clock::get()?.unix_timestamp,
    });
    Ok(())
}

// ─── Events ───────────────────────────────────────────────────────────────

#[event]
pub struct VaultPaused {
    pub vault: Pubkey,
    pub ts: i64,
}

#[event]
pub struct VaultResumed {
    pub vault: Pubkey,
    pub ts: i64,
}

#[event]
pub struct PolicyUpdated {
    pub vault: Pubkey,
    pub delegation_key: Pubkey,
    pub daily_cap: u64,
    pub per_call_cap: u64,
    pub allowlist_len: u8,
    pub expires_at: i64,
}

#[event]
pub struct VaultClawback {
    pub vault: Pubkey,
    pub amount: u64,
    pub ts: i64,
}
