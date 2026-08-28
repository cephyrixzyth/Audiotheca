import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  browseDirectoryEnriched,
  browseSearch,
  fetchBrowseFacets,
  fetchPeHints,
  listArchiveContents,
  lookupAcoustId,
  openInExplorer,
  type BrowseEntry,
} from "../api/client";
import { useExplorerPathDrag } from "../contexts/FileExplorerContext";
import { Badge, Button, DropdownMenu, VirtualTable, type DropdownItem, type VirtualRowAttrs } from "../ui";
import { formatAcoustIdResult } from "../utils/acoustId";
import { isPeBinaryFile } from "../utils/peName";
import { AudioPreviewStrip, isAuditionableFile } from "./AudioPreviewStrip";
import { FileExplorerTree } from "./FileExplorerTree";
import { ArchiveDiffWizard } from "./ArchiveDiffWizard";
import { DropZoneOverlay } from "./DropZoneOverlay";

const ARCHIVE_EXT = /\.(zip|rar|7z|iso|tar(\.(gz|bz2|xz))?|gz|001)$/i;
const LAST_PATH_KEY = "audiotheca.explorer.lastPath";

function isArchiveName(name: string): boolean {
  const lower = name.toLowerCase();
  if (/\.tar\.(gz|bz2|xz)$/.test(lower)) return true;
  return ARCHIVE_EXT.test(name);
}

