<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";

import { useAuthStore } from "@/store/auth";
import { useVaultsStore } from "@/store/vaults";

const auth = useAuthStore();
const vaults = useVaultsStore();
const router = useRouter();

async function onSignIn() {
  await auth.signIn();
  await vaults.refresh();
  router.push({ name: "vaults" });
}

async function onSignOut() {
  await auth.signOut();
  router.push({ name: "home" });
}

onMounted(async () => {
  if (auth.isAuthenticated) {
    await vaults.refresh();
  }
});
</script>

<template>
  <header class="app-header">
    <div class="container header-row">
      <div class="brand">
        <img src="/favicon.svg" alt="" width="28" height="28" />
        <span class="brand-name">x402guard</span>
        <span class="muted brand-tag">Solana-native AI agent wallets</span>
      </div>

      <nav class="header-actions">
        <template v-if="auth.isAuthenticated">
          <router-link :to="{ name: 'vaults' }" class="nav-link">My vaults</router-link>
          <button
            class="secondary"
            @click="onSignOut"
            data-testid="sign-out"
          >
            <span class="muted">{{ auth.pubkey?.slice(0, 4) }}…{{ auth.pubkey?.slice(-4) }}</span>
            &nbsp;Sign out
          </button>
        </template>
        <template v-else>
          <button
            :disabled="auth.signingIn"
            @click="onSignIn"
            data-testid="connect-phantom"
          >
            {{ auth.signingIn ? "Connecting…" : "Connect Phantom" }}
          </button>
        </template>
      </nav>
    </div>
  </header>

  <main>
    <router-view />
  </main>
</template>

<style scoped>
.app-header {
  border-bottom: 1px solid var(--border);
  background: rgba(11, 11, 20, 0.85);
  backdrop-filter: blur(8px);
  position: sticky;
  top: 0;
  z-index: 50;
}
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding-top: 1rem;
  padding-bottom: 1rem;
}
.brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.brand-name {
  font-weight: 700;
  font-size: 1.05rem;
  letter-spacing: 0.02em;
}
.brand-tag {
  font-size: 0.85rem;
  margin-left: 0.5rem;
}
.header-actions {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}
.nav-link {
  color: var(--text);
  font-weight: 500;
}
.nav-link:hover {
  color: var(--solana-green);
  text-decoration: none;
}
@media (max-width: 600px) {
  .brand-tag {
    display: none;
  }
}
</style>
