import { chromium, expect } from "@playwright/test";
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import { join, basename } from "node:path";
import { spawnSync } from "node:child_process";
import { setTimeout as pause } from "node:timers/promises";

const config = JSON.parse(await fs.readFile(process.argv[2], "utf8"));
const selected = new Set((config.only || "").split(",").filter(Boolean));
const { origin, lib, output } = config;
const assert = expect.configure({ timeout: 20000 });
if (
  new URL(origin).hostname !== "127.0.0.1" ||
  !basename(config.workspace).startsWith("Audiotheca-Demo-") ||
  lib !== join(config.workspace, "Sound Library")
)
  throw Error("The capture requires its disposable local fixture.");
const viewport = { width: 1440, height: 900 };
const artifacts = [];
for (const d of ["screenshots", "videos", "gifs", "recording"])
  await fs.mkdir(join(output, d), { recursive: true });
const browser = await chromium.launch({
  args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"],
});
const steps = [];
let ctx, page, devtools, started, firstFrame, currentName, idleStart, idleEnd;
const synth = join(lib, "a", "AcmeAudio", "SynthOne");
const audio = join(synth, "kick_120bpm_C.wav");
const mystery = join(lib, "a", "UnknownVendor", "MysteryPack");
const route = async (path) => {
  await page.goto(origin + "/#/" + path + "?run=20260704_1600");
  await assert(page.locator("main")).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
};
const button = (name, scope = page) =>
  scope.getByRole("button", { name, exact: typeof name === "string" }).first();
const sections = {
  flow: "Processing flow",
  controls: "Run controls",
  "ai-analyzer": "AI analyzer",
  appearance: "Theme studio",
  "orchestration-tools": "Orchestration tools",
  "spec-catalog": "Architecture spec catalog",
  "cloud-storage": "Cloud & storage telemetry",
};
const section = (id) =>
  page
    .getByRole("heading", { name: sections[id], exact: true })
    .locator(
      'xpath=ancestor::*[contains(concat(" ",normalize-space(@class)," ")," widget-group-pane ") or self::section][1]',
    );
