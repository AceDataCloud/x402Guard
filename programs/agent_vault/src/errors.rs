//! Custom error codes. Each variant maps directly to a UI toast / MCP error message
//! so the same identifier travels from on-chain → backend logs → user surface.

use anchor_lang::prelude::*;

#[error_code]
pub enum VaultError {
    #[msg("Per-call cap must not exceed the daily cap")]
    PerCallExceedsDaily,

    #[msg("Vault expiration must be in the future")]
    ExpirationInPast,

    #[msg("Endpoint allowlist exceeds the maximum size")]
    AllowlistTooLong,

    #[msg("Vault is paused — owner must resume before further spends")]
    VaultPaused,

    #[msg("Vault has expired — owner must update the policy or clawback the balance")]
    VaultExpired,

    #[msg("Spend exceeds the per-call cap")]
    PerCallCapExceeded,

    #[msg("Spend would exceed the remaining daily cap")]
    DailyCapExceeded,

    #[msg("Endpoint hash is not on the policy allowlist")]
    EndpointNotAllowed,

    #[msg("Spend was not signed by the delegation key registered in the policy")]
    DelegationKeyMismatch,

    #[msg("Nonce must be strictly greater than the last accepted nonce")]
    NonceReplay,
}
