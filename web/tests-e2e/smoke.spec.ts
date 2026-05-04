import { test, expect } from "@playwright/test";

/**
 * Smoke tests for the home + vaults pages.
 *
 * No real wallet here — Phantom can't be controlled headlessly. We only
 * check that the static surface renders and the auth-gated route
 * redirects to home when no session is present.
 */

test("home page renders the pitch and the connect-Phantom CTA", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("h1")).toContainText(/Solana/);
  await expect(page.locator("h1")).toContainText(/on-chain/);

  const connect = page.getByTestId("connect-phantom");
  await expect(connect).toBeVisible();
  await expect(connect).toHaveText(/Connect Phantom/);
});

test("the three pillars are rendered", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("text=Mint a vault")).toBeVisible();
  await expect(page.locator("text=Plug into your agent")).toBeVisible();
  await expect(page.locator("text=Watch policy enforce on-chain")).toBeVisible();
});

test("/vaults redirects to home when not authenticated", async ({ page }) => {
  await page.goto("/vaults");
  // Router guard should bounce back to / with ?next=/vaults — the path
  // separator may or may not be percent-encoded depending on Vue Router
  // version, so accept both.
  await expect(page).toHaveURL(/\/\?next=(%2F|\/)vaults$/);
});

test("the new-vault form validates per-call <= daily client-side", async ({
  page,
}) => {
  // Forge a valid-looking session so the route guard lets us through.
  // We don't have to mint a real wallet — the form is fully client-side
  // until the Phantom signature step.
  await page.addInitScript(() => {
    localStorage.setItem(
      "x402guard.session",
      "eyJwdWJrZXkiOiJ0ZXN0IiwiZXhwIjo5OTk5OTk5OTk5fQ.signature"
    );
    localStorage.setItem("x402guard.pubkey", "TestPubkeyForRouting111111111111111111");
  });

  await page.goto("/vaults/new");

  // Bump per-call above daily, expect submit disabled.
  await page.getByTestId("daily-cap").fill("1");
  await page.getByTestId("per-call-cap").fill("5");
  await expect(page.getByTestId("submit")).toBeDisabled();

  // Bring it back into range.
  await page.getByTestId("per-call-cap").fill("0.5");
  await expect(page.getByTestId("submit")).toBeEnabled();
});
