import { Tabs } from "../ui";
import { useFileExplorer } from "../contexts/FileExplorerContext";
import type { TabId } from "../types";
import {
  REVIEW_TAB_IDS,
  SYSTEM_TAB_IDS,
  asReviewTabId,
  asSystemTabId,
  primaryNavId,
  tabDef,
  tabForPrimaryNav,
  type PrimaryNavId,
} from "../utils/navTabs";

export type { TabDef } from "../utils/navTabs";
export { ALL_TABS, REVIEW_TAB_IDS, SYSTEM_TAB_IDS } from "../utils/navTabs";

interface Props {
  tab: TabId;
  onTabChange: (id: TabId) => void;
  scanActive: boolean;
}

function isPrimaryNavId(value: string): value is PrimaryNavId {
  switch (value) {
    case "dashboard":
    case "scan":
    case "review":
    case "system":
    case "help":
      return true;
    default:
      return false;
  }
}

export function NavTabs({ tab, onTabChange, scanActive }: Props) {
  const { openAtRoots } = useFileExplorer();
  const inReview = REVIEW_TAB_IDS.includes(tab);
  const inSystem = SYSTEM_TAB_IDS.includes(tab);
  const scanDef = tabDef("scan");

  function onPrimaryChange(value: string) {
    if (value === "library") {
      openAtRoots();
      return;
    }
    if (!isPrimaryNavId(value)) return;
    onTabChange(tabForPrimaryNav(value, tab));
  }

  return (
    <div className="nav-tabs">
      <Tabs
        aria-label="Main sections"
        rootClassName="top-tabs-primary"
        listClassName="top-tabs"
        triggerClassName="top-tab"
        value={primaryNavId(tab)}
        onValueChange={onPrimaryChange}
        items={[
          { value: "dashboard", label: "Dashboard", title: tabDef("dashboard").title },
          {
            value: "scan",
            title: scanActive ? `${scanDef.title} — scan in progress` : scanDef.title,
            label: (
              <>
                Scan
                {scanActive && <span className="scan-live-dot" aria-label="Scan running" />}
              </>
            ),
          },
          {
            value: "review",
            label: "Review",
            title: "Review scan results — investigation, duplicates, restructure, and more",
          },
          {
            value: "library",
            label: "Library",
            title: "Open library explorer at configured roots",
            className: "top-tab-library",
          },
          {
            value: "system",
            label: "System",
            title: "System tools — space recovery, security, environment, vendors",
          },
          { value: "help", label: "Help", title: tabDef("help").title },
        ]}
      />

      {inReview && (
        <Tabs
          aria-label="Review sections"
          listClassName="top-tabs top-tabs-secondary"
          triggerClassName="top-tab top-tab-sub"
          value={tab}
          onValueChange={(id) => {
            const next = asReviewTabId(id);
            if (next) onTabChange(next);
          }}
          items={REVIEW_TAB_IDS.map((id) => {
            const def = tabDef(id);
            return { value: id, label: def.label, title: def.title };
          })}
        />
      )}

      {inSystem && (
        <Tabs
          aria-label="System sections"
          listClassName="top-tabs top-tabs-secondary"
          triggerClassName="top-tab top-tab-sub"
          value={tab}
          onValueChange={(id) => {
            const next = asSystemTabId(id);
            if (next) onTabChange(next);
          }}
          items={SYSTEM_TAB_IDS.map((id) => {
            const def = tabDef(id);
            return { value: id, label: def.label, title: def.title };
          })}
        />
      )}
    </div>
  );
}
