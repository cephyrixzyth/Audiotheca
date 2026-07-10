import { expect, test } from "@playwright/test";

test.describe("Scan Flow smoke", () => {
  test("Scan tab shows flow presets including Almost full", async ({ page }) => {
    await page.goto("/");
    // First-run wizard or main shell — navigate to Scan when available.
    const scanTab = page.getByRole("button", { name: /^Scan$/i }).or(
      page.getByRole("tab", { name: /^Scan$/i }),
    );
    const skipWizard = page.getByRole("button", { name: /skip|later|continue|close/i });
    if (await skipWizard.first().isVisible().catch(() => false)) {
      await skipWizard.first().click();
    }
    if (await scanTab.first().isVisible().catch(() => false)) {
      await scanTab.first().click();
    } else {
      // Fallback: click nav text
      await page.locator("text=Scan").first().click();
    }

    const preset = page.locator("select.flow-preset-select, .flow-preset-select");
    await expect(preset.first()).toBeVisible({ timeout: 30_000 });
    const options = await preset.first().locator("option").allTextContents();
    const joined = options.join(" | ");
    expect(joined).toMatch(/Almost full/i);
    expect(joined).toMatch(/Full audit/i);
  });
});
