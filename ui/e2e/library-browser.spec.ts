import { expect, test, type Locator, type Page } from "@playwright/test";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { basename, dirname, join } from "node:path";

async function openLibrary(page: Page) {
  const roots = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      url.pathname.endsWith("/browse/enriched") &&
      url.searchParams.get("path") === "" &&
      response.ok()
    );
  });
  await page.getByRole("tab", { name: "Library", exact: true }).click();
  return (await (await roots).json()).entries[0].path as string;
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() =>
    localStorage.setItem("audiotheca.firstRunComplete", "1"),
  );
  await page.goto("/#/dashboard");
});

test("browse beyond one page, search again, and route pasted paths and browser drops", async ({
  page,
}) => {
  test.setTimeout(60_000);
  const root = await openLibrary(page);
  // The test server owns this temporary library. Never seed an operator's live folder.
  expect(basename(root)).toBe("library");
  expect(basename(dirname(root))).toMatch(/^audiotheca-browser-/);
  const folder = await mkdtemp(join(root, "explorer-paging-"));
  for (let block = 0; block < 501; block += 50) {
    await Promise.all(
      Array.from({ length: Math.min(50, 501 - block) }, (_, index) =>
        writeFile(
          join(folder, `take-${String(index + block).padStart(3, "0")}.txt`),
          "audio metadata",
        ),
      ),
    );
  }
  const sub = join(folder, "Samples");
  await mkdir(sub);
  const wav = join(sub, "drum.wav");
  const header = Buffer.alloc(46);
  header.write("RIFF");
  header.writeUInt32LE(38, 4);
  header.write("WAVEfmt ", 8);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(44100, 24);
  header.writeUInt32LE(88200, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(2, 40);
  await writeFile(wav, header);

  const pathInput = page.getByRole("textbox", {
    name: "Library path to inspect",
  });
  await pathInput.fill(folder);
  await page.getByRole("button", { name: "Inspect path" }).click();
  await expect(page.getByText(/500 of 502 items/)).toBeVisible();
  await page.getByRole("button", { name: "Load more items" }).click();
  await expect(page.getByText(/502 of 502 items/)).toBeVisible();
  const search = page.getByRole("searchbox", { name: "Search paths" });
  await search.fill("take-500");
  await expect(
    page.getByRole("button", { name: "Select take-500.txt" }),
  ).toBeVisible();
  await search.fill("take-");
  await search.press("Enter");
  await expect(page.getByText(/200 matches .*Search incomplete/)).toBeVisible();
  await page.getByRole("button", { name: "Continue search" }).click();
  await page.getByRole("button", { name: "Continue search" }).click();
  await expect(page.getByText(/501 matches .*Search complete/)).toBeVisible();

  const dropZone = page.locator(".drop-zone-overlay");
  await dropZone.evaluate((node) => {
    const transfer = new DataTransfer();
    transfer.items.add(new File(["local"], "unavailable.wav"));
    node.dispatchEvent(
      new DragEvent("drop", { bubbles: true, dataTransfer: transfer }),
    );
  });
  await expect(
    page.getByText(/Browser file drops do not include a server path/),
  ).toBeVisible();
  await dropZone.evaluate(
    (node, payload) => {
      const transfer = new DataTransfer();
      transfer.setData("text/plain", payload);
      node.dispatchEvent(
        new DragEvent("drop", { bubbles: true, dataTransfer: transfer }),
      );
    },
    [sub, wav, join(root, "missing")].join("\n"),
  );
  await expect(
    page.getByRole("button", { name: "Browse Samples" }),
  ).toBeVisible();
  await expect(page.getByText(/missing.*not found/)).toBeVisible();
  await page.getByRole("button", { name: "Audition drum.wav" }).click();
  await expect(page.getByLabel("Spot preview")).toBeVisible();
  await page.getByRole("button", { name: "Add to mix" }).click();
  await expect(page).toHaveURL(/studio\?path=.*drum.wav/);
  await expect(
    page.getByRole("heading", { name: "drum.wav", exact: true }),
  ).toBeVisible({ timeout: 20000 });
});

test("the Tauri webview drop event opens the dropped folder", async ({
  page,
}) => {
  await page.evaluate(async () => {
    const module = "/node_modules/@tauri-apps/api/mocks.js";
    const { mockIPC, mockWindows } = await import(module);
    mockWindows("main");
    mockIPC(
      (command: string) =>
        command === "api_base_url" ? location.origin + "/api" : null,
      { shouldMockEvents: true },
    );
  });
  const root = await openLibrary(page);
  const droppedFolder = await mkdtemp(join(root, "tauri-dropped-"));
  await expect(
    page.getByPlaceholder("Drop a file or paste a library path"),
  ).toBeVisible();
  async function expectNativeDrop(path: string, pane: Locator) {
    const view = pane.getByRole("navigation", { name: "Current path" });
    await expect(async () => {
      await page.evaluate(async (target) => {
        const module = "/node_modules/@tauri-apps/api/event.js";
        const { emit } = await import(module);
        await emit("tauri://drag-drop", {
          paths: [target],
          position: { x: 12, y: 16 },
        });
      }, path);
      await expect(
        view.getByRole("button", { name: "Open " + path, exact: true }),
      ).toBeVisible({ timeout: 600 });
    }).toPass({ timeout: 10000 });
  }
  const workspace = page.getByRole("region", { name: "Library explorer" });
  await expectNativeDrop(droppedFolder, workspace);
  await workspace.getByRole("button", { name: "Open as panel" }).click();
  const dialog = page.getByRole("dialog", { name: "Library explorer" });
  const modalFolder = await mkdtemp(join(root, "panel-dropped-"));
  await expectNativeDrop(modalFolder, dialog);
  await dialog.getByRole("button", { name: "Close", exact: true }).click();
  await expect(
    workspace.getByRole("button", {
      name: "Open " + droppedFolder,
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    workspace.getByRole("button", { name: "Open " + modalFolder, exact: true }),
  ).toHaveCount(0);
});
