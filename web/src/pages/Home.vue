<script setup lang="ts">
import { computed } from "vue";

import { useAuthStore } from "@/store/auth";

const auth = useAuthStore();
const cta = computed(() =>
  auth.isAuthenticated ? "Go to my vaults" : "Connect Phantom to begin"
);
</script>

<template>
  <section class="hero container">
    <h1>
      Give your AI agent a <span class="purple">Solana</span> wallet.<br />
      Keep the rules <span class="green">on-chain</span>.
    </h1>
    <p class="muted lede">
      x402guard mints a PDA-controlled USDC vault with a spending policy your
      agent can't escape. Plug a personal MCP URL into Claude / Cursor and let
      the agent pay for x402 APIs autonomously — every transfer gated by your
      daily cap, per-call cap, and endpoint allowlist.
    </p>

    <div class="btn-row">
      <router-link to="/vaults" v-if="auth.isAuthenticated">
        <button>{{ cta }}</button>
      </router-link>
      <a href="https://github.com/AceDataCloud/x402guard" target="_blank" rel="noreferrer">
        <button class="secondary">View on GitHub</button>
      </a>
    </div>
  </section>

  <section class="how container">
    <div class="card pillar">
      <h3>1 · Mint a vault</h3>
      <p class="muted">
        Connect Phantom, pick a daily cap and per-call cap, list the API hosts
        the agent is allowed to spend on. Phantom signs an Anchor
        <code>create_vault</code> ix. The vault is a PDA — no private key, only
        the program can move funds.
      </p>
    </div>

    <div class="card pillar">
      <h3>2 · Plug into your agent</h3>
      <p class="muted">
        Paste a per-vault MCP URL into Claude Desktop, Cursor, or any MCP
        client. Four tools light up:
        <code>aceguard_balance</code>,
        <code>aceguard_history</code>,
        <code>aceguard_spend</code>,
        <code>aceguard_pay_for_api</code>.
      </p>
    </div>

    <div class="card pillar">
      <h3>3 · Watch policy enforce on-chain</h3>
      <p class="muted">
        The agent autonomously calls paid APIs. Every <code>spend</code> ix is
        validated by the on-chain program before the SPL transfer fires —
        per-call cap, daily cap, allowlist, replay nonce, paused / expired.
        Pause or claw back at any time.
      </p>
    </div>
  </section>
</template>

<style scoped>
.hero {
  padding-top: 4rem;
  padding-bottom: 2rem;
}
.hero h1 {
  font-size: clamp(1.7rem, 4.2vw, 3rem);
  line-height: 1.15;
  margin: 0 0 1rem;
}
.purple {
  color: var(--solana-purple);
}
.green {
  color: var(--solana-green);
}
.lede {
  max-width: 720px;
  font-size: 1.1rem;
  margin: 0 0 2rem;
}
.how {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
  padding-bottom: 4rem;
}
.pillar h3 {
  margin: 0 0 0.5rem;
}
.pillar code {
  background: var(--bg);
  padding: 0.1em 0.4em;
  border-radius: 4px;
  font-size: 0.9em;
}
@media (max-width: 800px) {
  .how {
    grid-template-columns: 1fr;
  }
}
</style>
