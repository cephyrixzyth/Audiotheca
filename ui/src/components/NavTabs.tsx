import type { TabId } from "../types";
import { Tabs } from "../ui";
import { WorkspaceIcon } from "../ui/WorkspaceIcon";
import { REVIEW_TAB_IDS, SYSTEM_TAB_IDS, primaryNavId, tabDef, tabForPrimaryNav, type PrimaryNavId } from "../utils/navTabs";

export type { TabDef } from "../utils/navTabs";
export { ALL_TABS, REVIEW_TAB_IDS, SYSTEM_TAB_IDS } from "../utils/navTabs";

const sections: Array<{ id: PrimaryNavId; label: string }> = [
  { id: "dashboard", label: "Dashboard" }, { id: "library", label: "Library" },
  { id: "scan", label: "Scan" }, { id: "review", label: "Review" },
  { id: "studio", label: "Studio" }, { id: "system", label: "System" }, { id: "help", label: "Help" },
];

interface Props { tab: TabId; onTabChange: (id: TabId) => void; scanActive?: boolean }

export function NavTabs({ tab, onTabChange, scanActive }: Props) {
  return <Tabs aria-label="Main sections" orientation="vertical" rootClassName="primary-directory" listClassName="directory-list"
    triggerClassName="directory-link" value={primaryNavId(tab)}
    onValueChange={value => {
      const section = sections.find(item => item.id === value);
      if (section) onTabChange(tabForPrimaryNav(section.id, tab));
    }}
    items={sections.map(({ id, label }) => ({
      value: id, label: <><WorkspaceIcon name={id} /><span>{label}</span>{id === "scan" && scanActive && <i className="scan-live-dot" aria-label="Scan running" />}</>,
    }))} />;
}

export function SectionTabs({ tab, onTabChange }: Props) {
  const family = primaryNavId(tab);
  const ids = family === "review" ? REVIEW_TAB_IDS : family === "system" ? SYSTEM_TAB_IDS : [];
  if (!ids.length) return null;
  return <Tabs aria-label={family === "review" ? "Review sections" : "System sections"} listClassName="workspace-sections"
    triggerClassName="workspace-section" value={tab}
    onValueChange={value => { const next = ids.find(id => id === value); if (next) onTabChange(next); }}
    items={ids.map(id => ({ value: id, label: tabDef(id).label, title: tabDef(id).title }))} />;
}
