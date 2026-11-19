import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavTabs } from "./NavTabs";
import { ThemeSwitcher } from "./ThemeSwitcher";
import { OPEN_COMMAND_PALETTE_EVENT } from "./CommandPalette";
import { WorkspaceIcon } from "../ui/WorkspaceIcon";
import { useFileExplorer } from "../contexts/FileExplorerContext";
import { primaryNavId, tabDef } from "../utils/navTabs";
import type { TabId } from "../types";

export const pageTitles: Partial<Record<TabId, string>> = {
  dashboard: "Library workspace", library: "Sound library", scan: "Scan library", studio: "Spatial studio",
  investigation: "Investigation inbox", duplicates: "Duplicate review", restructure: "Restructure plan",
  archives: "Archive review", "scene-renames": "Scene renames", "deep-identify": "Deep identification",
  "scan-audit": "Scan audit", skipped: "Skipped files", "space-recovery": "Space recovery", security: "Security",
  environment: "Environment", vendors: "Vendor research", help: "Field guide",
};
const familyNames = { dashboard: "Workspace", scan: "Workspace", library: "Workspace", studio: "Production", review: "Review", system: "System", help: "Reference" };

interface Props { tab: TabId; onTabChange: (tab: TabId) => void; scanActive: boolean; version: string; root: string; children: ReactNode }

export function WorkspaceFrame({ tab, onTabChange, scanActive, version, root, children }: Props) {
  const [menu, setMenu] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const rail = useRef<HTMLElement>(null);
  const commandKey = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl";
  const { openAtRoots } = useFileExplorer();
  useEffect(() => {
    if (!menu) return;
    rail.current?.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]')?.focus();
    const size = window.matchMedia("(min-width: 761px)");
    const resized = () => { if (size.matches) setMenu(false); };
    size.addEventListener("change", resized);
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") { setMenu(false); trigger.current?.focus(); } };
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("keydown", close);
      size.removeEventListener("change", resized);
    };
  }, [menu]);
  useEffect(() => { setMenu(false); window.scrollTo(0, 0); }, [tab]);
  const family = familyNames[primaryNavId(tab)];
  const rootName = root.split(/[/\\]/).filter(Boolean).pop();
  return <div className={"app-shell workspace-shell" + (menu ? " menu-open" : "")}>
    <a className="skip-link" href="#workspace-content" onClick={event => {event.preventDefault(); document.querySelector<HTMLElement>("main.main")?.focus();}}>Skip to content</a>
    <aside ref={rail} className="workspace-rail" aria-label="Workspace navigation" id="workspace-navigation">
      <div className="rail-identity"><img src={import.meta.env.BASE_URL + "logo.png"} alt="" /><h1>Audiotheca</h1></div>
      <div className="rail-directory"><NavTabs tab={tab} scanActive={scanActive} onTabChange={id => { setMenu(false); onTabChange(id); }} /></div>
      <div className="rail-bottom">
        <button className="mounted-library" title={root || "Browse configured library roots"} aria-label="Browse library roots" onClick={() => { setMenu(false); openAtRoots(); }}>
          <WorkspaceIcon name="drive" /><span><small>Library root</small><strong>{rootName || "Browse roots"}</strong></span><WorkspaceIcon name="chevron" size={14}/></button>
        <span className="workspace-version">{version}</span>
      </div>
    </aside>
    {menu && <button aria-label="Close navigation" className="rail-scrim" onClick={() => { setMenu(false); requestAnimationFrame(() => trigger.current?.focus()); }} />}
    <div className="workspace-main-column" inert={menu}>
      <header className="topbar workspace-topbar">
        <button ref={trigger} className="mobile-menu" aria-label={menu ? "Close workspace menu" : "Open workspace menu"} aria-expanded={menu} aria-controls="workspace-navigation" onClick={() => setMenu(value => !value)}><WorkspaceIcon name={menu ? "close" : "route"} /></button>
        <span className="workspace-breadcrumb"><span>{family}</span><WorkspaceIcon name="chevron" size={13}/><strong>{tabDef(tab).label}</strong></span>
        <div className="topbar-tools"><button className="workspace-search" aria-label={`Search ${commandKey}K`} onClick={() => window.dispatchEvent(new Event(OPEN_COMMAND_PALETTE_EVENT))}><WorkspaceIcon name="search" size={16}/><span>Search commands</span><kbd>{commandKey} K</kbd></button><ThemeSwitcher /></div>
      </header>
      {children}
    </div>
  </div>;
}
