//! `spend` — the only path that moves USDC out of a vault.
//!
//! Authorised by the `delegation_key` registered in the vault's `Policy`.
//! All policy gates (paused, expired, daily cap, per-call cap, allowlist, nonce
//! replay) are checked **on-chain**, not in our backend. The backend can be
//! pwned and the user's wallet stays bounded by the on-chain rules.
//!
//! ## Why a separate signer for the delegation
//!
//! Anchor accepts at most one `Signer<'info>` per role; we use it for the
//! delegation authority directly. The owner does *not* need to sign — that's
//! the whole point: the agent is allowed to spend on the owner's behalf, but
//! only within the on-chain policy.

use anchor_lang::prelude::*;
use anchor_spl::associated_token::AssociatedToken;
use anchor_spl::token::{self, Mint, Token, TokenAccount, Transfer};

use crate::errors::VaultError;
use crate::state::{Policy, Vault, SEED_POLICY, SEED_VAULT};

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Debug)]
pub struct SpendArgs {
    /// USDC base units to transfer. `1 USDC = 1_000_000`.
    pub amount: u64,

    /// `sha256(host)` of the API endpoint being paid for. Must be present in
    /// `policy.endpoint_allowlist[..policy.allowlist_len]`.
    pub endpoint_hash: [u8; 32],

    /// Strictly-monotonic per-vault nonce. The program rejects any value
    /// `<= policy.last_nonce`. Backend issues nonces from a per-vault counter
    /// (Postgres SEQUENCE) so we never collide on concurrent spends.
    pub nonce: u64,
}

#[derive(Accounts)]
pub struct Spend<'info> {
    /// Delegation authority. Must match `policy.delegation_key`. This is the
    /// only signer required for a spend — the owner is not present in the tx.
    pub delegation_authority: Signer<'info>,

    #[account(
        seeds = [SEED_VAULT, vault.owner.as_ref(), &vault.agent_id],
        bump = vault.bump,
    )]
    pub vault: Box<Account<'info, Vault>>,

    #[account(
        mut,
        seeds = [SEED_POLICY, vault.key().as_ref()],
        bump = policy.bump,
        has_one = vault,
    )]
    pub policy: Box<Account<'info, Policy>>,

    #[account(address = vault.usdc_mint)]
    pub usdc_mint: Box<Account<'info, Mint>>,

    #[account(
        mut,
        associated_token::mint = usdc_mint,
        associated_token::authority = vault,
    )]
    pub vault_usdc_ata: Box<Account<'info, TokenAccount>>,

    /// Recipient's USDC ATA. Must already exist (the upstream x402 facilitator
    /// always has one — for now we don't auto-create here to keep the spend
    /// instruction lean. Backend tx builder pre-flights this and adds an
    /// `init_if_needed` ix in the same tx if necessary.)
    #[account(
        mut,
        token::mint = usdc_mint,
    )]
    pub recipient_usdc_ata: Box<Account<'info, TokenAccount>>,

    pub token_program: Program<'info, Token>,
    pub associated_token_program: Program<'info, AssociatedToken>,
    pub system_program: Program<'info, System>,
}

pub fn handler(ctx: Context<Spend>, args: SpendArgs) -> Result<()> {
    let policy = &mut ctx.accounts.policy;
    let clock = Clock::get()?;

    // 1. Pause and expiry — fail-closed guards.
    require!(!policy.paused, VaultError::VaultPaused);
    require!(
        clock.unix_timestamp < policy.expires_at,
        VaultError::VaultExpired
    );

    // 2. Caps.
    require!(args.amount > 0, VaultError::PerCallCapExceeded);
    require!(
        args.amount <= policy.per_call_cap,
        VaultError::PerCallCapExceeded
    );

    // 3. Daily window. Reset the counter if we crossed into a new UTC day.
    let today = clock.unix_timestamp / 86_400;
    if policy.day_index != today {
        policy.day_index = today;
        policy.used_today = 0;
    }
    let new_used = policy
        .used_today
        .checked_add(args.amount)
        .ok_or(VaultError::DailyCapExceeded)?;
    require!(new_used <= policy.daily_cap, VaultError::DailyCapExceeded);

    // 4. Endpoint allowlist (linear scan, max 8 entries).
    let allowed = policy.endpoint_allowlist[..policy.allowlist_len as usize]
        .iter()
        .any(|h| h == &args.endpoint_hash);
    require!(allowed, VaultError::EndpointNotAllowed);

    // 5. Delegation authority must match the registered key.
    require!(
        ctx.accounts.delegation_authority.key() == policy.delegation_key,
        VaultError::DelegationKeyMismatch
    );

    // 6. Replay protection.
    require!(args.nonce > policy.last_nonce, VaultError::NonceReplay);

    // 7. PDA-signed SPL transfer. The vault PDA is the ATA authority, so we
    //    need to sign with its seeds.
    let owner_key = ctx.accounts.vault.owner;
    let agent_id = ctx.accounts.vault.agent_id;
    let vault_bump = ctx.accounts.vault.bump;
    let signer_seeds: &[&[&[u8]]] = &[&[SEED_VAULT, owner_key.as_ref(), &agent_id, &[vault_bump]]];

    token::transfer(
        CpiContext::new_with_signer(
            ctx.accounts.token_program.to_account_info(),
            Transfer {
                from: ctx.accounts.vault_usdc_ata.to_account_info(),
                to: ctx.accounts.recipient_usdc_ata.to_account_info(),
                authority: ctx.accounts.vault.to_account_info(),
            },
            signer_seeds,
        ),
        args.amount,
    )?;

    // 8. Commit policy state.
    policy.used_today = new_used;
    policy.last_nonce = args.nonce;

    emit!(SpendEvent {
        vault: ctx.accounts.vault.key(),
        amount: args.amount,
        recipient: ctx.accounts.recipient_usdc_ata.key(),
        endpoint_hash: args.endpoint_hash,
        nonce: args.nonce,
        ts: clock.unix_timestamp,
    });

    Ok(())
}

#[event]
pub struct SpendEvent {
    pub vault: Pubkey,
    pub amount: u64,
    pub recipient: Pubkey,
    pub endpoint_hash: [u8; 32],
    pub nonce: u64,
    pub ts: i64,
}
