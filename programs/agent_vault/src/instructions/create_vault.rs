//! `create_vault` — initialises both PDAs and the vault's USDC ATA.
//!
//! After this ix lands the user can top up the vault by SPL-transferring USDC into
//! `vault_usdc_ata` from any wallet (Phantom, ourselves, etc.) — no further on-chain
//! state change is required for top-ups.

use anchor_lang::prelude::*;
use anchor_spl::associated_token::AssociatedToken;
use anchor_spl::token::{Mint, Token, TokenAccount};

use crate::errors::VaultError;
use crate::state::{Policy, Vault, MAX_ALLOWLIST, SEED_POLICY, SEED_VAULT};

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Debug)]
pub struct CreateVaultArgs {
    /// Owner-supplied opaque agent identifier (e.g. sha256 of the agent name).
    /// Used as a PDA seed so one owner can hold many vaults.
    pub agent_id: [u8; 32],

    /// Ed25519 pubkey allowed to authorise `spend` ixs against this vault.
    pub delegation_key: Pubkey,

    /// Spending caps in USDC base units. `1 USDC = 1_000_000`.
    pub daily_cap: u64,
    pub per_call_cap: u64,

    /// `sha256(host)` of each permitted endpoint. Up to `MAX_ALLOWLIST` (8) entries.
    pub endpoint_allowlist: Vec<[u8; 32]>,

    /// Unix timestamp (seconds). Must be strictly in the future at submit time.
    pub expires_at: i64,
}

#[derive(Accounts)]
#[instruction(args: CreateVaultArgs)]
pub struct CreateVault<'info> {
    #[account(mut)]
    pub owner: Signer<'info>,

    #[account(
        init,
        payer = owner,
        space = Vault::SIZE,
        seeds = [SEED_VAULT, owner.key().as_ref(), &args.agent_id],
        bump,
    )]
    pub vault: Account<'info, Vault>,

    #[account(
        init,
        payer = owner,
        space = Policy::SIZE,
        seeds = [SEED_POLICY, vault.key().as_ref()],
        bump,
    )]
    pub policy: Account<'info, Policy>,

    /// USDC mint. The deployer enforces this is real USDC at deploy-config level
    /// (program does not hardcode the mint so we can also test on devnet).
    pub usdc_mint: Account<'info, Mint>,

    #[account(
        init,
        payer = owner,
        associated_token::mint = usdc_mint,
        associated_token::authority = vault,
    )]
    pub vault_usdc_ata: Account<'info, TokenAccount>,

    pub system_program: Program<'info, System>,
    pub token_program: Program<'info, Token>,
    pub associated_token_program: Program<'info, AssociatedToken>,
    pub rent: Sysvar<'info, Rent>,
}

pub fn handler(ctx: Context<CreateVault>, args: CreateVaultArgs) -> Result<()> {
    require!(
        args.per_call_cap <= args.daily_cap,
        VaultError::PerCallExceedsDaily
    );
    require!(
        args.endpoint_allowlist.len() <= MAX_ALLOWLIST,
        VaultError::AllowlistTooLong
    );

    let clock = Clock::get()?;
    require!(
        args.expires_at > clock.unix_timestamp,
        VaultError::ExpirationInPast
    );

    let vault = &mut ctx.accounts.vault;
    vault.owner = ctx.accounts.owner.key();
    vault.agent_id = args.agent_id;
    vault.usdc_mint = ctx.accounts.usdc_mint.key();
    vault.bump = ctx.bumps.vault;
    vault.created_at = clock.unix_timestamp;

    let policy = &mut ctx.accounts.policy;
    policy.vault = vault.key();
    policy.delegation_key = args.delegation_key;
    policy.daily_cap = args.daily_cap;
    policy.per_call_cap = args.per_call_cap;

    let mut allow = [[0u8; 32]; MAX_ALLOWLIST];
    for (i, hash) in args.endpoint_allowlist.iter().enumerate() {
        allow[i] = *hash;
    }
    policy.endpoint_allowlist = allow;
    policy.allowlist_len = args.endpoint_allowlist.len() as u8;

    policy.expires_at = args.expires_at;
    policy.paused = false;
    policy.day_index = clock.unix_timestamp / 86_400;
    policy.used_today = 0;
    policy.last_nonce = 0;
    policy.bump = ctx.bumps.policy;

    emit!(VaultCreated {
        vault: vault.key(),
        owner: vault.owner,
        agent_id: vault.agent_id,
        delegation_key: policy.delegation_key,
        daily_cap: policy.daily_cap,
        per_call_cap: policy.per_call_cap,
        expires_at: policy.expires_at,
    });

    Ok(())
}

#[event]
pub struct VaultCreated {
    pub vault: Pubkey,
    pub owner: Pubkey,
    pub agent_id: [u8; 32],
    pub delegation_key: Pubkey,
    pub daily_cap: u64,
    pub per_call_cap: u64,
    pub expires_at: i64,
}
