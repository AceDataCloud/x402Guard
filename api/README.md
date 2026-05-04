# `api/` — x402guard FastAPI backend

The REST + per-vault MCP backend for x402guard. Co-located with the Anchor program (`../programs/`) and the Vue Dapp (`../web/`).

## Run locally

```bash
cd api
poetry install            # or: python -m venv .venv && pip install -e .
cp .env.example .env
poetry run uvicorn api.app:app --reload --port 8000
```

Then `curl http://localhost:8000/health` → `{"status":"ok","version":"0.1.0"}`.

## Test

```bash
PYTHONPATH=.. poetry run pytest tests/ -v
```

Test runner uses an in-memory SQLite database; no extra services required.

## What lives here

| Path | Purpose |
|---|---|
| `api/app.py` | FastAPI factory + middleware |
| `api/core/config.py` | Pydantic Settings (env + .env) |
| `api/core/db.py` | SQLAlchemy 2.x async session factory |
| `api/core/models.py` | ORM rows: `Vault`, `MCPSession`, `SpendRecord` |
| `api/core/solana.py` | RPC client + PDA derivation + endpoint hashing |
| `api/routes/health.py` | `/health` + `/.well-known/x402guard` |
| `api/tests/` | pytest suite (in-memory SQLite) |

## Out of scope for this PR

| Track | Lands in |
|---|---|
| Phantom signature auth + tx builders | next backend PR (`feat/api-vault-routes`) |
| Streamable HTTP MCP at `/mcp/<token>` | follow-up (`feat/api-mcp`) |
| Production K8s + Caddy ingress | own PR under `deploy/` |

## Notes

- We use SQLAlchemy 2.x async + `sqlite+aiosqlite` for local dev so route handlers stay native-async; production swaps to Postgres via `DATABASE_URL`.
- ORM models mirror on-chain accounts as a *projection*. The Anchor program is the source of truth — this DB is for "render the page without RPC roundtrips" and "issue MCP session tokens without hitting Solana on every spend."
- `connection_vault_key` (32-byte AES-256-GCM master key) is referenced here so the next PR's delegation-key wrapping has its config slot ready.
