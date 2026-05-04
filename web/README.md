# `web/` — x402guard Dapp

Vue 3 + Vite + Pinia + Phantom wallet adapter. Lives at `https://x402guard.acedata.cloud` in production; runs at `http://localhost:5173` in dev with the FastAPI backend on `:8000`.

## Run locally

```bash
cd web
npm install
npm run dev    # → http://localhost:5173
```

The dev server proxies `/api/*`, `/mcp/*`, `/health`, and `/.well-known/*` to `http://localhost:8000` (the FastAPI backend), so the browser never has to deal with CORS in dev.

## Build

```bash
npm run build      # vue-tsc + vite build → dist/
npm run preview    # serve dist on :5173 for sanity-check
```

## Lint

```bash
npm run lint
```

## E2E tests

```bash
npm run test:e2e   # Playwright; auto-starts vite dev server
```

Smoke coverage only at this stage — no real wallet is used (Phantom can't run headlessly). The full e2e dance against devnet lands in a follow-up.

## Layout

```
src/
├── main.ts              app entry — Pinia + Router
├── App.vue              top-level shell (header + <router-view>)
├── router.ts            Vue Router with auth guard
├── env.d.ts             Phantom provider + Vite env types
├── styles/global.css    dark theme, Solana purple/green accents
├── api/client.ts        Axios + bearer token + 401 handler
├── wallet/phantom.ts    typed wrapper: connect, signMessage, signAndSend
├── store/
│   ├── auth.ts          Pinia: signIn / signOut / persistence
│   └── vaults.ts        Pinia: refresh / build tx / finalise / MCP sessions
└── pages/
    ├── Home.vue         hero + 3 pillars + CTAs
    ├── Vaults.vue       list user's vaults
    ├── VaultNew.vue     stub — full flow in next PR
    └── VaultDetail.vue  stub — full flow in next PR

tests-e2e/smoke.spec.ts  3 cases: home renders, pillars, /vaults guard
playwright.config.ts     auto-starts the dev server
```

## Out of scope for this PR

- Vault creation flow (Phantom signs `create_vault` ix) — `feat/web-vault-flows`
- Vault detail / pause / resume / clawback / MCP-session UI — same follow-up
- Production K8s + Caddy ingress — `feat/deploy-k8s-caddy`
