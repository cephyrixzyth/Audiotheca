import type { TabId } from "../types";

export interface TabDef {
  id: TabId;
  label: string;
  title: string;
}

export const ALL_TABS: TabDef[] = [
  { id: "dashboard", label: "Dashboard", title: "Run KPIs, trends, and quick links to other tabs" },
  { id: "scan", label: "Scan", title: "Start scans, configure pipeline phases, and watch live progress" },
  { id: "investigation", label: "Investigation", title: "Items the engine could not confidently route — set vendor or bucket" },
  { id: "duplicates", label: "Duplicates", title: "Review suspected duplicate products and pick keepers" },
  { id: "restructure", label: "Restructure", title: "Planned vendor folder moves — edit destinations before live run" },
  { id: "archives", label: "Archives", title: "Archive vs extracted-folder pairs — confirm redundant archives" },
  { id: "scene-renames", label: "Scene renames", title: "Approve renaming scene-hash folders to product names" },
  { id: "scan-audit", label: "Scan audit", title: "Per-item scan status, ID method, and quick corrections" },
  { id: "skipped", label: "Skipped", title: "Failures, loose archives, cache hits, and rescan targets" },
  { id: "space-recovery", label: "Space recovery", title: "Hardlink dedup and bloat detection plans" },
  { id: "security", label: "Security", title: "Malware heuristics, quarantine, hash lookup" },
  { id: "environment", label: "Environment", title: "Toolchain health, repairs, manifest backup" },
  { id: "vendors", label: "Vendors", title: "Add vendor keywords, harvest gaps, and export feedback" },
  { id: "help", label: "Help", title: "Install, deploy, workflow, and layout guides" },
];

export const REVIEW_TAB_IDS: TabId[] = [
  "investigation",
  "duplicates",
  "restructure",
  "archives",
  "scene-renames",
  "scan-audit",
  "skipped",
];

export const SYSTEM_TAB_IDS: TabId[] = ["space-recovery", "security", "environment", "vendors"];

export type PrimaryNavId = "dashboard" | "scan" | "review" | "system" | "help";

const TAB_BY_ID = new Map(ALL_TABS.map((t) => [t.id, t]));

export function tabDef(id: TabId): TabDef {
  const def = TAB_BY_ID.get(id);
  if (!def) {
    throw new Error(`Unknown tab id: ${id}`);
  }
  return def;
}

export function primaryNavId(tab: TabId): PrimaryNavId {
  switch (tab) {
    case "dashboard":
      return "dashboard";
    case "scan":
      return "scan";
    case "help":
      return "help";
    case "investigation":
    case "duplicates":
    case "restructure":
    case "archives":
    case "scene-renames":
    case "scan-audit":
    case "skipped":
      return "review";
    case "space-recovery":
    case "security":
    case "environment":
    case "vendors":
      return "system";
    default: {
      const _exhaustive: never = tab;
      return _exhaustive;
    }
  }
}

export function asReviewTabId(value: string): TabId | null {
  return REVIEW_TAB_IDS.find((id) => id === value) ?? null;
}

export function asSystemTabId(value: string): TabId | null {
  return SYSTEM_TAB_IDS.find((id) => id === value) ?? null;
}

/** Map a primary chrome click to the route tab, keeping the current sub-tab when already in that group. */
export function tabForPrimaryNav(primary: PrimaryNavId, current: TabId): TabId {
  switch (primary) {
    case "dashboard":
    case "scan":
    case "help":
      return primary;
    case "review":
      return REVIEW_TAB_IDS.includes(current) ? current : "investigation";
    case "system":
      return SYSTEM_TAB_IDS.includes(current) ? current : "space-recovery";
    default: {
      const _exhaustive: never = primary;
      return _exhaustive;
    }
  }
}
