import type { TabId } from "../types";

const MESSAGES: Partial<Record<TabId, { title: string; body: string }>> = {
  dashboard: {
    title: "No scan reports yet",
    body: "Run a dry-run scan to populate KPIs, or use the panels below for host metrics and environment status.",
  },
  investigation: {
    title: "No investigation data",
    body: "Complete a scan to review items the engine could not confidently route.",
  },
  duplicates: {
    title: "No duplicate review data",
    body: "Run a scan to load suspected duplicate groups.",
  },
  restructure: {
    title: "No restructure plan",
    body: "Run a scan with restructure enabled to preview vendor folder moves.",
  },
  archives: {
    title: "No archive peek results",
    body: "Run a scan with archive peek enabled to compare archives and extracted folders.",
  },
  "scene-renames": {
    title: "No scene rename plan",
    body: "Run a scan to stage scene-hash folder rename candidates.",
  },
  "scan-audit": {
    title: "No scan audit rows",
    body: "Run a scan to populate per-item audit and correction tools.",
  },
  skipped: {
    title: "No skipped-file report",
    body: "Run a scan to list failures, truncations, and rescan targets.",
  },
  "space-recovery": {
    title: "No space recovery summary",
    body: "Run a scan to analyze hardlink dedup and bloat recovery options.",
  },
};

interface Props {
  tab: TabId;
  onStartScan?: () => void;
}

export function TabEmptyState({ tab, onStartScan }: Props) {
  const msg = MESSAGES[tab] ?? {
    title: "No run data",
    body: "Select a run from the toolbar or start a new scan.",
  };

  return (
    <div className="tab-empty-state">
      <h3>{msg.title}</h3>
      <p className="count-muted">{msg.body}</p>
      {onStartScan && (
        <button type="button" className="primary-btn" onClick={onStartScan}>
          Open Scan tab
        </button>
      )}
    </div>
  );

}
