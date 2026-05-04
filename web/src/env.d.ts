/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_SOLANA_CLUSTER?: "devnet" | "mainnet";
  readonly VITE_PHANTOM_REQUIRED?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Phantom injects a partial provider on `window.solana`. We type only the
// pieces we actually call so TypeScript can keep the rest honest.
interface PhantomProvider {
  isPhantom?: boolean;
  publicKey?: { toBase58(): string } | null;
  isConnected?: boolean;
  connect: (opts?: { onlyIfTrusted?: boolean }) => Promise<{
    publicKey: { toBase58(): string };
  }>;
  disconnect: () => Promise<void>;
  signMessage: (msg: Uint8Array, encoding?: string) => Promise<{
    signature: Uint8Array;
    publicKey: { toBase58(): string };
  }>;
  signAndSendTransaction: (
    tx: import("@solana/web3.js").Transaction | import("@solana/web3.js").VersionedTransaction
  ) => Promise<{ signature: string; publicKey: { toBase58(): string } }>;
  on?: (event: string, handler: (...args: unknown[]) => void) => void;
  removeListener?: (event: string, handler: (...args: unknown[]) => void) => void;
}

interface Window {
  solana?: PhantomProvider;
  phantom?: { solana?: PhantomProvider };
}
