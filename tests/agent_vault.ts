/**
 * Anchor TypeScript test for `create_vault`.
 *
 * Runs against a local validator that `anchor test` spins up automatically.
 * The validator clones the SPL Token + Associated Token program from devnet
 * (configured in `Anchor.toml`) so we get real SPL semantics for free.
 *
 * Subsequent PRs will add tests for `spend`, `pause`, `clawback`,
 * `update_policy`, and the full lifecycle.
 */

import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import {
  TOKEN_PROGRAM_ID,
  ASSOCIATED_TOKEN_PROGRAM_ID,
  createMint,
  getAssociatedTokenAddress,
} from "@solana/spl-token";
import { PublicKey, Keypair } from "@solana/web3.js";
import { createHash } from "crypto";
import { assert } from "chai";

import { AgentVault } from "../target/types/agent_vault";

const SEED_VAULT = Buffer.from("vault");
const SEED_POLICY = Buffer.from("policy");

function sha256(s: string): Buffer {
  return createHash("sha256").update(s).digest();
}

describe("agent_vault: create_vault", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);
  const program = anchor.workspace.AgentVault as Program<AgentVault>;
  const owner = provider.wallet as anchor.Wallet;

  let usdcMint: PublicKey;
  const delegation = Keypair.generate();
  const agentId = sha256("Claude-Birthday-Helper");

  before(async () => {
    // Mint a test USDC (6 decimals, like real USDC) on the local validator.
    usdcMint = await createMint(
      provider.connection,
      owner.payer,
      owner.publicKey,
      null,
      6
    );
  });

  it("creates a vault and policy with the requested parameters", async () => {
    const [vaultPda] = PublicKey.findProgramAddressSync(
      [SEED_VAULT, owner.publicKey.toBuffer(), agentId],
      program.programId
    );
    const [policyPda] = PublicKey.findProgramAddressSync(
      [SEED_POLICY, vaultPda.toBuffer()],
      program.programId
    );
    const vaultAta = await getAssociatedTokenAddress(usdcMint, vaultPda, true);

    const expiresAt = Math.floor(Date.now() / 1000) + 7 * 24 * 3600;
    const args = {
      agentId: Array.from(agentId),
      delegationKey: delegation.publicKey,
      // 2 USDC daily, 0.5 USDC per call.
      dailyCap: new anchor.BN(2_000_000),
      perCallCap: new anchor.BN(500_000),
      endpointAllowlist: [Array.from(sha256("api.acedata.cloud"))],
      expiresAt: new anchor.BN(expiresAt),
    };

    await program.methods
      .createVault(args)
      .accounts({
        owner: owner.publicKey,
        vault: vaultPda,
        policy: policyPda,
        usdcMint,
        vaultUsdcAta: vaultAta,
        systemProgram: anchor.web3.SystemProgram.programId,
        tokenProgram: TOKEN_PROGRAM_ID,
        associatedTokenProgram: ASSOCIATED_TOKEN_PROGRAM_ID,
        rent: anchor.web3.SYSVAR_RENT_PUBKEY,
      })
      .rpc();

    const vault = await program.account.vault.fetch(vaultPda);
    assert.ok(vault.owner.equals(owner.publicKey));
    assert.deepEqual(Array.from(vault.agentId), Array.from(agentId));
    assert.ok(vault.usdcMint.equals(usdcMint));

    const policy = await program.account.policy.fetch(policyPda);
    assert.ok(policy.vault.equals(vaultPda));
    assert.ok(policy.delegationKey.equals(delegation.publicKey));
    assert.equal(policy.dailyCap.toString(), "2000000");
    assert.equal(policy.perCallCap.toString(), "500000");
    assert.equal(policy.allowlistLen, 1);
    assert.equal(policy.paused, false);
    assert.equal(policy.usedToday.toString(), "0");
    assert.equal(policy.lastNonce.toString(), "0");
  });

  it("rejects per_call_cap > daily_cap", async () => {
    const altAgentId = sha256("rejection-test-1");
    const [vaultPda] = PublicKey.findProgramAddressSync(
      [SEED_VAULT, owner.publicKey.toBuffer(), altAgentId],
      program.programId
    );
    const [policyPda] = PublicKey.findProgramAddressSync(
      [SEED_POLICY, vaultPda.toBuffer()],
      program.programId
    );
    const vaultAta = await getAssociatedTokenAddress(usdcMint, vaultPda, true);

    try {
      await program.methods
        .createVault({
          agentId: Array.from(altAgentId),
          delegationKey: delegation.publicKey,
          dailyCap: new anchor.BN(1_000_000),
          perCallCap: new anchor.BN(2_000_000),
          endpointAllowlist: [],
          expiresAt: new anchor.BN(Math.floor(Date.now() / 1000) + 3600),
        })
        .accounts({
          owner: owner.publicKey,
          vault: vaultPda,
          policy: policyPda,
          usdcMint,
          vaultUsdcAta: vaultAta,
          systemProgram: anchor.web3.SystemProgram.programId,
          tokenProgram: TOKEN_PROGRAM_ID,
          associatedTokenProgram: ASSOCIATED_TOKEN_PROGRAM_ID,
          rent: anchor.web3.SYSVAR_RENT_PUBKEY,
        })
        .rpc();
      assert.fail("expected PerCallExceedsDaily");
    } catch (err: any) {
      assert.match(String(err), /PerCallExceedsDaily/);
    }
  });

  it("rejects expires_at in the past", async () => {
    const altAgentId = sha256("rejection-test-2");
    const [vaultPda] = PublicKey.findProgramAddressSync(
      [SEED_VAULT, owner.publicKey.toBuffer(), altAgentId],
      program.programId
    );
    const [policyPda] = PublicKey.findProgramAddressSync(
      [SEED_POLICY, vaultPda.toBuffer()],
      program.programId
    );
    const vaultAta = await getAssociatedTokenAddress(usdcMint, vaultPda, true);

    try {
      await program.methods
        .createVault({
          agentId: Array.from(altAgentId),
          delegationKey: delegation.publicKey,
          dailyCap: new anchor.BN(1_000_000),
          perCallCap: new anchor.BN(500_000),
          endpointAllowlist: [],
          expiresAt: new anchor.BN(Math.floor(Date.now() / 1000) - 3600),
        })
        .accounts({
          owner: owner.publicKey,
          vault: vaultPda,
          policy: policyPda,
          usdcMint,
          vaultUsdcAta: vaultAta,
          systemProgram: anchor.web3.SystemProgram.programId,
          tokenProgram: TOKEN_PROGRAM_ID,
          associatedTokenProgram: ASSOCIATED_TOKEN_PROGRAM_ID,
          rent: anchor.web3.SYSVAR_RENT_PUBKEY,
        })
        .rpc();
      assert.fail("expected ExpirationInPast");
    } catch (err: any) {
      assert.match(String(err), /ExpirationInPast/);
    }
  });
});
