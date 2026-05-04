/**
 * Wrapper around the Phantom provider.
 *
 * We deliberately don't use `@solana/wallet-adapter-react` — that's a
 * Vue/React-shaped stack we don't need. The Phantom API is small enough
 * to call directly, which keeps the bundle and the surface tight.
 */
import { Connection, PublicKey, Transaction, VersionedTransaction } from "@solana/web3.js";

export class PhantomNotInstalled extends Error {
  constructor() {
    super("Phantom wallet is not installed.");
    this.name = "PhantomNotInstalled";
  }
}

export class UserRejected extends Error {
  constructor() {
    super("User rejected the request in Phantom.");
    this.name = "UserRejected";
  }
}

export function getProvider(): PhantomProvider {
  const candidate = window.phantom?.solana ?? window.solana;
  if (!candidate || !candidate.isPhantom) {
    throw new PhantomNotInstalled();
  }
  return candidate;
}

export async function connectPhantom(): Promise<string> {
  const p = getProvider();
  try {
    const res = await p.connect();
    return res.publicKey.toBase58();
  } catch (err) {
    if ((err as { code?: number })?.code === 4001) throw new UserRejected();
    throw err;
  }
}

export async function disconnectPhantom(): Promise<void> {
  try {
    const p = getProvider();
    await p.disconnect();
  } catch {
    /* ignore — user may have already disconnected */
  }
}

export async function signMessage(message: string): Promise<string> {
  const p = getProvider();
  try {
    const encoded = new TextEncoder().encode(message);
    const res = await p.signMessage(encoded, "utf8");
    // base64 encode for transport — matches what the backend expects.
    return btoa(String.fromCharCode(...res.signature));
  } catch (err) {
    if ((err as { code?: number })?.code === 4001) throw new UserRejected();
    throw err;
  }
}

/**
 * Sign + send a base64-serialised legacy `Transaction`. The unsigned tx
 * comes from the backend (`/api/v1/vaults/create`, etc.), gets handed to
 * Phantom, and the wallet returns the network signature.
 */
export async function signAndSendBase64Tx(
  txBase64: string,
  connection: Connection
): Promise<string> {
  const p = getProvider();
  const raw = Uint8Array.from(atob(txBase64), (c) => c.charCodeAt(0));
  const tx = Transaction.from(raw);
  // Refresh the recent blockhash *just* before sign so we don't expire
  // while the user is staring at the Phantom popup.
  const { blockhash, lastValidBlockHeight } = await connection.getLatestBlockhash();
  tx.recentBlockhash = blockhash;
  tx.lastValidBlockHeight = lastValidBlockHeight;
  try {
    const result = await p.signAndSendTransaction(tx);
    return result.signature;
  } catch (err) {
    if ((err as { code?: number })?.code === 4001) throw new UserRejected();
    throw err;
  }
}

export async function confirmSig(
  connection: Connection,
  signature: string,
  timeoutMs = 30_000
): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const status = await connection.getSignatureStatuses([signature]);
    const s = status.value[0];
    if (s) {
      if (s.err) throw new Error(`tx failed: ${JSON.stringify(s.err)}`);
      if (
        s.confirmationStatus === "confirmed" ||
        s.confirmationStatus === "finalized"
      ) {
        return;
      }
    }
    await new Promise((r) => setTimeout(r, 800));
  }
  throw new Error(`tx confirmation timed out: ${signature}`);
}

/**
 * Suppress the obnoxious unused-import lints for types we re-export.
 */
export type { PublicKey, VersionedTransaction };
