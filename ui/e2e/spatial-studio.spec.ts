import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("a studio edit reopens with its imported audio and renders a stereo file", async ({
  page,
  browser,
}) => {
  // Two clean browser contexts each decode audio, render a 3D room and export PCM.
  test.slow();
  await page.addInitScript(() =>
    localStorage.setItem("audiotheca.firstRunComplete", "1"),
  );
  await page.goto("/#/studio");
  await page.getByRole("button", { name: "Play mix" }).click();
  await expect(page.getByRole("button", { name: "Pause mix" })).toBeVisible();
  await page.getByRole("button", { name: "Pause mix" }).click();
  await page.getByRole("button", { name: "Return to start" }).click();
  // 0.25 s, mono PCM. Imports go through decodeAudioData and IndexedDB.
  const frames = 11025,
    wav = Buffer.alloc(44 + frames * 2);
  wav.write("RIFF");
  wav.writeUInt32LE(wav.length - 8, 4);
  wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(44100, 24);
  wav.writeUInt32LE(88200, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write("data", 36);
  wav.writeUInt32LE(frames * 2, 40);
  for (let i = 0; i < frames; i++)
    wav.writeInt16LE(Math.round(12000 * Math.sin(i * 0.063)), 44 + i * 2);
  await page.getByLabel("Import audio files").setInputFiles({
    name: "Piano take.wav",
    mimeType: "audio/wav",
    buffer: wav,
  });
  await expect(
    page.getByRole("heading", { name: "Piano take.wav" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Solo", exact: true }).click();
  await page.getByRole("slider", { name: "Trim in" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("slider", { name: "Trim in" })).toHaveValue(
    "0.001",
  );
  await page.getByRole("button", { name: "Remove track" }).click();
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(
    page.getByText("Saved on this device", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: /Piano take.wav/ }).click();
  await expect(
    page.getByRole("button", { name: "Solo", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("slider", { name: "Trim in" })).toHaveValue(
    "0.001",
  );
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Export stereo WAV" }).click(),
  ]);
  const audio = await readFile((await download.path())!);
  expect(audio.toString("ascii", 0, 4)).toBe("RIFF");
  expect(audio.readUInt16LE(22)).toBe(2);
  expect(audio.readUInt32LE(24)).toBe(44100);
  let energy = 0,
    tail = 0;
  for (let i = 44; i < audio.length; i += 4) {
    if (i < 44100 * 4) energy += Math.abs(audio.readInt16LE(i));
    else tail += Math.abs(audio.readInt16LE(i));
  }
  expect(energy).toBeGreaterThan(100000);
  expect(tail).toBe(0);
  const [portable] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Save project file" }).click(),
  ]);
  const other = await browser.newContext({
    baseURL: new URL(page.url()).origin,
  });
  try {
    await other.addInitScript(() =>
      localStorage.setItem("audiotheca.firstRunComplete", "1"),
    );
    const clean = await other.newPage();
    await clean.goto("/#/studio");
    await expect(
      clean.getByText("Demo session · edits save on this device"),
    ).toBeVisible();
    await clean
      .getByLabel("Open portable project")
      .setInputFiles((await portable.path())!);
    await clean.getByRole("button", { name: /Piano take.wav/ }).click();
    await expect(
      clean.getByRole("button", { name: "Solo", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await expect(clean.getByRole("slider", { name: "Trim in" })).toHaveValue(
      "0.001",
    );
    const [exported] = await Promise.all([
      clean.waitForEvent("download"),
      clean.getByRole("button", { name: "Export stereo WAV" }).click(),
    ]);
    expect((await readFile((await exported.path())!)).equals(audio)).toBe(true);
  } finally {
    await other.close();
  }
});

test("speaker position changes the stereo balance of the actual mix", async ({
  page,
}) => {
  await page.addInitScript(() =>
    localStorage.setItem("audiotheca.firstRunComplete", "1"),
  );
  await page.goto("/#/studio");
  await page.getByRole("button", { name: /Brush pulse/ }).click();
  await page.getByRole("button", { name: "Solo", exact: true }).click();
  await page.getByText("Speaker position", { exact: true }).click();
  const position = page.getByRole("slider", { name: "Left / right" });
  async function channelEnergy(key: string) {
    await position.focus();
    await page.keyboard.press(key);
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Export stereo WAV" }).click(),
    ]);
    await expect(
      page.getByRole("link", { name: "Download rendered WAV" }),
    ).toBeVisible();
    const bytes = await readFile((await download.path())!);
    const sum = [0, 0];
    for (let i = 44; i < bytes.length; i += 4) {
      sum[0] += bytes.readInt16LE(i) ** 2;
      sum[1] += bytes.readInt16LE(i + 2) ** 2;
    }
    return sum;
  }
  const left = await channelEnergy("Home"),
    right = await channelEnergy("End");
  expect(left[0]).toBeGreaterThan(left[1] * 1.1);
  expect(right[1]).toBeGreaterThan(right[0] * 1.1);
});
