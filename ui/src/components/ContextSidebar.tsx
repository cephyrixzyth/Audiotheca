import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { TabId } from "../types";

export interface SidebarFilterDef {
  key: string;
  label: string;
  title?: string;
  options: { value: string; label: string }[];
}

interface ContextSidebarState {
  query: string;
  setQuery: (q: string) => void;
  tab: TabId;
  filters: Record<string, string>;
  setFilter: (key: string, value: string) => void;
  registerFilters: (defs: SidebarFilterDef[]) => void;
}

const ContextSidebarCtx = createContext<ContextSidebarState | null>(null);

export function ContextSidebarProvider({
  tab,
  children,
}: {
  tab: TabId;
  children: ReactNode;
}) {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [filterDefs, setFilterDefs] = useState<SidebarFilterDef[]>([]);

  useEffect(() => {
    setQuery("");
    setFilters({});
    setFilterDefs([]);
  }, [tab]);

  const setFilter = useCallback((key: string, value: string) => {
    setFilters((prev) => (prev[key] === value ? prev : { ...prev, [key]: value }));
  }, []);

  const registerFilters = useCallback((defs: SidebarFilterDef[]) => {
    setFilterDefs((prev) => {
      if (
        prev.length === defs.length &&
        prev.every((d, i) => JSON.stringify(d) === JSON.stringify(defs[i]))
      ) {
        return prev;
      }
      return defs;
    });
  }, []);

  const value = useMemo(
    () => ({ query, setQuery, tab, filters, setFilter, registerFilters }),
    [query, tab, filters, setFilter, registerFilters],
  );
  return (
    <ContextSidebarCtx.Provider value={value}>
      <SidebarDefsCtx.Provider value={filterDefs}>{children}</SidebarDefsCtx.Provider>
    </ContextSidebarCtx.Provider>
  );
}

const SidebarDefsCtx = createContext<SidebarFilterDef[]>([]);

export function useContextSidebar() {
  const ctx = useContext(ContextSidebarCtx);
  if (!ctx) throw new Error("useContextSidebar requires ContextSidebarProvider");
  return ctx;
}

/** Publish filter dropdowns for the active tab into the left sidebar. */
export function useSidebarFilters(defs: SidebarFilterDef[]) {
  const { filters, setFilter, registerFilters } = useContextSidebar();
  useEffect(() => {
    registerFilters(defs);
  }, [registerFilters, defs]);
  return { filters, setFilter };
}

const SEARCH_TABS = new Set<TabId>([
  "scan",
  "investigation",
  "duplicates",
  "restructure",
  "archives",
  "scan-audit",
  "skipped",
  "security",
  "scene-renames",
]);

const TAB_HINTS: Partial<Record<TabId, string>> = {
  scan: "Filter progress log lines (phase names, paths, errors).",
  investigation: "Search items and groups by name, path, bucket, or reason.",
  duplicates: "Filter duplicate groups by product name or path.",
  restructure: "Filter routes by vendor, path, or destination.",
  archives: "Filter archive peek rows by name or path.",
  "scan-audit": "Search audit rows by vendor, path, or fingerprint.",
  skipped: "Search skipped paths and failure reasons.",
  security: "Filter findings by file name or path (after scan).",
  environment: "Environment tab uses in-panel controls — no sidebar search.",
  help: "Browse built-in guides for install, deploy, and daily use.",
  dashboard: "Search not available on Dashboard — use tab filters on data views.",
  vendors: "Use in-panel vendor tools — sidebar search not used here.",
  "scene-renames": "Filter by scene ID, proposed name, or source path.",
  "space-recovery": "Use Space Recovery panel filters.",
};

export function ContextSidebar({ stamp }: { stamp?: string }) {
  const { query, setQuery, tab, filters, setFilter } = useContextSidebar();
  const filterDefs = useContext(SidebarDefsCtx);

  return (
    <aside className="context-sidebar">
      <div className="context-sidebar-brand">
        <strong>Audiotheca</strong>
        <span className="count-muted">Library dedupe &amp; routing</span>
      </div>

      {SEARCH_TABS.has(tab) && (
        <label className="context-field">
          <span className="context-label">Search</span>
          <input
            type="search"
            className="field-input"
            placeholder="Filter this view…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            title={TAB_HINTS[tab] ?? "Context search for the active tab"}
          />
        </label>
      )}

      {!SEARCH_TABS.has(tab) && TAB_HINTS[tab] && (
        <p className="count-muted context-search-hint">{TAB_HINTS[tab]}</p>
      )}

      {filterDefs.length > 0 && (
        <div className="context-sidebar-section">
          <span className="context-label">Filters</span>
          {filterDefs.map((def) => (
            <label key={def.key} className="context-field">
              <span className="context-label">{def.label}</span>
              <select
                className="field-input"
                value={filters[def.key] ?? ""}
                title={def.title ?? def.label}
                onChange={(e) => setFilter(def.key, e.target.value)}
              >
                {def.options.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}

      {stamp && tab !== "scan" && (
        <label className="context-field">
          <span className="context-label">Active run</span>
          <input type="text" className="field-input" value={stamp} readOnly title="Selected report stamp" />
        </label>
      )}

      {filterDefs.length === 0 && (
        <div className="context-sidebar-section">
          <span className="context-label">Filters</span>
          <p className="count-muted context-placeholder">
            {TAB_HINTS[tab] ?? "Tab-specific filters and quick actions will appear here."}
          </p>
        </div>
      )}
    </aside>
  );
}
