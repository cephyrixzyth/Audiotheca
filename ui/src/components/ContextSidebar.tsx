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
import { LabeledSelect } from "../ui";

export interface SidebarFilterDef {
  key: string;
  label: string;
  title?: string;
  options: { value: string; label: string }[];
}

interface DuplicateQueue {
  query: string;
  confidence: string;
  offset: number;
  hideRejected: boolean;
  showReferenceExtras: boolean;
}

const defaultQueue: DuplicateQueue = {
  query: "", confidence: "HIGH", offset: 0, hideRejected: true, showReferenceExtras: false,
};

function readQueue(stamp: string): DuplicateQueue {
  try {
    const value = JSON.parse(localStorage.getItem(`audiotheca.duplicateQueue.${stamp}`) ?? "null");
    if (!value) return defaultQueue;
    return {
      query: typeof value.query === "string" ? value.query : "",
      confidence: ["", "HIGH", "MEDIUM", "LOW"].includes(value.confidence) ? value.confidence : "HIGH",
      offset: Number.isSafeInteger(value.offset) && value.offset >= 0 && value.offset % 100 === 0 ? value.offset : 0,
      hideRejected: value.hideRejected !== false,
      showReferenceExtras: value.showReferenceExtras === true,
    };
  } catch {
    return defaultQueue;
  }
}

interface ContextSidebarState {
  queue: DuplicateQueue;
  updateQueue: (patch: Partial<DuplicateQueue>) => void;
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
  stamp,
  children,
}: {
  tab: TabId;
  stamp: string;
  children: ReactNode;
}) {
  const [plainQuery, setPlainQuery] = useState("");
  const saved = useMemo(() => readQueue(stamp), [stamp]);
  const [edited, setEdited] = useState<{ stamp: string; queue: DuplicateQueue } | null>(null);
  const queue = edited?.stamp === stamp ? edited.queue : saved;

  useEffect(() => {
    if (!edited?.stamp) return;
    try {
      localStorage.setItem(`audiotheca.duplicateQueue.${edited.stamp}`, JSON.stringify(edited.queue));
    } catch {
      // The queue remains usable when persistent browser storage is unavailable.
    }
  }, [edited]);

  const updateQueue = useCallback((patch: Partial<DuplicateQueue>) => {
    setEdited(previous => ({
      stamp, queue: { ...(previous?.stamp === stamp ? previous.queue : saved), ...patch },
    }));
  }, [stamp, saved]);

  const query = tab === "duplicates" ? queue.query : plainQuery;
  const setQuery = useCallback((next: string) => {
    if (tab === "duplicates") updateQueue({ query: next, offset: 0 });
    else setPlainQuery(next);
  }, [tab, updateQueue]);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [filterDefs, setFilterDefs] = useState<SidebarFilterDef[]>([]);

  useEffect(() => {
    setPlainQuery("");
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
    () => ({ query, setQuery, tab, filters, setFilter, registerFilters, queue, updateQueue }),
    [query, setQuery, tab, filters, setFilter, registerFilters, queue, updateQueue],
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
  "deep-identify",
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
  "deep-identify": "Filter recoveries by item, vendor, method, or evidence.",
  "space-recovery": "Use Space Recovery panel filters.",
  plugins: "Use the Plugin Ledger filters.",
  automation: "Automation uses in-panel controls.",
};

export function ContextSidebar() {
  const { query, setQuery, tab, filters, setFilter } = useContextSidebar();
  const filterDefs = useContext(SidebarDefsCtx);
  if (!SEARCH_TABS.has(tab) && !filterDefs.length) return null;
  return (
    <section className="context-sidebar filter-line" aria-label="View filters">
      {SEARCH_TABS.has(tab) && (
        <div className="context-field">
          <label className="context-field" htmlFor="context-sidebar-search">
            <span className="context-label">Search</span>
            <input
              id="context-sidebar-search"
              type="search"
              className="field-input"
              placeholder="Filter this view…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              title={TAB_HINTS[tab] ?? "Context search for the active tab"}
            />
          </label>
        </div>
      )}

      {filterDefs.length > 0 && (
        <div className="context-sidebar-section">
          <span className="context-label">Filters</span>
          {filterDefs.map((def) => (
            <LabeledSelect
              key={def.key}
              className="field-input"
              wrapperClassName="context-field"
              labelClassName="context-label"
              label={def.label}
              labelTitle={def.title ?? def.label}
              value={filters[def.key] ?? ""}
              title={def.title ?? def.label}
              onChange={(e) => setFilter(def.key, e.target.value)}
            >
              {def.options.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </LabeledSelect>
          ))}
        </div>
      )}

    </section>
  );
}
