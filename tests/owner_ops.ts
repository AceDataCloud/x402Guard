/**
 * Anchor TypeScript tests for the owner-only ops:
 *   pause / resume / update_policy / clawback
 *
 * Each `it` builds a fresh vault using the same makeVault helper used in
 * tests/spend.ts so cases stay isolated.
 */

import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import {
  TOKEN_PROGRAM_ID,
  ASSOCIATED_TOKEN_PROGRAM_ID,
  createMint,
  createAssociatedTokenAccount,
  getAssociatedTokenAddress,
  mintTo,
  getAccount,
} from "@solana/spl-token";
import { PublicKey, Keypair } from "@solana/web3.js";
import { createHash, randomBytes } from "crypto";
import { assert } from "chai";

import { AgentVault } from "../target/types/agent_vault";

const SEED_VAULT = Buffer.from("vault");
const SEED_POLICY = Buffer.from("policy");

function sha256(s: string): Buffer {
  return createHash("sha256").update(s).digest();
}

describe("agent_vault: owner ops", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);
  const program = anchor.workspace.AgentVault as Program<AgentVault>;
  const owner = provider.wallet as anchor.Wallet;

  let usdcMint: PublicKey;
  let recipientAta: PublicKey;
  let ownerUsdcAta: PublicKey;

  async function fundLamports(pubkey: PublicKey, sol = 1) {
    const sig = await provider.connection.requestAirdrop(
      pubkey,
      sol * anchor.web3.LAMPORTS_PER_SOL
    );
    await provider.connection.confirmTransaction(sig, "confirmed");
  }

  async function makeVault(opts: {
    dailyCap?: number;
    perCallCap?: number;
    allowlist?: string[];
    fundUsdc?: number;
  } = {}) {
    const delegation = Keypair.generate();
    await fundLamports(delegation.publicKey, 1);
    const agentId = randomBytes(32);
    const [vaultPda] = PublicKey.findProgramAddressSync(
      [SEED_VAULT, owner.publicKey.toBuffer(), agentId],
      program.programId
    );
    const [policyPda] = PublicKey.findProgramAddressSync(
      [SEED_POLICY, vaultPda.toBuffer()],
      program.programId
    );
    const vaultAta = await getAssociatedTokenAddress(usdcMint, vaultPda, true);

    await program.methods
      .createVault({
        agentId: Array.from(agentId),
        delegationKey: delegation.publicKey,
        dailyCap: new anchor.BN(opts.dailyCap ?? 2_000_000),
        perCallCap: new anchor.BN(opts.perCallCap ?? 500_000),
        endpointAllowlist: (opts.allowlist ?? ["api.acedata.cloud"]).map(
          (h) => Array.from(sha256(h))
        ),
        expiresAt: new anchor.BN(
          Math.floor(Date.now() / 1000) + 7 * 24 * 3600
        ),
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

    if (opts.fundUsdc) {
      await mintTo(
        provider.connection,
        owner.payer,
        usdcMint,
        vaultAta,
        owner.publicKey,
        opts.fundUsdc
      );
    }

    return { vaultPda, policyPda, vaultAta, delegation, agentId };
  }

  before(async () => {
    usdcMint = await createMint(
      provider.connection,
      owner.payer,
      owner.publicKey,
      null,
      6
    );
    recipientAta = await createAssociatedTokenAccount(
      provider.connection,
      owner.payer,
      usdcMint,
      Keypair.generate().publicKey
    );
    ownerUsdcAta = await createAssociatedTokenAccount(
      provider.connection,
      owner.payer,
      usdcMint,
      owner.publicKey
    );
  });

  describe("pause / resume", () => {
    it("pauses the vault and blocks subsequent spends", async () => {
      const fx = await makeVault({ fundUsdc: 5_000_000 });
      await program.methods
        .pause()
        .accounts({
          owner: owner.publicKey,
          vault: fx.vaultPda,
          policy: fx.policyPda,
        })
        .rpc();
      const policy = await program.account.policy.fetch(fx.policyPda);
      assert.equal(policy.paused, true);

      // Attempting a spend now should fail with VaultPaused.
      try {
        await program.methods
          .spend({
            amount: new anchor.BN(100_000),
            endpointHash: Array.from(sha256("api.acedata.cloud")),
            nonce: new anchor.BN(1),
          })
          .accounts({
            delegationAuthority: fx.delegation.publicKey,
            vault: fx.vaultPda,
            policy: fx.policyPda,
            usdcMint,
            vaultUsdcAta: fx.vaultAta,
            recipientUsdcAta: recipientAta,
            tokenProgram: TOKEN_PROGRAM_ID,
            associatedTokenProgram: ASSOCIATED_TOKEN_PROGRAM_ID,
            systemProgram: anchor.web3.SystemProgram.programId,
          })
          .signers([fx.delegation])
          .rpc();
        assert.fail("expected VaultPaused");
      } catch (err: any) {
        assert.match(String(err), /VaultPaused/);
      }
    });

    it("resume re-enables spending", async () => {
      const fx = await makeVault({ fundUsdc: 5_000_000 });
      await program.methods
        .pause()
        .accounts({
          owner: owner.publicKey,
          vault: fx.vaultPda,
          policy: fx.policyPda,
        })
        .rpc();
      await program.methods
        .resume()
        .accounts({
          owner: owner.publicKey,
          vault: fx.vaultPda,
          policy: fx.policyPda,
        })
        .rpc();
      const policy = await program.account.policy.fetch(fx.policyPda);
      assert.equal(policy.paused, false);
    });

    it("rejects pause from a non-owner signer", async () => {
      const fx = await makeVault();
      const imposter = Keypair.generate();
      await fundLamports(imposter.publicKey, 1);
      try {
        await program.methods
          .pause()
          .accounts({
            owner: imposter.publicKey,
            vault: fx.vaultPda,
            policy: fx.policyPda,
          })
          .signers([imposter])
          .rpc();
        assert.fail("expected has_one constraint failure");
      } catch (err: any) {
        // Anchor surfaces this as a constraint violation; depending on Anchor
        // version the message contains "ConstraintHasOne" or "has_one".
        assert.match(String(err), /HasOne|has_one|2001|ConstraintSeeds/);
      }
    });
  });

  describe("update_policy", () => {
    it("partial update only changes provided fields", async () => {
      const fx = await makeVault({
        dailyCap: 2_000_000,
        perCallCap: 500_000,
      });
      await program.methods
        .updatePolicy({
          delegationKey: null,
          dailyCap: new anchor.BN(4_000_000),
          perCallCap: null,
          endpointAllowlist: null,
          expiresAt: null,
        })
        .accounts({
          owner: owner.publicKey,
          vault: fx.vaultPda,
          policy: fx.policyPda,
        })
        .rpc();
      const policy = await program.account.policy.fetch(fx.policyPda);
      assert.equal(policy.dailyCap.toString(), "4000000");
      assert.equal(policy.perCallCap.toString(), "500000");
    });

    it("rejects update that would push per_call > daily", async () => {
      const fx = await makeVault({
        dailyCap: 2_000_000,
        perCallCap: 500_000,
      });
      try {
        await program.methods
          .updatePolicy({
            delegationKey: null,
            dailyCap: null,
            perCallCap: new anchor.BN(3_000_000),
            endpointAllowlist: null,
            expiresAt: null,
          })
          .accounts({
            owner: owner.publicKey,
            vault: fx.vaultPda,
            policy: fx.policyPda,
          })
          .rpc();
        assert.fail("expected PerCallExceedsDaily");
      } catch (err: any) {
        assert.match(String(err), /PerCallExceedsDaily/);
      }
    });

    it("rejects expires_at in the past", async () => {
      const fx = await makeVault();
      try {
        await program.methods
          .updatePolicy({
            delegationKey: null,
            dailyCap: null,
            perCallCap: null,
            endpointAllowlist: null,
            expiresAt: new anchor.BN(Math.floor(Date.now() / 1000) - 60),
          })
          .accounts({
            owner: owner.publicKey,
            vault: fx.vaultPda,
            policy: fx.policyPda,
          })
          .rpc();
        assert.fail("expected ExpirationInPast");
      } catch (err: any) {
        assert.match(String(err), /ExpirationInPast/);
      }
    });

    it("replaces the endpoint allowlist atomically", async () => {
      const fx = await makeVault({
        allowlist: ["api.acedata.cloud", "facilitator.acedata.cloud"],
      });
      await program.methods
        .updatePolicy({
          delegationKey: null,
          dailyCap: null,
          perCallCap: null,
          endpointAllowlist: [
            Array.from(sha256("new.endpoint")),
          ],
          expiresAt: null,
        })
        .accounts({
          owner: owner.publicKey,
          vault: fx.vaultPda,
          policy: fx.policyPda,
        })
        .rpc();
      const policy = await program.account.policy.fetch(fx.policyPda);
      assert.equal(policy.allowlistLen, 1);
      assert.deepEqual(
        Array.from(policy.endpointAllowlist[0]),
        Array.from(sha256("new.endpoint"))
      );
    });
  });

  describe("clawback", () => {
    it("sweeps the full vault balance to the owner and pauses atomically", async () => {
      const fx = await makeVault({ fundUsdc: 3_500_000 });

      const ownerBefore = (await getAccount(provider.connection, ownerUsdcAta))
        .amount;

      await program.methods
        .clawback()
        .accounts({
          owner: owner.publicKey,
          vault: fx.vaultPda,
          policy: fx.policyPda,
          usdcMint,
          vaultUsdcAta: fx.vaultAta,
          ownerUsdcAta,
          tokenProgram: TOKEN_PROGRAM_ID,
        })
        .rpc();

      const vaultAfter = await getAccount(provider.connection, fx.vaultAta);
      assert.equal(vaultAfter.amount.toString(), "0");

      const ownerAfter = (await getAccount(provider.connection, ownerUsdcAta))
        .amount;
      assert.equal(
        (ownerAfter - ownerBefore).toString(),
        "3500000"
      );

      const policy = await program.account.policy.fetch(fx.policyPda);
      assert.equal(policy.paused, true);
    });

    it("0-balance clawback still pauses the vault", async () => {
      const fx = await makeVault();

      await program.methods
        .clawback()
        .accounts({
          owner: owner.publicKey,
          vault: fx.vaultPda,
          policy: fx.policyPda,
          usdcMint,
          vaultUsdcAta: fx.vaultAta,
          ownerUsdcAta,
          tokenProgram: TOKEN_PROGRAM_ID,
        })
        .rpc();

      const policy = await program.account.policy.fetch(fx.policyPda);
      assert.equal(policy.paused, true);
    });
  });
});
