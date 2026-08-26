import { describe, expect, it } from "vitest";
import {
  ALL_TAB_PATHS,
  DEFAULT_TAB,
  TAB_TO_PATH,
  pathForTab,
  tabForPath,
} from "./routes";
import type { TabId } from "./types";

const ALL_TABS: TabId[] = [
  "dashboard",
  "scan",
  "investigation",
  "duplicates",
  "restructure",
  "archives",
  "scene-renames",
  "scan-audit",
  "skipped",
  "space-recovery",
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
