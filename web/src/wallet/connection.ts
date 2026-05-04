/**
 * Connection helper — Solana RPC URL config.
 *
 * Backend tells us which cluster it's on via `/.well-known/x402guard`,
 * but for tx confirmation we need a Solana RPC the browser can hit
 * directly. We default to the cluster's public RPC; ops can override
 * via `VITE_SOLANA_RPC_URL`.
 */
import { Connection } from "@solana/web3.js";

let _conn: Connection | null = null;

export function getConnection(): Connection {
  if (_conn) return _conn;
  const explicit = import.meta.env.VITE_SOLANA_RPC_URL;
  const cluster = import.meta.env.VITE_SOLANA_CLUSTER ?? "devnet";
  const url =
    explicit ??
    (cluster === "mainnet"
      ? "https://api.mainnet-beta.solana.com"
      : "https://api.devnet.solana.com");
  _conn = new Connection(url, "confirmed");
  return _conn;
}
