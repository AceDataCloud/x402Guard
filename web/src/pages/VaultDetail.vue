<script setup lang="ts">
import { useRoute } from "vue-router";

const route = useRoute();
</script>

<template>
  <section class="container">
    <h2>Vault detail</h2>
    <p class="muted">
      Detail / pause / resume / clawback / MCP-session flows for vault
      <code>{{ route.params.id }}</code> land in the follow-up PR
      <code>feat/web-vault-flows</code>.
    </p>
    <router-link :to="{ name: 'vaults' }">← Back to vaults</router-link>
  </section>
</template>
