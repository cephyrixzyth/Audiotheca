import { expect, test } from "@playwright/test";

test("duplicate filters and page six reopen independently for each scan", async ({ page }) => {
  // The seeded API supplies real runs and saved decisions. Size only the list response
  // so this UI test can exercise later pages without manufacturing 600 file groups.
  await page.route("**/api/runs/*/duplicates?**", route =>
    route.fulfill({ json: { groups: [], total: 601 } }),
  );
  const run = page.getByRole("combobox", { name: "Run", exact: true });
  const confidence = page.getByRole("combobox", { name: "Confidence", exact: true });
  const search = page.locator("#context-sidebar-search");
  const next = page.getByRole("button", { name: "Next", exact: true });
  await page.goto("/#/review/duplicates?run=20260704_1300");
  await search.fill("Tape");
  await confidence.selectOption("MEDIUM");
  for (let i = 0; i < 5; i++) await next.click();
  await expect(page.getByText("501–600 of 601 groups")).toBeVisible();
  await page.reload();
  await expect(search).toHaveValue("Tape");
  await expect(confidence).toHaveValue("MEDIUM");
  await expect(page.getByText("501–600 of 601 groups")).toBeVisible();
  await run.selectOption("20260704_1600");
  await expect(search).toHaveValue("");
  await expect(confidence).toHaveValue("HIGH");
  await expect(page.getByText("1–100 of 601 groups")).toBeVisible();
  await run.selectOption("20260704_1300");
  await expect(page.getByText("501–600 of 601 groups")).toBeVisible();
  await search.fill("Keys");
  await expect(page.getByText("1–100 of 601 groups")).toBeVisible();
});
