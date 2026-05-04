<script setup lang="ts">
import { onMounted } from "vue";

import { useAuthStore } from "@/store/auth";
import { useVaultsStore } from "@/store/vaults";

const auth = useAuthStore();
const vaults = useVaultsStore();

onMounted(async () => {
  if (auth.isAuthenticated) {
    await vaults.refresh();
  }
});

function fmtDate(s: string): string {
  return new Date(s).toLocaleString();
}
</script>

<template>
  <section class="container vaults-page">
    <header class="page-head">
      <div>
        <h2>My agent vaults</h2>
        <p class="muted">
          Each vault is a Solana PDA holding USDC. The on-chain
          <code>agent_vault</code> program enforces every spend.
        </p>
      </div>
      <router-link :to="{ name: 'vault-new' }">
        <button data-testid="new-vault">+ New vault</button>
      </router-link>
    </header>

    <div v-if="!auth.isAuthenticated" class="card empty">
      <p>Connect Phantom to see your vaults.</p>
    </div>

    <div v-else-if="vaults.loading" class="card empty muted">Loading…</div>

    <div v-else-if="vaults.lastError" class="card empty">
      <p class="error-msg">Failed to load vaults: {{ vaults.lastError }}</p>
      <button class="secondary" @click="vaults.refresh">Retry</button>
    </div>

    <div v-else-if="vaults.vaults.length === 0" class="card empty">
      <p class="muted">
        You don't have any vaults yet. Create one to get an MCP URL you can
        paste into Claude Desktop.
      </p>
      <router-link :to="{ name: 'vault-new' }">
        <button>+ Create your first vault</button>
      </router-link>
    </div>

    <ul v-else class="vault-grid">
      <li v-for="v in vaults.vaults" :key="v.id" class="card vault-card">
        <header class="vault-card-head">
          <h3>{{ v.agent_name }}</h3>
          <span class="status" :class="{ paused: v.paused }">
            {{ v.paused ? "Paused" : "Active" }}
          </span>
        </header>

        <dl class="kv">
          <div><dt>Daily cap</dt><dd>{{ v.daily_cap_usdc }} USDC</dd></div>
          <div><dt>Per call</dt><dd>{{ v.per_call_cap_usdc }} USDC</dd></div>
          <div>
            <dt>Allowlist</dt>
            <dd class="ellipsis">{{ v.endpoint_allowlist.join(", ") }}</dd>
          </div>
          <div><dt>Expires</dt><dd>{{ fmtDate(v.expires_at) }}</dd></div>
        </dl>

        <p class="vault-pda muted">
          PDA:&nbsp;
          <a
            :href="`https://solscan.io/account/${v.vault_pda}`"
            target="_blank"
            rel="noreferrer"
            >{{ v.vault_pda.slice(0, 6) }}…{{ v.vault_pda.slice(-6) }}</a
          >
        </p>

        <div class="btn-row">
          <router-link :to="{ name: 'vault-detail', params: { id: v.id } }">
            <button class="secondary">Manage</button>
          </router-link>
        </div>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.vaults-page {
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
  margin: 0;
}
.page-head p {
  margin: 0.25rem 0 0;
}
.empty {
  text-align: center;
}
.error-msg {
  color: var(--danger);
}
.vault-grid {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}
.vault-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 0 0 1rem;
}
.vault-card-head h3 {
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
.kv {
  display: grid;
  gap: 0.4rem;
  margin: 0 0 1rem;
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
}
.kv dd.ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 14rem;
}
.vault-pda {
  margin: 0 0 1rem;
  font-size: 0.85rem;
}
</style>
