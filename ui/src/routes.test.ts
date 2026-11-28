import { describe, expect, it } from "vitest";
import {
  ALL_TAB_PATHS,
  DEFAULT_TAB,
  TAB_TO_PATH,
  pathForTab,
  readRunParam,
  setRunParam,
  tabForPath,
} from "./routes";
import type { TabId } from "./types";

const ALL_TABS: TabId[] = [
  "dashboard",
  "studio",
  "library",
  "scan",
  "investigation",
  "duplicates",
  "restructure",
  "archives",
  "scene-renames",
  "deep-identify",
  "scan-audit",
  "skipped",
  "space-recovery",
  "plugins",
  "automation",
  "security",
  "environment",
  "vendors",
  "help",
];

describe("routes", () => {
  it("maps every TabId to a unique path", () => {
    const paths = ALL_TABS.map((t) => TAB_TO_PATH[t]);
    expect(new Set(paths).size).toBe(ALL_TABS.length);
    for (const p of paths) expect(p.startsWith("/")).toBe(true);
  });

  it("round-trips tab -> path -> tab for all tabs", () => {
    for (const tab of ALL_TABS) {
      expect(tabForPath(pathForTab(tab))).toBe(tab);
    }
  });

  it("tolerates a trailing slash", () => {
    expect(tabForPath("/review/duplicates/")).toBe("duplicates");
  });

  it("falls back to the default tab for unknown paths", () => {
    expect(tabForPath("/")).toBe(DEFAULT_TAB);
    expect(tabForPath("/nope")).toBe(DEFAULT_TAB);
  });

  it("exposes all paths for smoke coverage", () => {
    expect(ALL_TAB_PATHS).toHaveLength(ALL_TABS.length);
  });
});

describe("run param", () => {
  it("reads the run stamp from search", () => {
    expect(readRunParam("?run=20260704_1600")).toBe("20260704_1600");
    expect(readRunParam("")).toBe("");
    expect(readRunParam("?x=1")).toBe("");
  });

  it("sets the run stamp preserving other params", () => {
    expect(setRunParam("", "abc")).toBe("?run=abc");
    expect(setRunParam("?x=1", "abc")).toContain("run=abc");
    expect(setRunParam("?x=1", "abc")).toContain("x=1");
  });

  it("removes the run stamp when empty", () => {
    expect(setRunParam("?run=abc", "")).toBe("");
    expect(setRunParam("?run=abc&x=1", "")).toBe("?x=1");
  });

  it("round-trips through read/set", () => {
    expect(readRunParam(setRunParam("", "stamp-1"))).toBe("stamp-1");
  });
});
