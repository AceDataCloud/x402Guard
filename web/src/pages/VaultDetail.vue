<script setup lang="ts">
/**
 * Vault detail page.
 *
 *  - Shows policy snapshot + Solscan links
 *  - Top up: SPL transfer USDC into the vault's ATA via Phantom
 *  - Owner ops: pause / resume / clawback (each builds a backend tx,
 *    Phantom signs, we finalise the local cache via /mark-paused)
 *  - MCP sessions: list / create / revoke
 */
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  PublicKey,
  Transaction,
  ComputeBudgetProgram,
} from "@solana/web3.js";
import {
  createAssociatedTokenAccountIdempotentInstruction,
  createTransferCheckedInstruction,
  getAssociatedTokenAddressSync,
  TOKEN_PROGRAM_ID,
} from "@solana/spl-token";

import { getConnection } from "@/wallet/connection";
import {
  confirmSig,
  signAndSendBase64Tx,
  PhantomNotInstalled,
  UserRejected,
  getProvider,
} from "@/wallet/phantom";
import { useAuthStore } from "@/store/auth";
import { useVaultsStore, type MCPSessionRow, type VaultRow } from "@/store/vaults";
import { apiClient } from "@/api/client";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const vaults = useVaultsStore();

const vaultId = computed(() => String(route.params.id));
const vault = computed<VaultRow | undefined>(() =>
  vaults.vaults.find((v) => v.id === vaultId.value)
);

const wellKnown = ref<{ usdc_mint: string; cluster: string } | null>(null);

const sessions = ref<MCPSessionRow[]>([]);
const newSessionLabel = ref("");
const topUpAmount = ref(1);

const error = ref<string | null>(null);
const busy = ref<string | null>(null);
const lastTx = ref<string | null>(null);

const solscanBase = computed(() =>
  wellKnown.value?.cluster === "devnet"
    ? "https://solscan.io"
    : "https://solscan.io"
);

const solscanCluster = computed(() =>
  wellKnown.value?.cluster === "devnet" ? "?cluster=devnet" : ""
);

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  return new Date(s).toLocaleString();
}

function copy(text: string) {
  navigator.clipboard.writeText(text);
}

async function loadAll() {
  if (!auth.isAuthenticated) {
    router.push({ name: "home", query: { next: route.fullPath } });
    return;
  }
  if (!vaults.vaults.length) await vaults.refresh();
  if (!wellKnown.value) {
    wellKnown.value = (
      await apiClient.get<{ usdc_mint: string; cluster: string }>("/.well-known/x402guard")
    ).data;
  }
  if (vault.value) {
    sessions.value = await vaults.listMcpSessions(vault.value.id);
  }
}

async function ownerAction(action: "pause" | "resume" | "clawback") {
  if (!vault.value) return;
  busy.value = action;
  error.value = null;
  try {
    const built = await vaults.buildOwnerActionTx(vault.value.id, action);
    const sig = await signAndSendBase64Tx(built.tx_b64, getConnection());
    await confirmSig(getConnection(), sig);
    lastTx.value = sig;

    // Reflect new pause state locally without a fresh refresh.
    if (action === "pause" || action === "clawback") {
      await vaults.markPaused(vault.value.id, true);
    } else if (action === "resume") {
      await vaults.markPaused(vault.value.id, false);
    }
    await vaults.refresh();
  } catch (e: unknown) {
    if (e instanceof UserRejected) error.value = "Cancelled in Phantom.";
    else if (e instanceof PhantomNotInstalled)
      error.value = "Phantom is not installed.";
    else error.value = (e as Error).message;
  } finally {
    busy.value = null;
  }
}