function formatSize(size: number | null | undefined): string {
  if (size == null) return "—";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  return `${(size / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function FacetStrip({
  label,
  options,
  selected,
  onSelect,
}: {
  label: string;
  options: Array<{ value: string; count: number }>;
  selected: string;
  onSelect: (value: string) => void;
}) {
  if (!options.length) return null;
  return (
    <div className="explorer-facet-strip" aria-label={label}>
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          className={`bucket-chip ${selected === opt.value ? "active" : ""}`.trim()}
          aria-pressed={selected === opt.value}
          onClick={() => onSelect(opt.value === selected ? "" : opt.value)}
          title={`${opt.count} files`}
        >
          {opt.value} ({opt.count})
        </button>
      ))}
    </div>
  );
}

function saveLastPath(path: string): void {
  try {
    sessionStorage.setItem(LAST_PATH_KEY, path);
  } catch {
    /* ignore */
  }
}

function pathSegments(fullPath: string): { label: string; path: string }[] {
  if (!fullPath) return [];
  const sep = fullPath.includes("\\") ? "\\" : "/";
  const parts = fullPath.split(/[/\\]/).filter(Boolean);
  const crumbs: { label: string; path: string }[] = [];
  let acc = "";
  for (let i = 0; i < parts.length; i += 1) {
    const part = parts[i];
    if (i === 0 && /^[a-zA-Z]:/.test(part)) {
      acc = part.endsWith(":") || part.endsWith(":\\") ? part : `${part}${sep}`;
      if (!acc.endsWith(sep) && /^[a-zA-Z]:$/.test(part)) acc = `${part}${sep}`;
    } else {
      acc = acc ? `${acc}${sep}${part}` : part;
    }
    crumbs.push({ label: part.replace(/\\$/, ""), path: acc });
  }
  return crumbs;
}

function isUnderSubtree(path: string, subtreeRoot: string | null): boolean {
  if (!subtreeRoot?.trim()) return true;
  const norm = (p: string) => p.replace(/\\/g, "/").toLowerCase().replace(/\/+$/, "");
  const child = norm(path);
  const root = norm(subtreeRoot);
  return child === root || child.startsWith(`${root}/`);
}

type PeHintPayload = {
  ok?: boolean;
  error?: string;
  engine?: string;
  path?: string;
  severity?: string;
  capabilities?: Array<{ id: string; severity: string; description: string }>;
};

function PeHintBanner({ result, busy }: { result: PeHintPayload | null; busy: boolean }) {
  if (busy) return <p className="count-muted">PE capability hints…</p>;
  if (!result) return null;
  const caps = result.capabilities ?? [];
  return (
    <div className="banner dry explorer-pe-hint" style={{ marginTop: "0.75rem" }}>
      <strong>PE capability hints</strong>
      {result.error ? <p className="count-muted">{result.error}</p> : null}
      {result.engine && !result.error ? <p className="count-muted">Engine: {result.engine}</p> : null}
      {!result.error && (
        <div className="pe-cap-cell">
          {caps.length === 0
            ? "—"
            : caps.slice(0, 8).map((cap) => (
                <Badge
                  key={cap.id}
                  tone={cap.severity === "high" ? "high" : cap.severity === "medium" ? "medium" : "ready"}
                  title={cap.description}
                >
                  {cap.id}
                </Badge>
              ))}
        </div>
      )}
    </div>
  );
}

type ContextMenuState = {
  x: number;
  y: number;
  entry: BrowseEntry;
} | null;

interface PaneProps {
  paneId: string;
  initialPath: string;
  stamp: string | null;
  subtreeRoot: string | null;
  treeRoots: BrowseEntry[];
  showTree: boolean;
  peerPath?: string | null;
  onPathChange?: (path: string) => void;
  onRequestDiff?: (archivePath: string, folderPath: string) => void;
}

function ExplorerPane({
  paneId,
  initialPath,
  stamp,
  subtreeRoot,
  treeRoots,
  showTree,
  peerPath = null,
  onPathChange,
  onRequestDiff,
}: PaneProps) {
  const [currentPath, setCurrentPath] = useState(initialPath);
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<BrowseEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [archiveEntries, setArchiveEntries] = useState<string[] | null>(null);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState>(null);
  const [hoverAuditionPath, setHoverAuditionPath] = useState<string | null>(null);
  const [selectedEntry, setSelectedEntry] = useState<BrowseEntry | null>(null);
  const [pathQuery, setPathQuery] = useState("");
  const [libraryHits, setLibraryHits] = useState<BrowseEntry[] | null>(null);
  const [librarySearching, setLibrarySearching] = useState(false);
  const [librarySearchError, setLibrarySearchError] = useState<string | null>(null);
  const [facetType, setFacetType] = useState<string>("");
  const [facetBuckets, setFacetBuckets] = useState<{
    type: Array<{ value: string; count: number }>;
    bpm: Array<{ value: string; count: number }>;
    key: Array<{ value: string; count: number }>;
  }>({ type: [], bpm: [], key: [] });
  const [facetBusy, setFacetBusy] = useState(false);
  const [peHint, setPeHint] = useState<PeHintPayload | null>(null);
  const [peHintBusy, setPeHintBusy] = useState(false);
  const [acoustIdMsg, setAcoustIdMsg] = useState<string | null>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadSeq = useRef(0);

  const setHoverAuditionDebounced = useCallback((path: string | null) => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    if (!path) {
      setHoverAuditionPath(null);
      return;
    }
    hoverTimer.current = setTimeout(() => setHoverAuditionPath(path), 280);
  }, []);

  const filteredEntries = useMemo(() => {
    const q = pathQuery.trim().toLowerCase();
    let rows = libraryHits ?? entries;
    if (!libraryHits && q) {
      rows = entries.filter(
        (entry) =>
          entry.name.toLowerCase().includes(q) || entry.path.toLowerCase().replace(/\\/g, "/").includes(q),
      );
    }
    if (facetType) {
      const token = facetType.toLowerCase();
      rows = rows.filter(
        (entry) => entry.is_dir || entry.name.toLowerCase().includes(token) || entry.path.toLowerCase().includes(token),
      );
    }
    return rows;
  }, [entries, pathQuery, libraryHits, facetType]);

  async function loadFacets() {
    if (!currentPath) {
      setLibrarySearchError("Open a folder before loading facets");
      return;
    }
    setFacetBusy(true);
    setLibrarySearchError(null);
    try {
      const data = await fetchBrowseFacets(currentPath, 200);
      setFacetBuckets({
        type: data.facets?.type ?? [],
        bpm: data.facets?.bpm ?? [],
        key: data.facets?.key ?? [],
      });
    } catch (err) {
      setLibrarySearchError(err instanceof Error ? err.message : String(err));
    } finally {
      setFacetBusy(false);
    }
  }

  async function runLibrarySearch() {
    const q = pathQuery.trim();
    if (q.length < 2) {
      setLibrarySearchError("Type at least 2 characters to search the library");
      return;
    }
    setLibrarySearching(true);
    setLibrarySearchError(null);
    try {
      const searchRoot = subtreeRoot?.trim() || currentPath || "";
      const data = await browseSearch(q, searchRoot, 200);
      setLibraryHits(data.entries);
      if (!data.entries.length) setLibrarySearchError("No path matches");
    } catch (err) {
      setLibraryHits([]);
      setLibrarySearchError(err instanceof Error ? err.message : String(err));
    } finally {
      setLibrarySearching(false);
    }
  }

  useEffect(() => () => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
  }, []);

  const loadDir = useCallback(
    async (path: string) => {
      if (subtreeRoot && path && !isUnderSubtree(path, subtreeRoot)) {
        setError(`Path is outside the tab subtree (${subtreeRoot})`);
        return;
      }
      const seq = ++loadSeq.current;
      setLoading(true);
      setError(null);
      setArchiveEntries(null);
      setArchiveError(null);
        setLibraryHits(null);
        setLibrarySearchError(null);
        setSelectedEntry(null);
        setFacetType("");
        setFacetBuckets({ type: [], bpm: [], key: [] });
        setPeHint(null);
        setPeHintBusy(false);
        setAcoustIdMsg(null);
      try {
        const data = await browseDirectoryEnriched(path, stamp ?? "");
        if (seq !== loadSeq.current) return;
        const resolved = data.path || path;
        setCurrentPath(resolved);
        saveLastPath(resolved);
        onPathChange?.(resolved);
        setParent(data.parent);
        setEntries(data.entries);
      } catch (err) {
        if (seq !== loadSeq.current) return;
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (seq === loadSeq.current) setLoading(false);
      }
    },
    [stamp, subtreeRoot, onPathChange],
  );

  useEffect(() => {
    void loadDir(initialPath);
  }, [initialPath, loadDir]);

  useEffect(() => {
    if (!contextMenu) return;
    function dismiss() {
      setContextMenu(null);
    }
    window.addEventListener("scroll", dismiss, true);
    return () => window.removeEventListener("scroll", dismiss, true);
  }, [contextMenu]);

  async function openEntry(entry: BrowseEntry) {
    if (entry.is_dir) {
      await loadDir(entry.path);
      return;
    }
    if (isArchiveName(entry.name)) {
      const seq = ++loadSeq.current;
      setLoading(true);
      setArchiveError(null);
      try {
        const data = await listArchiveContents(entry.path);
        if (seq !== loadSeq.current) return;
        setCurrentPath(entry.path);
        saveLastPath(entry.path);
        onPathChange?.(entry.path);
        setParent(data.path.replace(/[/\\][^/\\]+$/, "") || null);
        setEntries([]);
        setArchiveEntries(data.entries);
        if (data.error) setArchiveError(data.error);
      } catch (err) {
        if (seq !== loadSeq.current) return;
        setArchiveError(err instanceof Error ? err.message : String(err));
      } finally {
        if (seq === loadSeq.current) setLoading(false);
      }
    }
  }

  async function copyPath(path: string) {
    try {
      await navigator.clipboard.writeText(path);
    } catch {
      /* ignore */
    }
    setContextMenu(null);
  }

  async function handlePeHints(path: string) {
    setContextMenu(null);
    setPeHintBusy(true);
    setPeHint(null);
    try {
      const data = (await fetchPeHints(path)) as PeHintPayload;
      setPeHint(data);
    } catch (err) {
      setPeHint({ ok: false, error: err instanceof Error ? err.message : String(err) });
    } finally {
      setPeHintBusy(false);
    }
  }

  async function handleAcoustId(path: string) {
    setContextMenu(null);
    setAcoustIdMsg("AcoustID…");
    try {
      const res = await lookupAcoustId({ path });
      setAcoustIdMsg(formatAcoustIdResult(res));
    } catch (err) {
      setAcoustIdMsg(err instanceof Error ? err.message : String(err));
    }
  }

  const crumbs = useMemo(() => pathSegments(currentPath), [currentPath]);

  const contextItems: DropdownItem[] = contextMenu
    ? [
        {
          id: "open",
          label: contextMenu.entry.is_dir
            ? "Browse"
            : isArchiveName(contextMenu.entry.name)
              ? "List archive"
              : "Open",
          onSelect: () => void openEntry(contextMenu.entry),
        },
        {
          id: "reveal",
          label: "Reveal in OS",
          onSelect: () => void openInExplorer(contextMenu.entry.path),
        },
        {
          id: "copy",
          label: "Copy path",
          onSelect: () => void copyPath(contextMenu.entry.path),
        },
        ...(!contextMenu.entry.is_dir && isPeBinaryFile(contextMenu.entry.name)
          ? [
              {
                id: "pe-hints",
                label: "PE capability hints",
                onSelect: () => void handlePeHints(contextMenu.entry.path),
              },
            ]
          : []),
        ...(!contextMenu.entry.is_dir && isAuditionableFile(contextMenu.entry.name)
          ? [
              {
                id: "acoustid",
                label: "AcoustID lookup",
                onSelect: () => void handleAcoustId(contextMenu.entry.path),
              },
            ]
          : []),
        ...(isArchiveName(contextMenu.entry.name) && peerPath && onRequestDiff
          ? [
              {
                id: "diff",
                label: "Diff vs other pane",
                onSelect: () => onRequestDiff(contextMenu.entry.path, peerPath),
              },
            ]
          : []),
      ]
    : [];

  return (
    <div className="file-explorer-pane" data-pane={paneId}>
      <nav className="file-explorer-breadcrumbs" aria-label="Current path">
        <Button variant="ghost" size="sm" title="Library roots" onClick={() => void loadDir("")}>
          Roots
        </Button>
        {crumbs.map((crumb, index) => (
          <span key={`${crumb.path}:${index}`} className="breadcrumb-segment">
            <span className="breadcrumb-sep">/</span>
            <Button
              variant="ghost"
              size="sm"
              className="breadcrumb-link"
              title={crumb.path}
              onClick={() => void loadDir(crumb.path)}
            >
              {crumb.label}
            </Button>
          </span>
        ))}
      </nav>

      <div className="file-explorer-body">
        {showTree && (
          <FileExplorerTree roots={treeRoots} selectedPath={currentPath} onSelect={(p) => void loadDir(p)} />
        )}

        <div className="file-explorer-main">
          <div className="file-explorer-toolbar">
            <Button
              variant="secondary"
              size="sm"
              disabled={!parent}
              title="Go to parent folder"
              onClick={() => parent && void loadDir(parent)}
            >
              ↑ Up
            </Button>
            {archiveEntries && (
              <Button
                variant="secondary"
                size="sm"
                title="Return to folder listing"
                onClick={() => parent && void loadDir(parent)}
              >
                Back to folder
              </Button>
            )}
            <label className="explorer-search-field">
              <span className="visually-hidden">Search paths</span>
              <input
                type="search"
                value={pathQuery}
                placeholder="Filter folder · Search library…"
                aria-label="Search paths"
                title="Type to filter this folder instantly. Press Enter or Search for recursive library search."
                onChange={(e) => {
                  setPathQuery(e.target.value);
                  setLibraryHits(null);
                  setLibrarySearchError(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void runLibrarySearch();
                  }
                  if (e.key === "Escape") {
                    setPathQuery("");
                    setLibraryHits(null);
                    setLibrarySearchError(null);
                  }
                }}
              />
            </label>
            <Button
              variant="ghost"
              size="sm"
              disabled={librarySearching || pathQuery.trim().length < 2}
              title="Recursive path search under this root"
              onClick={() => void runLibrarySearch()}
            >
              {librarySearching ? "Searching…" : "Search"}
            </Button>
            {(libraryHits || pathQuery) && (
              <Button
                variant="ghost"
                size="sm"
                title="Clear search filter"
                onClick={() => {
                  setPathQuery("");
                  setLibraryHits(null);
                  setLibrarySearchError(null);
                }}
              >
                Clear
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              disabled={facetBusy || !currentPath}
              title="Derive type/BPM/key facets for this folder"
              onClick={() => void loadFacets()}
            >
              {facetBusy ? "Facets…" : "Facets"}
            </Button>
          </div>

          {(facetBuckets.type.length > 0 || facetBuckets.bpm.length > 0 || facetBuckets.key.length > 0) && (
            <div className="explorer-facet-groups">
              <button
                type="button"
                className={`bucket-chip ${!facetType ? "active" : ""}`.trim()}
                aria-pressed={!facetType}
                onClick={() => setFacetType("")}
              >
                All facets
              </button>
              <FacetStrip
                label="Sample type facets"
                options={facetBuckets.type}
                selected={facetType}
                onSelect={setFacetType}
              />
              <FacetStrip
                label="BPM facets"
                options={facetBuckets.bpm}
                selected={facetType}
                onSelect={setFacetType}
              />
              <FacetStrip
                label="Key facets"
                options={facetBuckets.key}
                selected={facetType}
                onSelect={setFacetType}
              />
            </div>
          )}

          {loading && <p className="count-muted">Loading…</p>}
          {error && <div className="error">{error}</div>}
          {archiveError && <div className="error">{archiveError}</div>}
          {librarySearchError && <p className="count-muted">{librarySearchError}</p>}
          {libraryHits && (
            <p className="count-muted">
              Library search: {libraryHits.length} hit{libraryHits.length === 1 ? "" : "s"}
            </p>
          )}
          {!libraryHits && pathQuery.trim() && !loading && !archiveEntries && (
            <p className="count-muted">
              Folder filter: {filteredEntries.length}/{entries.length}
            </p>
          )}

          {!loading && archiveEntries && (
            <div className="file-explorer-list">
              <p className="count-muted">
                Archive contents ({archiveEntries.length} entries) — listed without extracting
              </p>
              <ul className="archive-entry-list">
                {archiveEntries.map((name, index) => (
                  <li key={`${index}:${name}`}>{name}</li>
                ))}
              </ul>
            </div>
          )}

          {!loading && !archiveEntries && (
            <VirtualTable
              items={filteredEntries}
              colCount={4}
              estimateSize={40}
              tableClassName="data-table file-explorer-table"
              header={
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Size</th>
                  <th>Audit</th>
                </tr>
              }
              renderRow={(entry, _index, rowAttrs) => (
                <ExplorerRow
                  key={entry.path}
                  entry={entry}
                  rowAttrs={rowAttrs}
                  selected={selectedEntry?.path === entry.path}
                  autoAudition={hoverAuditionPath === entry.path && isAuditionableFile(entry.name)}
                  onHover={(active) => setHoverAuditionDebounced(active ? entry.path : null)}
                  onSelect={() => setSelectedEntry(entry)}
                  onOpen={() => void openEntry(entry)}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    setSelectedEntry(entry);
                    setContextMenu({ x: e.clientX, y: e.clientY, entry });
                  }}
                />
              )}
            />
          )}

          {selectedEntry && !selectedEntry.is_dir && isAuditionableFile(selectedEntry.name) && (
            <div className="explorer-spot-preview" aria-label="Spot preview">
              <div className="explorer-spot-meta">
                <strong title={selectedEntry.path}>{selectedEntry.name}</strong>
                <span className="count-muted">{formatSize(selectedEntry.size)}</span>
              </div>
              <AudioPreviewStrip path={selectedEntry.path} name={selectedEntry.name} autoPlay={false} />
            </div>
          )}
          {selectedEntry && !selectedEntry.is_dir && isPeBinaryFile(selectedEntry.name) && (
            <div className="explorer-spot-preview" aria-label="PE capability hints">
              <div className="explorer-spot-meta">
                <strong title={selectedEntry.path}>{selectedEntry.name}</strong>
                <span className="count-muted">{formatSize(selectedEntry.size)}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={peHintBusy}
                  title="Capa-lite PE capability hints (pefile heuristics)"
                  onClick={() => void handlePeHints(selectedEntry.path)}
                >
                  {peHintBusy ? "PE hints…" : "PE hints"}
                </Button>
              </div>
            </div>
          )}
          <PeHintBanner result={peHint} busy={peHintBusy} />
          {acoustIdMsg ? <p className="count-muted">{acoustIdMsg}</p> : null}
        </div>
      </div>

      {contextMenu && (
        <DropdownMenu
          open
          onOpenChange={(next) => {
            if (!next) setContextMenu(null);
          }}
          align="start"
          ariaLabel="File actions"
          trigger={
            <button
              type="button"
              className="explorer-context-anchor"
              style={{ top: contextMenu.y, left: contextMenu.x }}
              aria-hidden
              tabIndex={-1}
            />
          }
          items={contextItems}
        />
      )}
    </div>
  );
}

function ExplorerRow({
  entry,
  onOpen,
  onSelect,
  onContextMenu,
  onHover,
  selected = false,
  autoAudition = false,
  rowAttrs,
}: {
  entry: BrowseEntry;
  onOpen: () => void;
  onSelect: () => void;
  onContextMenu: (e: React.MouseEvent) => void;
  onHover?: (active: boolean) => void;
  selected?: boolean;
  autoAudition?: boolean;
  rowAttrs?: VirtualRowAttrs;
}) {
  const drag = useExplorerPathDrag(entry.path);
  const auditLabel = [entry.vendor, entry.status, entry.investigation_bucket].filter(Boolean).join(" · ");

  return (
    <tr
      className={[entry.is_dir ? "dir-row" : "", selected ? "selected" : ""].filter(Boolean).join(" ")}
      onClick={onSelect}
      onDoubleClick={onOpen}
      onContextMenu={onContextMenu}
      onMouseEnter={() => onHover?.(true)}
      onMouseLeave={() => onHover?.(false)}
      draggable={drag.draggable}
      onDragStart={drag.onDragStart}
      {...rowAttrs}
    >
      <td>
        <div className="explorer-name-cell">
          <button
            type="button"
            className="linkish-btn"
            title={
              entry.is_dir
                ? "Open this folder"
                : isArchiveName(entry.name)
                  ? "List archive contents without extracting"
                  : "Click to Spot-preview · drag to Scan path fields"
            }
            onClick={(e) => {
              e.stopPropagation();
              onSelect();
              if (entry.is_dir || isArchiveName(entry.name)) onOpen();
            }}
          >
            {entry.name}
          </button>
          {!entry.is_dir && isAuditionableFile(entry.name) && (
            <AudioPreviewStrip path={entry.path} name={entry.name} autoPlay={autoAudition} compact />
          )}
        </div>
      </td>
      <td>{entry.is_dir ? "Folder" : isArchiveName(entry.name) ? "Archive" : "File"}</td>
      <td>{formatSize(entry.size)}</td>
      <td className="explorer-audit-cell">{auditLabel || "—"}</td>
    </tr>
  );
}

interface Props {
  initialPath: string;
  secondaryPath?: string | null;
  dualPane?: boolean;
  stamp?: string | null;
  subtreeRoot?: string | null;
  pinned?: boolean;
  popOut?: boolean;
  onTogglePopOut?: () => void;
  onTogglePin?: () => void;
  onClose: () => void;
}

export function FileExplorerPanel({
  initialPath,
  secondaryPath = null,
  dualPane = false,
  stamp = null,
  subtreeRoot = null,
  pinned = false,
  popOut = false,
  onTogglePin,
  onTogglePopOut,
  onClose,
}: Props) {
  const [treeRoots, setTreeRoots] = useState<BrowseEntry[]>([]);
  const [primaryPath, setPrimaryPath] = useState(initialPath);
  const [secondaryCurrentPath, setSecondaryCurrentPath] = useState(secondaryPath ?? "");
  const [diffPair, setDiffPair] = useState<{ archivePath: string; folderPath: string } | null>(
    null,
  );

  useEffect(() => {
    void browseDirectoryEnriched("", stamp ?? "").then((data) =>
      setTreeRoots(data.entries.filter((e) => e.is_dir)),
    );
  }, [stamp]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && !pinned) onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, pinned]);

  const shellClass = [
    "file-explorer-shell",
    pinned ? "pinned" : "modal",
    popOut ? "popout" : "",
    dualPane && secondaryPath ? "dual-pane" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={pinned ? "file-explorer-dock" : `file-explorer-backdrop${popOut ? " popout-mode" : ""}`}
      onClick={pinned ? undefined : onClose}
      role="presentation"
    >
      {diffPair && stamp && (
        <ArchiveDiffWizard
          stamp={stamp}
          archivePath={diffPair.archivePath}
          folderPath={diffPair.folderPath}
          onClose={() => setDiffPair(null)}
        />
      )}
      <aside
        className={shellClass}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Library explorer"
      >
        <header className="file-explorer-header">
          <div>
            <h2>Library explorer</h2>
            {subtreeRoot && (
              <p className="count-muted" title="Subtree filter for current tab">
                Filtered to: {subtreeRoot}
              </p>
            )}
          </div>
          <DropZoneOverlay />
          <div className="file-explorer-header-actions">
            <Button
              variant="secondary"
              size="sm"
              active={popOut}
              title={popOut ? "Standard width panel" : "Pop out wide explorer"}
              onClick={onTogglePopOut}
            >
              {popOut ? "Standard" : "Pop out"}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              active={pinned}
              title={pinned ? "Unpin panel (closes on backdrop click)" : "Pin panel docked on the right"}
              onClick={onTogglePin}
            >
              {pinned ? "Unpin" : "Pin"}
            </Button>
            <Button variant="secondary" size="sm" onClick={onClose} title="Close explorer (Esc)">
              Close
            </Button>
          </div>
        </header>

        {dualPane && secondaryPath ? (
          <div className="file-explorer-dual">
            <ExplorerPane
              paneId="primary"
              initialPath={initialPath}
              stamp={stamp}
              subtreeRoot={subtreeRoot ?? null}
              treeRoots={treeRoots}
              showTree
              peerPath={secondaryCurrentPath}
              onPathChange={setPrimaryPath}
              onRequestDiff={(archivePath, folderPath) =>
                setDiffPair({ archivePath, folderPath })
              }
            />
            <ExplorerPane
              paneId="secondary"
              initialPath={secondaryPath}
              stamp={stamp}
              subtreeRoot={subtreeRoot ?? null}
              treeRoots={treeRoots}
              showTree={false}
              peerPath={primaryPath}
              onPathChange={setSecondaryCurrentPath}
              onRequestDiff={(archivePath, folderPath) =>
                setDiffPair({ archivePath, folderPath })
              }
            />
          </div>
        ) : (
          <ExplorerPane
            paneId="single"
            initialPath={initialPath}
            stamp={stamp}
            subtreeRoot={subtreeRoot ?? null}
            treeRoots={treeRoots}
            showTree
          />
        )}
      </aside>
    </div>
  );
}
