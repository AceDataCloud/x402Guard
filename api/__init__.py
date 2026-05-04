"""x402guard FastAPI backend.

Three surfaces, one app:

- Dapp REST API at `/api/*` — Phantom-authed CRUD for vaults
- Per-vault MCP at `/mcp/<token>` — Streamable HTTP for AI agents
- Operational endpoints `/health`, `/.well-known/...`

The Anchor program at `programs/agent_vault` is the spending boundary;
this service only **builds** Solana transactions for Phantom to sign or
**signs** them with a delegation key for the agent. We never custody
owner funds.
"""

__version__ = "0.1.0"
