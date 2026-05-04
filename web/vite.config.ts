import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// `process` import not needed: Vite injects env through `loadEnv`,
// but for our small surface we just use `import.meta.env.VITE_*`.
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Forward API + MCP traffic to the FastAPI dev server so the
      // browser doesn't need a separate origin in dev. Production
      // serves both off the same host (x402guard.acedata.cloud).
      "/api": "http://localhost:8000",
      "/mcp": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/.well-known": "http://localhost:8000",
    },
  },
});
