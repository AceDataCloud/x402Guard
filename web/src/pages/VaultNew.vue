<script setup lang="ts">
/* New vault flow lands in the next PR (`feat/web-vault-flows`). The
   route already exists so the navigation hierarchy is stable. */
</script>

<template>
  <section class="container">
    <h2>New vault</h2>
    <p class="muted">
      Vault creation flow (Phantom signs <code>create_vault</code> ix) lands
      in the follow-up PR <code>feat/web-vault-flows</code>.
    </p>
    <router-link :to="{ name: 'vaults' }">← Back to vaults</router-link>
  </section>
</template>
