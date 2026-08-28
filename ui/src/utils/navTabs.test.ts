import { describe, expect, it } from "vitest";
import type { TabId } from "../types";
import {
  ALL_TABS,
  REVIEW_TAB_IDS,
  SYSTEM_TAB_IDS,
  asReviewTabId,
  asSystemTabId,
  primaryNavId,
  tabForPrimaryNav,
  type PrimaryNavId,
} from "./navTabs";

const ALL_TAB_IDS: TabId[] = [
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

describe("primaryNavId", () => {
  it("maps every TabId onto a primary chrome id", () => {
    const ids = ALL_TAB_IDS.map((tab) => primaryNavId(tab));
    expect(new Set(ids)).toEqual(new Set<PrimaryNavId>(["dashboard", "scan", "review", "system", "help"]));
    for (const tab of ALL_TAB_IDS) {
      expect(ALL_TABS.some((def) => def.id === tab)).toBe(true);
    }
  });

  it("groups review and system sub-tabs", () => {
    for (const id of REVIEW_TAB_IDS) expect(primaryNavId(id)).toBe("review");
    for (const id of SYSTEM_TAB_IDS) expect(primaryNavId(id)).toBe("system");
    expect(primaryNavId("dashboard")).toBe("dashboard");
    expect(primaryNavId("scan")).toBe("scan");
    expect(primaryNavId("help")).toBe("help");
  });
});

describe("tabForPrimaryNav", () => {
  it("keeps the current review sub-tab when Review is already active", () => {
    expect(tabForPrimaryNav("review", "duplicates")).toBe("duplicates");
  });

  it("opens Investigation when entering Review from elsewhere", () => {
    expect(tabForPrimaryNav("review", "dashboard")).toBe("investigation");
  });

  it("keeps the current system sub-tab when System is already active", () => {
    expect(tabForPrimaryNav("system", "vendors")).toBe("vendors");
  });

  it("opens Space recovery when entering System from elsewhere", () => {
    expect(tabForPrimaryNav("system", "scan")).toBe("space-recovery");
  });

  it("parses review and system sub-tab ids", () => {
    expect(asReviewTabId("duplicates")).toBe("duplicates");
    expect(asReviewTabId("dashboard")).toBeNull();
    expect(asSystemTabId("vendors")).toBe("vendors");
    expect(asSystemTabId("scan")).toBeNull();
  });

  it("routes leaf primary ids to themselves", () => {
    expect(tabForPrimaryNav("dashboard", "help")).toBe("dashboard");
    expect(tabForPrimaryNav("scan", "help")).toBe("scan");
    expect(tabForPrimaryNav("help", "scan")).toBe("help");
  });
});