async function topUp() {
  if (!vault.value || !wellKnown.value) return;
  if (topUpAmount.value <= 0) {
    error.value = "Amount must be > 0";
    return;
  }
  busy.value = "topup";
  error.value = null;
  try {
    const conn = getConnection();
    const provider = getProvider();
    const owner = new PublicKey(vault.value.owner_pubkey);
    const mint = new PublicKey(wellKnown.value.usdc_mint);
    const vaultPda = new PublicKey(vault.value.vault_pda);

    const ownerAta = getAssociatedTokenAddressSync(mint, owner);
    const vaultAta = getAssociatedTokenAddressSync(mint, vaultPda, true);

    const tx = new Transaction();
    tx.add(ComputeBudgetProgram.setComputeUnitLimit({ units: 60_000 }));
    // Idempotent — no-op if the vault ATA already exists, which it
    // does after create_vault landed on chain.
    tx.add(
      createAssociatedTokenAccountIdempotentInstruction(
        owner,
        vaultAta,
        vaultPda,
        mint
      )
    );
    tx.add(
      createTransferCheckedInstruction(
        ownerAta,
        mint,
        vaultAta,
        owner,
        Math.round(topUpAmount.value * 1_000_000),
        6,
        [],
        TOKEN_PROGRAM_ID
      )
    );

    const { blockhash, lastValidBlockHeight } = await conn.getLatestBlockhash();
    tx.recentBlockhash = blockhash;
    tx.lastValidBlockHeight = lastValidBlockHeight;
    tx.feePayer = owner;

    const result = await provider.signAndSendTransaction(tx);
    await confirmSig(conn, result.signature);
    lastTx.value = result.signature;
  } catch (e: unknown) {
    if (e instanceof UserRejected) error.value = "Cancelled in Phantom.";
    else if (e instanceof PhantomNotInstalled)
      error.value = "Phantom is not installed.";
    else error.value = (e as Error).message;
  } finally {
    busy.value = null;
  }
}

async function newSession() {
  if (!vault.value) return;
  busy.value = "session-create";
  error.value = null;
  try {
    const created = await vaults.createMcpSession(
      vault.value.id,
      newSessionLabel.value || undefined
    );
    sessions.value = [created, ...sessions.value];
    newSessionLabel.value = "";
  } catch (e: unknown) {
    error.value = (e as Error).message;
  } finally {
    busy.value = null;
  }
}

async function revokeSession(token: string) {
  if (!vault.value) return;
  busy.value = `revoke-${token}`;
  try {
    await vaults.revokeMcpSession(vault.value.id, token);
    sessions.value = sessions.value.filter((s) => s.token !== token);
  } catch (e: unknown) {
    error.value = (e as Error).message;
  } finally {
    busy.value = null;
  }
}

onMounted(loadAll);
</script>

