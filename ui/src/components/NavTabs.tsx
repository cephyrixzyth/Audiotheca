import { useFileExplorer } from "../contexts/FileExplorerContext";
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

const TAB_BY_ID = new Map(ALL_TABS.map((t) => [t.id, t]));

function tabDef(id: TabId): TabDef {
  return TAB_BY_ID.get(id)!;
}

interface Props {
  tab: TabId;
  onTabChange: (id: TabId) => void;
  scanActive: boolean;
}

export function NavTabs({ tab, onTabChange, scanActive }: Props) {
  const { openAtRoots } = useFileExplorer();
  const inReview = REVIEW_TAB_IDS.includes(tab);
  const inSystem = SYSTEM_TAB_IDS.includes(tab);

  function scanTitle(def: TabDef): string {
    return def.id === "scan" && scanActive ? `${def.title} — scan in progress` : def.title;
  }

  return (
    <div className="nav-tabs">
      <nav className="top-tabs top-tabs-primary" aria-label="Main sections">
        <button
          type="button"
          className={`top-tab ${tab === "dashboard" ? "active" : ""}`}
          title={tabDef("dashboard").title}
          onClick={() => onTabChange("dashboard")}
        >
          Dashboard
        </button>
        <button
          type="button"
          className={`top-tab ${tab === "scan" ? "active" : ""}`}
          title={scanTitle(tabDef("scan"))}
          onClick={() => onTabChange("scan")}
        >
          Scan
          {scanActive && <span className="scan-live-dot" aria-label="Scan running" />}
        </button>
        <button
          type="button"
          className={`top-tab ${inReview ? "active" : ""}`}
          title="Review scan results — investigation, duplicates, restructure, and more"
          onClick={() => onTabChange(inReview ? tab : "investigation")}
        >
          Review
        </button>
        <button
          type="button"
          className="top-tab top-tab-library"
          title="Open library explorer at configured roots"
          onClick={openAtRoots}
        >
          Library
        </button>
        <button
          type="button"
          className={`top-tab ${inSystem ? "active" : ""}`}
          title="System tools — space recovery, security, environment, vendors"
          onClick={() => onTabChange(inSystem ? tab : "space-recovery")}
        >
          System
        </button>
        <button
          type="button"
          className={`top-tab ${tab === "help" ? "active" : ""}`}
          title={tabDef("help").title}
          onClick={() => onTabChange("help")}
        >
          Help
        </button>
      </nav>

      {inReview && (
        <nav className="top-tabs top-tabs-secondary" aria-label="Review sections">
          {REVIEW_TAB_IDS.map((id) => {
            const def = tabDef(id);
            return (
              <button
                key={id}
                type="button"
                className={`top-tab top-tab-sub ${tab === id ? "active" : ""}`}
                title={def.title}
                onClick={() => onTabChange(id)}
              >
                {def.label}
              </button>
            );
          })}
        </nav>
      )}

      {inSystem && (
        <nav className="top-tabs top-tabs-secondary" aria-label="System sections">
          {SYSTEM_TAB_IDS.map((id) => {
            const def = tabDef(id);
            return (
              <button
                key={id}
                type="button"
                className={`top-tab top-tab-sub ${tab === id ? "active" : ""}`}
                title={def.title}
                onClick={() => onTabChange(id)}
              >
                {def.label}
              </button>
            );
          })}
        </nav>
      )}
    </div>
  );
}
