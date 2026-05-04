import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright e2e config.
 *
 * `npm run dev` is started by Playwright via the `webServer` block —
 * we don't have to manually `vite` in another tab. CI matches.
 */
export default defineConfig({
  testDir: "./tests-e2e",
  fullyParallel: false, // shared dev server, keep order predictable
  retries: 0,
  workers: 1,
  reporter: process.env.CI ? "list" : "html",
  use: {
    baseURL: "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