<template>
  <section class="container vault-detail">
    <p>
      <router-link :to="{ name: 'vaults' }">← Back to vaults</router-link>
    </p>

    <div v-if="!vault" class="card empty muted">Vault not found.</div>

    <template v-else>
      <header class="page-head">
        <div>
          <h2>{{ vault.agent_name }}</h2>
          <p class="muted">
            <span :class="['status', { paused: vault.paused }]">
              {{ vault.paused ? "Paused" : "Active" }}
            </span>
            · created {{ fmtDate(vault.created_at) }}
          </p>
        </div>
        <div class="btn-row">
          <button
            class="secondary"
            :disabled="!!busy"
            @click="vault.paused ? ownerAction('resume') : ownerAction('pause')"
            :data-testid="vault.paused ? 'resume' : 'pause'"
          >
            {{ vault.paused ? "Resume" : "Pause" }}
          </button>
          <button
            class="danger"
            :disabled="!!busy"
            @click="ownerAction('clawback')"
            data-testid="clawback"
          >
            Clawback
          </button>
        </div>
      </header>

      <p v-if="error" class="error-msg">{{ error }}</p>
      <p v-if="lastTx" class="muted last-tx">
        Last tx:
        <a
          :href="`${solscanBase}/tx/${lastTx}${solscanCluster}`"
          target="_blank"
          rel="noreferrer"
        >{{ lastTx.slice(0, 8) }}…{{ lastTx.slice(-8) }}</a>
      </p>

      <div class="grid-2">
        <article class="card">
          <h3>Policy</h3>
          <dl class="kv">
            <div><dt>Daily cap</dt><dd>{{ vault.daily_cap_usdc }} USDC</dd></div>
            <div><dt>Per-call cap</dt><dd>{{ vault.per_call_cap_usdc }} USDC</dd></div>
            <div>
              <dt>Allowlist</dt>
              <dd>
                <code v-for="h in vault.endpoint_allowlist" :key="h">{{ h }}</code>
              </dd>
            </div>
            <div><dt>Expires</dt><dd>{{ fmtDate(vault.expires_at) }}</dd></div>
            <div>
              <dt>Vault PDA</dt>
              <dd>
                <a
                  :href="`${solscanBase}/account/${vault.vault_pda}${solscanCluster}`"
                  target="_blank"
                  rel="noreferrer"
                  >{{ vault.vault_pda.slice(0, 6) }}…{{ vault.vault_pda.slice(-6) }}</a
                >
              </dd>
            </div>
            <div v-if="vault.create_tx">
              <dt>Create tx</dt>
              <dd>
                <a
                  :href="`${solscanBase}/tx/${vault.create_tx}${solscanCluster}`"
                  target="_blank"
                  rel="noreferrer"
                  >{{ vault.create_tx.slice(0, 6) }}…{{ vault.create_tx.slice(-6) }}</a
                >
              </dd>
            </div>
          </dl>
        </article>

        <article class="card">
          <h3>Top up</h3>
          <p class="muted">
            Send USDC from your Phantom wallet to the vault's associated token
            account.
          </p>
          <div class="topup-row">
            <input
              v-model.number="topUpAmount"
              type="number"
              min="0.001"
              step="0.001"
              data-testid="topup-amount"
            />
            <button
              :disabled="busy === 'topup'"
              @click="topUp"
              data-testid="topup-submit"
            >
              {{ busy === "topup" ? "Sending…" : "Send USDC" }}
            </button>
          </div>
        </article>
      </div>

      <article class="card">
        <header class="card-head">
          <h3>MCP sessions</h3>
          <span class="muted">
            Paste the URL into Claude Desktop / Cursor / any MCP client.
          </span>
        </header>

        <div class="session-create">
          <input
            v-model="newSessionLabel"
            placeholder="Optional label (e.g. 'claude-desktop')"
            data-testid="session-label"
          />
          <button
            :disabled="busy === 'session-create'"
            @click="newSession"
            data-testid="session-create"
          >
            {{ busy === "session-create" ? "Creating…" : "+ New MCP URL" }}
          </button>
        </div>

        <ul v-if="sessions.length" class="session-list">
          <li v-for="s in sessions" :key="s.token" class="session-item">
            <div>
              <strong>{{ s.label ?? "(unlabelled)" }}</strong>
              <p class="muted mcp-url">{{ s.mcp_url }}</p>
            </div>
            <div class="btn-row">
              <button class="secondary" @click="copy(s.mcp_url)">Copy</button>
              <button
                class="danger"
                :disabled="busy === `revoke-${s.token}`"
                @click="revokeSession(s.token)"
              >
                {{ busy === `revoke-${s.token}` ? "Revoking…" : "Revoke" }}
              </button>
            </div>
          </li>
        </ul>
        <p v-else class="muted">No sessions yet — create one to get an MCP URL.</p>
      </article>
    </template>
  </section>
</template>

<style scoped>
.vault-detail {
  padding-top: 2rem;
  padding-bottom: 4rem;
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1.5rem;
}
.page-head h2 {
  margin: 0 0 0.25rem;
}
.page-head p {
  margin: 0;
}
.status {
  font-size: 0.8rem;
  padding: 0.2em 0.6em;
  border-radius: 999px;
  background: rgba(20, 241, 149, 0.18);
  color: var(--solana-green);
  font-weight: 600;
}
.status.paused {
  background: rgba(255, 92, 117, 0.18);
  color: var(--danger);
}
.error-msg {
  color: var(--danger);
}
.last-tx {
  margin: 0 0 1rem;
}
.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1rem;
}
@media (max-width: 800px) {
  .grid-2 {
    grid-template-columns: 1fr;
  }
}
.kv {
  display: grid;
  gap: 0.5rem;
  margin: 0;
}
.kv > div {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
}
.kv dt {
  color: var(--text-muted);
}
.kv dd {
  margin: 0;
  text-align: right;
  font-variant-numeric: tabular-nums;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  align-items: end;
}
.kv dd code {
  background: var(--bg);
  padding: 0.1em 0.4em;
  border-radius: 4px;
  font-size: 0.85em;
}
.topup-row {
  display: flex;
  gap: 0.5rem;
}
.topup-row input {
  flex: 1;
}
.card-head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
  align-items: center;
}
.card-head h3 {
  margin: 0;
}
.session-create {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
}
.session-create input {
  flex: 1;
}
.session-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 0.6rem;
}
.session-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  border: 1px solid var(--border);
  padding: 0.8rem 1rem;
  border-radius: 8px;
}
.mcp-url {
  margin: 0.2rem 0 0;
  font-family: ui-monospace, monospace;
  font-size: 0.85rem;
  word-break: break-all;
}
</style>
