import { expect, test } from "@playwright/test";

test("the offline reader supports keyboard navigation and user-controlled media", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() =>
    localStorage.setItem("audiotheca.firstRunComplete", "1"),
  );
  await page.route(url => url.pathname.startsWith("/api/") || !["localhost", "127.0.0.1"].includes(url.hostname),
    route => route.abort("internetdisconnected"));
  const requested: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/help/"))
      requested.push(request.url());
  });
  await page.goto("/#/help?topic=start&run=20260704_1600");
  const manual = page.getByRole("region", { name: "Audiotheca help" });
  await expect(
    manual.getByRole("heading", { name: "Your first library scan" }),
  ).toBeVisible();
  expect(requested).toEqual([]);
  const search = manual.getByRole("searchbox", { name: "Find a guide" });
  await search.fill("spatial audio");
  const topic = manual.getByRole("button", {
    name: "Edit and mix in spatial audio",
  });
  await topic.focus();
  await page.keyboard.press("Enter");
  const title = manual.getByRole("heading", {
    name: "Edit and mix in spatial audio",
  });
  await expect(title).toBeFocused();
  await expect(page).toHaveURL(/topic=studio/);
  await expect(
    manual.getByRole("link", { name: "Open Studio" }),
  ).toHaveAttribute("href", /studio\?run=20260704_1600/);
  await manual.getByRole("button", { name: "View screenshot" }).click();
  await expect
    .poll(() =>
      manual
        .locator("figure img")
        .evaluate((image: HTMLImageElement) => image.naturalWidth),
    )
    .toBeGreaterThan(0);
  await manual.getByRole("button", { name: "View walkthrough" }).click();
  const video = manual.locator("video");
  await expect(video).toHaveJSProperty("controls", true);
  await expect(video).toHaveJSProperty("paused", true);
  await expect
    .poll(() =>
      video.evaluate((element: HTMLVideoElement) => element.readyState),
    )
    .toBeGreaterThanOrEqual(1);
  await manual.getByRole("button", { name: "Close walkthrough" }).click();
  await expect(video).toHaveCount(0);
  await search.fill("no-such-guide");
  await expect(manual.getByRole("status")).toContainText("0 matching guides");
  await manual.getByRole("button", { name: "Clear search" }).click();
  await expect(search).toHaveValue("");
});