async function show(node) {
  await node.waitFor({ state: "visible" });
  await node.evaluate((el) =>
    el.scrollIntoView({ block: "center", behavior: "instant" }),
  );
  await pause(220);
}
async function verify(name, node, pattern) {
  await node.waitFor({ state: "visible" });
  if (pattern) await assert(node).toContainText(pattern);
  steps.push({ action: name, route: new URL(page.url()).hash });
  if (!firstFrame) firstFrame = performance.now();
  await pause(600);
}
async function click(node, name) {
  await show(node);
  if (!firstFrame) firstFrame = performance.now();
  await node.click();
  steps.push({ action: name, route: new URL(page.url()).hash });
  await pause(420);
}
async function shot(name, witness, pattern) {
  await verify(name, witness, pattern);
  if (
    selected.size &&
    !selected.has("screenshots") &&
    !selected.has(name) &&
    !selected.has(currentName)
  )
    return;
  const target = join(output, "screenshots", name + ".png");
  const frame = await devtools.send("Page.captureScreenshot", {
    format: "png",
    optimizeForSpeed: true,
  });
  await fs.writeFile(target, Buffer.from(frame.data, "base64"));
  artifacts.push({
    type: "screenshot",
    name,
    route: new URL(page.url()).hash,
    observed: (await witness.innerText()).slice(0, 200),
  });
}
async function panel(id) {
  const block = section(id);
  await show(block);
  const collapsed = block.getByRole("button", { name: /^Expand / }).first();
  if (await collapsed.count()) await collapsed.click();
  const heading = block.getByRole("heading", {
    name: sections[id],
    exact: true,
  });
  await heading.evaluate((el) => {
    el.style.scrollMarginBlockStart = "2rem";
    el.scrollIntoView({ block: "start", behavior: "instant" });
  });
  await pause(200);
  return block;
}
async function explorer(path) {
  await route("library");
  const shell = page.locator("main");
  await assert(
    shell
      .getByRole("button", { name: "Open folder Sound Library" })
      .or(shell.getByRole("button", { name: "Open folder a", exact: true }))
      .first(),
  ).toBeVisible();
  const field = shell.getByLabel("Library path to inspect");
  await field.fill(path);
  await click(
    button("Inspect path", shell),
    "Inspect the selected server path",
  );
  await assert(
    shell.getByRole("navigation", { name: "Current path" }),
  ).toContainText(basename(path));
  return shell;
}
function command(args) {
  const p = spawnSync(
    "ffmpeg",
    ["-hide_banner", "-loglevel", "error", "-y", ...args],
    { encoding: "utf8", maxBuffer: 4e6 },
  );
  if (p.status !== 0) throw Error(p.stderr || "ffmpeg failed");
}
async function scenario(name, shots, actions) {
  if (
    selected.size &&
    !selected.has(name) &&
    !(name && selected.has("walkthroughs")) &&
    !shots.some((s) => selected.has(s)) &&
    !(shots.length && selected.has("screenshots"))
  )
    return;
  currentName = name;
  steps.length = 0;
  firstFrame = 0;
  idleStart = 0;
  idleEnd = 0;
  const record =
    Boolean(name) &&
    (!selected.size || selected.has(name) || selected.has("walkthroughs"));
  ctx = await browser.newContext({
    viewport,
    deviceScaleFactor: 1,
    colorScheme: "dark",
    reducedMotion: "no-preference",
    ...(record
      ? { recordVideo: { dir: join(output, "recording"), size: viewport } }
      : {}),
  });
  await ctx.addInitScript(() =>
    localStorage.setItem("audiotheca.firstRunComplete", "1"),
  );
  started = performance.now();
  page = await ctx.newPage();
  devtools = await ctx.newCDPSession(page);
  page.setDefaultTimeout(30000);
  console.log("Capture", name || shots.join(","));
  try {
    await actions();
    await pause(700);
  } catch (err) {
    await fs
      .writeFile(
        join(output, "diagnostic.txt"),
        await page
          .locator("main")
          .innerText()
          .catch(() => ""),
      )
      .catch(() => {});
    throw err;
  }
  const video = page.video();
  await ctx.close();
  if (record) {
    if (steps.length < 2) throw Error("No verified interaction for " + name);
    const source = await video.path(),
      clip = join(output, "videos", name + ".mp4"),
      gif = join(output, "gifs", name + ".gif");
    const lead = Math.max(0, (firstFrame - started) / 1000 - 0.4);
    const cut =
      idleEnd - idleStart > 5000
        ? "select='not(between(t," +
          ((idleStart - started) / 1000 - lead + 2).toFixed(2) +
          "," +
          ((idleEnd - started) / 1000 - lead - 0.8).toFixed(2) +
          "))',setpts=N/FRAME_RATE/TB,"
        : "";
    command([
      "-ss",
      lead.toFixed(2),
      "-i",
      source,
      "-an",
      "-vf",
      cut + "fps=16,scale=1280:800:flags=lanczos",
      "-c:v",
      "libx264",
      "-preset",
      "veryfast",
      "-crf",
      "21",
      "-pix_fmt",
      "yuv420p",
      "-movflags",
      "+faststart",
      clip,
    ]);
    command([
      "-i",
      clip,
      "-vf",
      "fps=7,scale=1000:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
      "-loop",
      "0",
      gif,
    ]);
    artifacts.push({ type: "walkthrough", name, steps: [...steps] });
    await fs.unlink(source);
  }
}
try {
  await scenario(
    "first-scan-walkthrough",
    ["ui-overview", "dashboard-gauges"],
    async () => {
      await route("dashboard");
      const run = page.getByRole("combobox", { name: "Run", exact: true });
      await assert(run).toHaveValue("20260704_1600");
      await assert(page.locator(".home-ledger").first()).toContainText(
        "128 items",
        { timeout: 20000 },
      );
      await shot("ui-overview", page.locator(".station-grid"));
      await click(button("Run analysis"), "Open the saved run analysis");
      const gauge = page.getByText(/Route.ready/i, { exact: false }).first();
      await show(gauge);
      await shot("dashboard-gauges", gauge);
      await route("scan");
      const start = button(/Start dry.run scan/i);
      await show(start);
      const launch = page.waitForResponse(
        (r) =>
          r.request().method() === "POST" &&
          /\/api\/jobs$/.test(new URL(r.url()).pathname),
        { timeout: 10000 },
      );
      await click(start, "Start the dry scan in the fixture library");
      const response = await launch;
      expect(response.ok()).toBeTruthy();
      await verify("Dry scan accepted by the server", page.locator("main"));
      idleStart = performance.now();
      await assert
        .poll(
          async () =>
            (
              await fs.readdir(
                join(config.workspace, "Application data", "dedupe_reports"),
              )
            ).filter(
              (p) => p.startsWith("Run_Summary_") && !p.includes("20260704_"),
            ).length,
          { timeout: 240000 },
        )
        .toBeGreaterThan(0);
      idleEnd = performance.now();
      await route("dashboard");
      await assert.poll(() => run.locator("option").count()).toBeGreaterThan(2);
      const newer = await run.locator("option").allTextContents();
      const value = await run.locator("option").first().getAttribute("value");
      if (!value || value === "20260704_1600")
        throw Error("Expected a fresh scan, received " + newer);
      await page.goto(origin + "/#/dashboard?run=" + encodeURIComponent(value));
      await assert(run).toHaveValue(value);
      await click(button("Run analysis"), "Open analysis for the completed scan");
      const summary = page.locator(".dash-run-banner");
      await assert(summary).toContainText(value);
      await verify("Read the completed dry-run dashboard", summary, /Dry run/i);
      expect(new URL(page.url()).hash).toContain("#/dashboard?run=" + value);
    },
  );
  await scenario("scan-phases-and-flow", ["scan-panel"], async () => {
    await route("scan");
    const flow = await panel("flow");
    await shot("scan-panel", flow, /flow/i);
    const toggle = flow.getByRole("switch", {
      name: /Skip Deep identification/i,
    });
    await click(toggle, "Skip the deep-identification phase");
    await verify(
      "Confirm the phase can be enabled again",
      flow.getByRole("switch", { name: /Enable Deep identification/i }),
    );
    await show(section("controls"));
    await verify("Inspect dry-run controls", section("controls"));
  });
  await scenario(
    "investigation-and-vendors",
    ["investigation-inbox"],
    async () => {
      await route("review/investigation");
      await click(
        page.getByRole("tab", { name: "All items" }),
        "Show individual items",
      );
      const row = page
        .locator("main tr")
        .filter({ hasText: "MysteryPack" })
        .first();
      await show(row);
      await shot("investigation-inbox", row);
      await route("system/vendors");
      await click(
        page.getByRole("tab", { name: "Vendor database" }),
        "Open the local keyword database",
      );
      await verify(
        "Inspect vendor keyword controls",
        page.locator("main"),
        /keyword/i,
      );
    },
  );
  await scenario("investigation-lookup", ["investigation-lookup"], async () => {
    await route("review/investigation");
    await click(
      page.getByText("Look up vendor evidence", { exact: true }),
      "Expand vendor lookup",
    );
    const lookup = page.locator(".investigation-lookup-panel");
    await show(lookup);
    await verify("Open the investigation lookup", lookup);
    await lookup.getByRole("textbox").first().fill("Acme Audio SynthOne");
    await click(button("Plan", lookup), "Plan the local search query");
    const result = lookup.getByText(/Preset .*outbound/i);
    await assert(result).toBeVisible();
    await show(lookup);
    await shot("investigation-lookup", result);
    await lookup
      .getByLabel("Release text for tag generation")
      .fill("Acme Audio SynthOne analog synthesizer drum presets");
    await click(
      button("Generate tags", lookup),
      "Generate tags from release text",
    );
    await verify("Read the generated tags", lookup.getByText(/^Tags:/i));
  });
  await scenario("ai-lookup-review", [], async () => {
    await route("scan");
    await click(button("Diagnostics"), "Open scan diagnostics");
    const ai = await panel("ai-analyzer");
    await verify("Open the AI analyzer", ai);
    await ai.getByLabel("Manual lookup path").fill(mystery);
    await click(button("Query", ai), "Query the local identification provider");
    const card = ai.locator(".ai-result-card").first();
    await show(card);
    await card.hover();
    await verify(
      "Read the local identification suggestion",
      card,
      /MysteryPack|Mystery Pack/i,
    );
    const reject = button("Reject", card);
    if (await reject.count()) {
      await click(reject, "Reject the suggestion for this disposable review");
      await verify(
        "Return to the reviewed discoveries",
        ai.getByText("Discoveries", { exact: true }),
      );
    }
  });
  await scenario(
    "archive-diff-wizard",
    ["archives-verdicts", "archive-diff-wizard"],
    async () => {
      await route("review/archives");
      const row = page
        .locator("tr")
        .filter({ hasText: "redundant.zip" })
        .first();
      await show(row);
      await shot("archives-verdicts", row);
      await click(
        button(/Diff|Compare/, row),
        "Compare the archive with its extracted folder",
      );
      const modal = page.getByRole("dialog");
      await show(modal);
      await shot("archive-diff-wizard", modal, /Drums\/Kick.wav/i);
      await click(button("Keep archive", modal), "Protect the archive");
      await verify(
        "Read the saved keeper decision",
        modal.getByRole("status"),
        /Keeper set to archive/i,
      );
    },
  );
  await scenario(
    "file-explorer-and-archives",
    ["file-explorer", "dropzone-overlay"],
    async () => {
      const shell = await explorer(join(lib, "archives"));
      const archive = button("List archive redundant.zip", shell);
      await show(archive);
      await shot("file-explorer", archive);
      await shell.locator(".drop-zone-overlay").evaluate(
        (node, paths) => {
          const transfer = new DataTransfer();
          transfer.setData("text/plain", paths.join("\n"));
          node.dispatchEvent(
            new DragEvent("drop", { bubbles: true, dataTransfer: transfer }),
          );
        },
        [
          join(lib, "archives", "redundant_extracted"),
          join(lib, "archives", "redundant.zip"),
        ],
      );
      const routes = shell.getByRole("list", { name: "Drop results" });
      await show(routes);
      await shot("dropzone-overlay", routes, /redundant_extracted/);
      await click(archive, "List the ZIP members");
      await verify(
        "Inspect members without extraction",
        shell.getByText("Drums/Kick.wav", { exact: true }).first(),
      );
    },
  );
  await scenario("audio-preview-library", ["audio-preview"], async () => {
    const shell = await explorer(synth);
    const take = button("Select kick_120bpm_C.wav", shell);
    await verify("Locate the drum recording", take);
    await click(take, "Select the drum recording");
    const preview = shell.getByLabel("Spot preview");
    await show(preview);
    const play = preview.getByRole("button", {
      name: "Preview kick_120bpm_C.wav",
      exact: true,
    });
    if (await play.count())
      await click(play, "Audition the selected recording");
    const stop = preview.getByRole("button", {
      name: "Stop preview of kick_120bpm_C.wav",
      exact: true,
    });
    await assert(stop).toBeVisible();
    await shot("audio-preview", preview);
    if (await stop.count()) await stop.click();
  });
  await scenario(
    "environment-and-spec-catalog",
    [
      "environment-themes",
      "environment-orchestration",
      "environment-spec-catalog",
      "environment-cloud-storage",
    ],
    async () => {
      await route("system/environment");
      await click(
        page.getByRole("tab", { name: "Workspace setup" }),
        "Open workspace tools",
      );
      for (const [id, name] of [
        ["appearance", "environment-themes"],
        ["orchestration-tools", "environment-orchestration"],
        ["spec-catalog", "environment-spec-catalog"],
        ["cloud-storage", "environment-cloud-storage"],
      ]) {
        if (id === "cloud-storage")
          await click(
            page.getByRole("tab", { name: "Storage & policies" }),
            "Open storage and policy tools",
          );
        const view = await panel(id);
        await shot(name, view);
        if (id === "spec-catalog") {
          const filter = view
            .getByRole("group", { name: "Spec status" })
            .getByRole("button", { name: "partial", exact: true });
          await click(
            filter,
            "Filter the architecture catalog by implementation status",
          );
          await assert(filter).toHaveAttribute("aria-pressed", "true");
          await verify("Inspect partially implemented specifications", view);
        }
      }
    },
  );
  await scenario(
    "security-and-space-recovery",
    ["security-malware"],
    async () => {
      await route("system/security");
      const main = page.locator("main");
      await verify("Open the run security review", main, /malware|security/i);
      await click(
        page.getByRole("tab", { name: "Scan setup" }),
        "Open security scan controls",
      );
      await shot("security-malware", main, /scan/i);
      await route("system/space-recovery");
      await click(
        page.getByRole("tab", { name: "Recovery reports" }),
        "Inspect recovery reports",
      );
      const space = page
        .locator("main")
        .getByText(/hardlink|bloat/i)
        .first();
      await show(space);
      await verify("Inspect the space recovery plan controls", space);
    },
  );
  await scenario("spatial-studio-mix", ["spatial-studio"], async () => {
    await route("studio");
    const ready = button("Export stereo WAV");
    await assert(ready).toBeEnabled();
    const track = page.getByRole("slider", { name: "Trim in" });
    await verify("Open the editable room and its demo tracks", ready);
    await page.getByLabel("Import audio files").setInputFiles(audio);
    await assert(
      page.getByRole("heading", { name: "kick_120bpm_C.wav" }),
    ).toBeVisible();
    await track.focus();
    await page.keyboard.press("ArrowRight");
    await assert(track).toHaveValue("0.001");
    await verify("Trim the imported recording", track);
    await click(button("Solo", page), "Solo the imported track");
    await assert(page.locator(".studio-scene canvas")).toBeVisible({
      timeout: 60000,
    });
    await assert(page.locator(".studio-scene-message")).toHaveCount(0, {
      timeout: 90000,
    });
    await page
      .getByRole("heading", { name: "Spatial studio", exact: true })
      .first()
      .scrollIntoViewIfNeeded();
    await shot(
      "spatial-studio",
      page.getByRole("heading", { name: "Spatial studio" }),
    );
    const downloaded = page.waitForEvent("download");
    await click(ready, "Render the stereo WAV");
    const file = await downloaded;
    expect(file.suggestedFilename()).toMatch(/\.wav$/i);
    await verify("Receive the rendered stereo mix", page.locator("main"));
  });
  await scenario(
    "",
    [
      "duplicates-review",
      "scene-renames",
      "scan-audit",
      "skipped-files",
      "help-panel",
    ],
    async () => {
      for (const [path, name, match] of [
        ["review/duplicates", "duplicates-review", /keeper|duplicate/i],
        ["review/scene-renames", "scene-renames", /rename/i],
        ["review/scan-audit", "scan-audit", /identification|audit/i],
        ["review/skipped", "skipped-files", /skipped|failures/i],
        ["help", "help-panel", /Your first library scan/i],
      ]) {
        if (
          selected.size &&
          !selected.has("screenshots") &&
          !selected.has(name)
        )
          continue;
        await route(path);
        const main = page.locator("main");
        await assert(main).toContainText(match);
        const evidence = {
          "review/duplicates": /SynthOne Copy/i,
          "review/scene-renames": /VintageKeys/i,
          "review/scan-audit": /SynthOne/i,
          "review/skipped": /LockedPack|loose.zip|SynthOne/i,
        };
        if (path === "help") {
          await assert(
            main.getByRole("heading", { name: "Your first library scan" }),
          ).toBeVisible();
          expect(
            await main
              .locator("img[src*='/help/'], video[src*='/help/']")
              .count(),
          ).toBe(0);
        } else await assert(main).toContainText(evidence[path]);
        await shot(name, main, match);
      }
    },
  );
  await scenario(
    "restructure-live-staging",
    ["restructure-preview"],
    async () => {
      await route("review/restructure");
      const main = page.locator("main");
      await verify("Read the saved restructure plan", main, /SynthOne/);
      await click(button(/Section a \(/i, main), "Approve the fixture section");
      await click(
        button(/Dry.run approved sections/i, main),
        "Preview the approved move",
      );
      await assert(main).toContainText(/Dry run: 1 move|1 move.*preview/i);
      await shot("restructure-preview", main, /SynthOne/);
      await click(
        button(/Execute approved/i, main),
        "Review live move confirmation",
      );
      const confirmation = page.getByRole("dialog");
      const commit = button("Move approved sections", confirmation);
      await click(commit, "Apply the approved fixture move");
      await assert(main).toContainText(
        /Live: 1 move\(s\) applied \(0 failed\)/i,
      );
      await fs.access(
        join(lib, "a", "Acme Audio", "SynthOne", "kick_120bpm_C.wav"),
      );
      await verify("Verify the staged destination and result", main);
    },
  );
} finally {
  await browser.close();
}
for (const a of artifacts) {
  const paths =
    a.type === "screenshot"
      ? ["screenshots/" + a.name + ".png"]
      : ["videos/" + a.name + ".mp4", "gifs/" + a.name + ".gif"];
  a.files = {};
  for (const file of paths) {
    const bytes = await fs.readFile(join(output, file));
    a.files[file] = {
      sha256: createHash("sha256").update(bytes).digest("hex"),
      bytes: bytes.length,
    };
  }
}
await fs.writeFile(
  join(output, "capture-proof.json"),
  JSON.stringify({ viewport, artifacts }, null, 2) + "\n",
);
console.log("Recorded", artifacts.length, "documented states/workflows");
