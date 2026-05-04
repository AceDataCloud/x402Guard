<script setup lang="ts">
/**
 * Vault creation flow.
 *
 * 1. Validate user input (per_call ≤ daily, future expiry).
 * 2. POST to /api/v1/vaults/create — backend persists a pending row,
 *    returns the unsigned create_vault tx as base64.
 * 3. Phantom signs + sends. We confirm against a Solana RPC.
 * 4. POST tx signature to /api/v1/vaults/finalise.
 * 5. Navigate to the vault detail page.
 */
import { computed, reactive, ref } from "vue";
import { useRouter } from "vue-router";

import { getConnection } from "@/wallet/connection";
import { confirmSig, signAndSendBase64Tx, UserRejected, PhantomNotInstalled } from "@/wallet/phantom";
import { useVaultsStore } from "@/store/vaults";

const router = useRouter();
const vaults = useVaultsStore();

interface FormState {
  agentName: string;
  dailyCap: number;
  perCallCap: number;
  expiresInDays: number;
  allowlistRaw: string;
}

const form = reactive<FormState>({
  agentName: "Claude-Birthday-Helper",
  dailyCap: 2,
  perCallCap: 0.5,
  expiresInDays: 7,
  allowlistRaw: "api.acedata.cloud",
});

const submitting = ref(false);
const error = ref<string | null>(null);

const allowlist = computed(() =>
  form.allowlistRaw
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean)
);

const valid = computed(() => {
  if (!form.agentName.trim()) return false;
  if (form.dailyCap <= 0) return false;
  if (form.perCallCap <= 0) return false;
  if (form.perCallCap > form.dailyCap) return false;
  if (form.expiresInDays <= 0) return false;
  if (allowlist.value.length === 0 || allowlist.value.length > 8) return false;
  return true;
});

async function onSubmit() {
  if (!valid.value || submitting.value) return;
  submitting.value = true;
  error.value = null;
  try {
    const expiresAt = new Date(
      Date.now() + form.expiresInDays * 86_400 * 1000
    ).toISOString();

    const built = await vaults.buildCreateTx({
      agent_name: form.agentName.trim(),
      daily_cap_usdc: form.dailyCap,
      per_call_cap_usdc: form.perCallCap,
      endpoint_allowlist: allowlist.value,
      expires_at: expiresAt,
    });

    const conn = getConnection();
    const sig = await signAndSendBase64Tx(built.tx_b64, conn);
    await confirmSig(conn, sig);
    await vaults.finalise(built.pending_id, sig);
    await vaults.refresh();
    router.push({ name: "vault-detail", params: { id: built.pending_id } });
  } catch (e: unknown) {
    if (e instanceof UserRejected) {
      error.value = "You cancelled the Phantom signature.";
    } else if (e instanceof PhantomNotInstalled) {
      error.value = "Phantom wallet is not installed.";
    } else {
      error.value = (e as Error).message ?? String(e);
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <section class="container new-vault">
    <header class="page-head">
      <h2>New agent vault</h2>
      <p class="muted">
        Pick a daily cap, a per-call cap, and the API hosts your agent is
        allowed to spend on. Phantom signs an Anchor
        <code>create_vault</code> ix and your vault is born.
      </p>
    </header>

    <form @submit.prevent="onSubmit" class="card form-card">
      <label>
        <span>Agent name</span>
        <input v-model="form.agentName" placeholder="Claude-Birthday-Helper" data-testid="agent-name" />
        <small class="muted">
          Used as the seed for the vault's PDA — same name + same wallet
          always yields the same vault.
        </small>
      </label>

      <div class="grid">
        <label>
          <span>Daily cap (USDC)</span>
          <input
            v-model.number="form.dailyCap"
            type="number"
            min="0.001"
            step="0.001"
            data-testid="daily-cap"
          />
        </label>
        <label>
          <span>Per-call cap (USDC)</span>
          <input
            v-model.number="form.perCallCap"
            type="number"
            min="0.001"
            step="0.001"
            data-testid="per-call-cap"
          />
        </label>
        <label>
          <span>Expires in (days)</span>
          <input
            v-model.number="form.expiresInDays"
            type="number"
            min="1"
            max="365"
            data-testid="expires-in-days"
          />
        </label>
      </div>

      <label>
        <span>Endpoint allowlist</span>
        <textarea
          v-model="form.allowlistRaw"
          rows="3"
          placeholder="api.acedata.cloud&#10;api.openai.com"
          data-testid="allowlist"
        ></textarea>
        <small class="muted">
          One host per line (or comma-separated). Up to 8 entries. Stored on
          chain as <code>sha256(host)</code>.
        </small>
      </label>

      <p v-if="error" class="error-msg">{{ error }}</p>

      <div class="btn-row">
        <button :disabled="!valid || submitting" type="submit" data-testid="submit">
          {{ submitting ? "Signing in Phantom…" : "Create vault" }}
        </button>
        <router-link :to="{ name: 'vaults' }">
          <button type="button" class="secondary">Cancel</button>
        </router-link>
      </div>
    </form>
  </section>
</template>

<style scoped>
.new-vault {
  padding-top: 2rem;
  padding-bottom: 4rem;
  max-width: 720px;
}
.page-head h2 {
  margin: 0 0 0.25rem;
}
.page-head p {
  margin: 0 0 1.5rem;
  max-width: 64ch;
}
.form-card {
  display: grid;
  gap: 1.25rem;
}
label {
  display: grid;
  gap: 0.4rem;
}
label span {
  font-weight: 600;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 1rem;
}
@media (max-width: 600px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
textarea {
  font: inherit;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.55em 0.8em;
  width: 100%;
  resize: vertical;
}
.error-msg {
  color: var(--danger);
  margin: 0;
}
small {
  font-size: 0.85em;
}
code {
  background: var(--bg);
  padding: 0.1em 0.4em;
  border-radius: 4px;
}
</style>
