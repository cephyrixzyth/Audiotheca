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
  "/studio",
  "/library",
  "/review/deep-identify",
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
  await page.getByRole("tab", { name: "Scan", exact: true }).click();
  await expect(page).toHaveURL(/#\/scan(\?|$)/);
  await page.getByRole("tab", { name: "Review", exact: true }).click();
  await expect(page).toHaveURL(/#\/review\//);
  await page.getByRole("tab", { name: "System", exact: true }).click();
  await expect(page).toHaveURL(/#\/system\//);
  await page.getByRole("tab", { name: "Help", exact: true }).click();
  await expect(page).toHaveURL(/#\/help(\?|$)/);
});

test("ui-kit gallery route renders the primitives", async ({ page }) => {
  await page.goto("/#/ui-kit");
  await expect(page.getByRole("heading", { name: "Audiotheca UI kit" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Primary", exact: true })).toBeVisible();
});

test("command palette opens (Ctrl+K / button), filters, and navigates", async ({ page }) => {
  await page.goto("/#/dashboard");

  // Keyboard shortcut opens it.
  await page.keyboard.press("Control+k");
  const input = page.getByPlaceholder("Search tabs, actions, and spec codes…");
  await expect(input).toBeVisible();
  await input.fill("Restructure");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#\/review\/restructure/);

  // Topbar button opens it too, and spec codes are searchable.
  await page.getByRole("button", { name: /^Search / }).click();
  const input2 = page.getByPlaceholder("Search tabs, actions, and spec codes…");
  await expect(input2).toBeVisible();
  await input2.fill("WEB-SPDR");
  await expect(page.getByRole("option", { name: /WEB-SPDR/ })).toBeVisible();
  await page.keyboard.press("Escape");
});

test("selected run is deep-linked via ?run= and survives tab changes", async ({ page }) => {
  // Default run param is applied to the URL once runs load.
  await page.goto("/#/dashboard");
  await expect(page).toHaveURL(/run=/);

  // Deep-linking a specific run + tab selects that run in the toolbar.
  await page.goto("/#/review/duplicates?run=20260704_1300");
  await expect(page).toHaveURL(/#\/review\/duplicates\?run=20260704_1300/);
  await expect(page.getByRole("combobox", {name: "Run", exact: true})).toHaveValue("20260704_1300");

  // Changing tabs preserves the run param.
  await page.getByRole("tab", { name: "Scan audit", exact: true }).click();
  await expect(page).toHaveURL(/run=20260704_1300/);
});
