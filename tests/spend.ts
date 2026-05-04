/**
 * Anchor TypeScript tests for `spend`.
 *
 * Each `it` block creates a fresh vault to keep cases isolated; the happy
 * path also exercises the daily-counter rollover, the allowlist, the per-call
 * cap, and replay protection.
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

interface VaultFixture {
  vaultPda: PublicKey;
  policyPda: PublicKey;
  vaultAta: PublicKey;
  delegation: Keypair;
  agentId: Buffer;
}

describe("agent_vault: spend", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);
  const program = anchor.workspace.AgentVault as Program<AgentVault>;
  const owner = provider.wallet as anchor.Wallet;

  let usdcMint: PublicKey;
  let recipientAta: PublicKey;

  // Fund the delegation key with a few SOL so it can pay tx fees.
  async function fundLamports(pubkey: PublicKey, sol = 1) {
    const sig = await provider.connection.requestAirdrop(
      pubkey,
      sol * anchor.web3.LAMPORTS_PER_SOL
    );
    await provider.connection.confirmTransaction(sig, "confirmed");
  }

  async function makeVault(opts: {
    dailyCap: number;
    perCallCap: number;
    allowlist: string[];
    expiresInSec?: number;
    fundUsdc?: number;
  }): Promise<VaultFixture> {
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
        dailyCap: new anchor.BN(opts.dailyCap),
        perCallCap: new anchor.BN(opts.perCallCap),
        endpointAllowlist: opts.allowlist.map((host) =>
          Array.from(sha256(host))
        ),
        expiresAt: new anchor.BN(
          Math.floor(Date.now() / 1000) + (opts.expiresInSec ?? 7 * 24 * 3600)
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

  async function spend(
    fx: VaultFixture,
    amount: number,
    endpointHost: string,
    nonce: number,
    recipient: PublicKey = recipientAta
  ) {
    return program.methods
      .spend({
        amount: new anchor.BN(amount),
        endpointHash: Array.from(sha256(endpointHost)),
        nonce: new anchor.BN(nonce),
      })
      .accounts({
        delegationAuthority: fx.delegation.publicKey,
        vault: fx.vaultPda,
        policy: fx.policyPda,
        usdcMint,
        vaultUsdcAta: fx.vaultAta,
        recipientUsdcAta: recipient,
        tokenProgram: TOKEN_PROGRAM_ID,
        associatedTokenProgram: ASSOCIATED_TOKEN_PROGRAM_ID,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .signers([fx.delegation])
      .rpc();
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
  });

  it("happy path: transfers USDC, updates used_today + last_nonce, emits event", async () => {
    const fx = await makeVault({
      dailyCap: 2_000_000,
      perCallCap: 500_000,
      allowlist: ["api.acedata.cloud"],
      fundUsdc: 5_000_000,
    });

    await spend(fx, 250_000, "api.acedata.cloud", 1);

    const policy = await program.account.policy.fetch(fx.policyPda);
    assert.equal(policy.usedToday.toString(), "250000");
    assert.equal(policy.lastNonce.toString(), "1");

    const vaultAtaState = await getAccount(provider.connection, fx.vaultAta);
    assert.equal(vaultAtaState.amount.toString(), "4750000");
    const recipientState = await getAccount(provider.connection, recipientAta);
    assert.ok(Number(recipientState.amount) >= 250_000);
  });

  it("rejects amount over per_call_cap", async () => {
    const fx = await makeVault({
      dailyCap: 2_000_000,
      perCallCap: 500_000,
      allowlist: ["api.acedata.cloud"],
      fundUsdc: 5_000_000,
    });
    try {
      await spend(fx, 1_000_000, "api.acedata.cloud", 1);
      assert.fail("expected PerCallCapExceeded");
    } catch (err: any) {
      assert.match(String(err), /PerCallCapExceeded/);
    }
  });

  it("rejects when running spend would cross daily_cap", async () => {
    const fx = await makeVault({
      dailyCap: 600_000,
      perCallCap: 500_000,
      allowlist: ["api.acedata.cloud"],
      fundUsdc: 5_000_000,
    });
    await spend(fx, 500_000, "api.acedata.cloud", 1);
    try {
      await spend(fx, 200_000, "api.acedata.cloud", 2);
      assert.fail("expected DailyCapExceeded");
    } catch (err: any) {
      assert.match(String(err), /DailyCapExceeded/);
    }
  });

  it("rejects endpoint not on the allowlist", async () => {
    const fx = await makeVault({
      dailyCap: 2_000_000,
      perCallCap: 500_000,
      allowlist: ["api.acedata.cloud"],
      fundUsdc: 5_000_000,
    });
    try {
      await spend(fx, 100_000, "evil-api.com", 1);
      assert.fail("expected EndpointNotAllowed");
    } catch (err: any) {
      assert.match(String(err), /EndpointNotAllowed/);
    }
  });

  it("rejects spend signed by an unrelated key", async () => {
    const fx = await makeVault({
      dailyCap: 2_000_000,
      perCallCap: 500_000,
      allowlist: ["api.acedata.cloud"],
      fundUsdc: 5_000_000,
    });
    const imposter = Keypair.generate();
    await fundLamports(imposter.publicKey, 1);

    try {
      await program.methods
        .spend({
          amount: new anchor.BN(100_000),
          endpointHash: Array.from(sha256("api.acedata.cloud")),
          nonce: new anchor.BN(1),
        })
        .accounts({
          delegationAuthority: imposter.publicKey,
          vault: fx.vaultPda,
          policy: fx.policyPda,
          usdcMint,
          vaultUsdcAta: fx.vaultAta,
          recipientUsdcAta: recipientAta,
          tokenProgram: TOKEN_PROGRAM_ID,
          associatedTokenProgram: ASSOCIATED_TOKEN_PROGRAM_ID,
          systemProgram: anchor.web3.SystemProgram.programId,
        })
        .signers([imposter])
        .rpc();
      assert.fail("expected DelegationKeyMismatch");
    } catch (err: any) {
      assert.match(String(err), /DelegationKeyMismatch/);
    }
  });

  it("rejects nonce replay", async () => {
    const fx = await makeVault({
      dailyCap: 2_000_000,
      perCallCap: 500_000,
      allowlist: ["api.acedata.cloud"],
      fundUsdc: 5_000_000,
    });
    await spend(fx, 100_000, "api.acedata.cloud", 5);
    try {
      await spend(fx, 100_000, "api.acedata.cloud", 5);
      assert.fail("expected NonceReplay");
    } catch (err: any) {
      assert.match(String(err), /NonceReplay/);
    }
    // Strictly-greater also rejects equal-or-less.
    try {
      await spend(fx, 100_000, "api.acedata.cloud", 4);
      assert.fail("expected NonceReplay");
    } catch (err: any) {
      assert.match(String(err), /NonceReplay/);
    }
  });
});
