/**
 * Buffer polyfill — must be imported BEFORE any module that pulls in
 * @solana/web3.js or @solana/spl-token, which expect Node's Buffer at
 * module-load time. ESM hoists imports, so doing this in main.ts after
 * `import App` would be too late.
 */
import { Buffer } from "buffer";

if (typeof globalThis.Buffer === "undefined") {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).Buffer = Buffer;
}

export {};
