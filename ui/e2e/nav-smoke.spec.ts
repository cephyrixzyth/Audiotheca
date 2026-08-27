import { test, expect } from "@playwright/test";

/**
 * Navigation smoke test for the routing adoption.
 *
 * Verifies that every tab/sub-tab is reachable by URL (HashRouter), renders
 * inside the app shell, and that top-level nav still drives the router. This is
 * the regression gate that guarantees no screen was dropped by the migration.
 */

const TAB_PATHS: string[] = [
  "/dashboard",
  "/scan",
  "/review/investigation",
  "/review/duplicates",
  "/review/restructure",
  "/review/archives",
  "/review/scene-renames",
  "/review/scan-audit",
  "/review/skipped",
  "/system/space-recovery",
  "/system/security",
  "/system/environment",
  "/system/vendors",
  "/help",
];

test("root redirects to dashboard", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("header.topbar")).toBeVisible();
  await expect(page).toHaveURL(/#\/dashboard(\?|$)/);
});

for (const path of TAB_PATHS) {
  test(`route ${path} renders inside the shell`, async ({ page }) => {
    await page.goto(`/#${path}`);
    // Shell chrome is always present.
    await expect(page.locator(".app-shell")).toBeVisible();
    await expect(page.locator("header.topbar")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Audiotheca", level: 1 })).toBeVisible();
    // The main content region rendered something.
    await expect(page.locator("main.main")).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`#${path.replace(/\//g, "\\/")}(\\?|$)`));
  });
}

test("top navigation drives the router", async ({ page }) => {
  await page.goto("/#/dashboard");
  await page.getByRole("button", { name: "Scan", exact: true }).click();
  await expect(page).toHaveURL(/#\/scan(\?|$)/);
  await page.getByRole("button", { name: "Review", exact: true }).click();
  await expect(page).toHaveURL(/#\/review\//);
  await page.getByRole("button", { name: "System", exact: true }).click();
  await expect(page).toHaveURL(/#\/system\//);
  await page.getByRole("button", { name: "Help", exact: true }).click();
  await expect(page).toHaveURL(/#\/help(\?|$)/);
});

test("ui-kit gallery route renders the primitives", async ({ page }) => {
  await page.goto("/#/ui-kit");
  await expect(page.getByRole("heading", { name: "Audiotheca UI kit" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Primary", exact: true })).toBeVisible();
});

test("selected run is deep-linked via ?run= and survives tab changes", async ({ page }) => {
  // Default run param is applied to the URL once runs load.
  await page.goto("/#/dashboard");
  await expect(page).toHaveURL(/run=/);

  // Deep-linking a specific run + tab selects that run in the toolbar.
  await page.goto("/#/review/duplicates?run=20260704_1300");
  await expect(page).toHaveURL(/#\/review\/duplicates\?run=20260704_1300/);
  await expect(page.locator("select.field-input").first()).toHaveValue("20260704_1300");

  // Changing tabs preserves the run param.
  await page.getByRole("button", { name: "Scan audit", exact: true }).click();
  await expect(page).toHaveURL(/run=20260704_1300/);
});
