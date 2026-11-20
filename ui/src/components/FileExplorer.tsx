import "./LibraryWorkspace.css";
import { LibraryAssetIcon, type AssetKind } from "./LibraryAssetIcon";
import { LoadingStatus } from "../ui/LoadingStatus";
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
  type DirectoryPage,
  type SearchPage,
} from "../api/client";
import { useLocation, useNavigate } from "react-router-dom";
import {
  useFileExplorer,
  useExplorerPathDrag,
} from "../contexts/FileExplorerContext";
import {
  Badge,
  Button,
  DropdownMenu,
  VirtualTable,
  type DropdownItem,
  type VirtualRowAttrs,
} from "../ui";
import { explorerBreadcrumbs } from "../utils/explorerBreadcrumbs";
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

function assetKind(entry: BrowseEntry): AssetKind {
  return entry.is_dir
    ? "folder"
    : isAuditionableFile(entry.name)
      ? "audio"
      : isArchiveName(entry.name)
        ? "archive"
        : "file";
}
function lastSegment(path: string) {
  return path.split(/[/\\]/).filter(Boolean).pop() || "Library locations";
}

function formatSize(size: number | null | undefined): string {
  if (size == null) return "—";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024)
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
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

function isUnderSubtree(path: string, subtreeRoot: string | null): boolean {
  if (!subtreeRoot?.trim()) return true;
  const norm = (p: string) =>
    p.replace(/\\/g, "/").toLowerCase().replace(/\/+$/, "");
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

function PeHintBanner({
  result,
  busy,
}: {
  result: PeHintPayload | null;
  busy: boolean;
}) {
  if (busy) return <p className="count-muted">PE capability hints…</p>;
  if (!result) return null;
  const caps = result.capabilities ?? [];
  return (
    <div
      className="banner dry explorer-pe-hint"
      style={{ marginTop: "0.75rem" }}
    >
      <strong>PE capability hints</strong>
      {result.error ? <p className="count-muted">{result.error}</p> : null}
      {result.engine && !result.error ? (
        <p className="count-muted">Engine: {result.engine}</p>
      ) : null}
      {!result.error && (
        <div className="pe-cap-cell">
          {caps.length === 0
            ? "—"
            : caps.slice(0, 8).map((cap) => (
                <Badge
                  key={cap.id}
                  tone={
                    cap.severity === "high"
                      ? "high"
                      : cap.severity === "medium"
                        ? "medium"
                        : "ready"
                  }
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
  workspace?: boolean;
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
  workspace = false,
  initialPath,
  stamp,
  subtreeRoot,
  treeRoots,
  showTree,
  peerPath = null,
  onPathChange,
  onRequestDiff,
}: PaneProps) {
  const navigate = useNavigate();
  const { close, panelOpen } = useFileExplorer();
  const [kindFilter, setKindFilter] = useState<AssetKind | "all">("all");
  const [currentPath, setCurrentPath] = useState(initialPath);
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<BrowseEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [archiveEntries, setArchiveEntries] = useState<string[] | null>(null);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState>(null);
  const [hoverAuditionPath, setHoverAuditionPath] = useState<string | null>(
    null,
  );
  const [selectedEntry, setSelectedEntry] = useState<BrowseEntry | null>(null);
  const auditionTrim = useRef({ path: "", start: 0, end: 1 });
  const [pathQuery, setPathQuery] = useState("");
  const [libraryHits, setLibraryHits] = useState<BrowseEntry[] | null>(null);
  const [dirPage, setDirPage] = useState<DirectoryPage | null>(null);
  const [searchPage, setSearchPage] = useState<SearchPage | null>(null);
  const searchSequence = useRef(0);
  const [librarySearching, setLibrarySearching] = useState(false);
  const [librarySearchError, setLibrarySearchError] = useState<string | null>(
    null,
  );
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
          entry.name.toLowerCase().includes(q) ||
          entry.path.toLowerCase().replace(/\\/g, "/").includes(q),
      );
    }
    if (facetType) {
      const token = facetType.toLowerCase();
      rows = rows.filter(
        (entry) =>
          entry.is_dir ||
          entry.name.toLowerCase().includes(token) ||
          entry.path.toLowerCase().includes(token),
      );
    }
    return kindFilter === "all"
      ? rows
      : rows.filter((entry) => assetKind(entry) === kindFilter);
  }, [entries, pathQuery, libraryHits, facetType, kindFilter]);

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

  function clearSearch() {
    searchSequence.current += 1;
    setSearchPage(null);
    setLibraryHits(null);
    setLibrarySearching(false);
    setLibrarySearchError(null);
  }

  async function runLibrarySearch(cursor = "") {
    const q = pathQuery.trim();
    if (q.length < 2) {
      setLibrarySearchError("Type at least 2 characters to search the library");
      return;
    }
    const seq = ++searchSequence.current;
    setLibrarySearching(true);
    setLibrarySearchError(null);
    try {
      const searchRoot = subtreeRoot?.trim() || currentPath || "";
      const data = await browseSearch(q, searchRoot, 200, cursor, stamp ?? "");
      if (seq !== searchSequence.current) return;
      setSearchPage(data);
      setLibraryHits((prior) =>
        cursor ? [...(prior ?? []), ...data.entries] : data.entries,
      );
    } catch (err) {
      if (seq === searchSequence.current)
        setLibrarySearchError(err instanceof Error ? err.message : String(err));
    } finally {
      if (seq === searchSequence.current) setLibrarySearching(false);
    }
  }

  useEffect(
    () => () => {
      if (hoverTimer.current) clearTimeout(hoverTimer.current);
    },
    [],
  );

  const loadDir = useCallback(
    async (path: string, cursor = "", selectFile = false) => {
      if (subtreeRoot && path && !isUnderSubtree(path, subtreeRoot)) {
        setError(`Path is outside the tab subtree (${subtreeRoot})`);
        return;
      }
      const seq = ++loadSeq.current;
      setLoading(true);
      setError(null);
      if (!cursor) {
        searchSequence.current += 1;
        setLibrarySearching(false);
        setSearchPage(null);
        setDirPage(null);
        setArchiveEntries(null);
        setArchiveError(null);
        setLibraryHits(null);
        setLibrarySearchError(null);
        setSelectedEntry(null);
        setKindFilter("all");
        setFacetType("");
        setFacetBuckets({ type: [], bpm: [], key: [] });
        setPeHint(null);
        setPeHintBusy(false);
        setAcoustIdMsg(null);
      }
      try {
        const data = await browseDirectoryEnriched(path, stamp ?? "", cursor);
        if (seq !== loadSeq.current) return;
        const resolved = data.path || path;
        setCurrentPath(resolved);
        saveLastPath(resolved);
        onPathChange?.(resolved);
        setParent(data.parent);
        setDirPage(data);
        setEntries((prior) =>
          cursor ? [...prior, ...data.entries] : data.entries,
        );
        if (selectFile) {
          const selected = data.entries.find(
            (item) => !item.is_dir && item.path === path,
          );
          setSelectedEntry(selected ?? null);
        }
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
    void loadDir(initialPath, "", true);
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
      setPathQuery("");
      await loadDir(entry.path);
      return;
    }
    if (isArchiveName(entry.name)) {
      const seq = ++loadSeq.current;
      clearSearch();
      setDirPage(null);
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
      setPeHint({
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      });
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

  const crumbs = useMemo(
    () =>
      explorerBreadcrumbs(currentPath).filter((crumb) =>
        treeRoots.some((root) => isUnderSubtree(crumb.path, root.path)),
      ),
    [currentPath, treeRoots],
  );

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
        ...(!contextMenu.entry.is_dir &&
        isAuditionableFile(contextMenu.entry.name)
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
        <Button
          variant="ghost"
          size="sm"
          title="Library roots"
          onClick={() => void loadDir("")}
        >
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
              aria-label={`Open ${crumb.path}`}
              onClick={() => void loadDir(crumb.path)}
            >
              {crumb.label}
            </Button>
          </span>
        ))}
      </nav>

      <div className="file-explorer-body">
        {showTree && (
          <aside
            className="library-location-rail"
            aria-label="Library locations"
          >
            <div className="library-rail-heading">
              <h3>Locations</h3>
              <span>{treeRoots.length}</span>
            </div>
            <FileExplorerTree
              roots={treeRoots}
              selectedPath={currentPath}
              onSelect={(p) => {
                setPathQuery("");
                void loadDir(p);
              }}
            />
            <div className="library-drop-block">
              <h4>Open a path</h4>{" "}
              <DropZoneOverlay
                receiveDesktopDrops={!workspace || !panelOpen}
                onOpen={(row) => {
                  setPathQuery("");
                  void loadDir(row.path, "", row.action !== "browse");
                }}
              />
            </div>
          </aside>
        )}

        <div className="file-explorer-main">
          <header className="library-location-title">
            <div>
              <h3>
                {libraryHits ? "Search results" : lastSegment(currentPath)}
              </h3>
              {currentPath && <span title={currentPath}>{currentPath}</span>}
            </div>
          </header>
          <div className="file-explorer-toolbar">
            <Button
              variant="secondary"
              size="sm"
              disabled={!parent}
              title="Go to parent folder"
              onClick={() => parent && void loadDir(parent)}
            >
              Up
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
                placeholder="Filter names or search below this folder"
                aria-label="Search paths"
                title="Type to filter this folder instantly. Press Enter or Search for recursive library search."
                onChange={(e) => {
                  setPathQuery(e.target.value);
                  clearSearch();
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void runLibrarySearch();
                  }
                  if (e.key === "Escape") {
                    setPathQuery("");
                    clearSearch();
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
                  clearSearch();
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

          {workspace && !archiveEntries && (
            <div className="library-kind-filter" aria-label="File types">
              {(["all", "audio", "folder", "archive", "file"] as const).map(
                (kind) => (
                  <button
                    type="button"
                    key={kind}
                    aria-pressed={kindFilter === kind}
                    onClick={() => setKindFilter(kind)}
                  >
                    {
                      {
                        all: "All",
                        audio: "Audio",
                        folder: "Folders",
                        archive: "Archives",
                        file: "Other",
                      }[kind]
                    }
                  </button>
                ),
              )}
            </div>
          )}
          {(facetBuckets.type.length > 0 ||
            facetBuckets.bpm.length > 0 ||
            facetBuckets.key.length > 0) && (
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

          {loading && <LoadingStatus>Loading…</LoadingStatus>}
          {error && <div className="error">{error}</div>}
          {archiveError && <div className="error">{archiveError}</div>}
          {librarySearchError && (
            <p className="count-muted">{librarySearchError}</p>
          )}
          {!archiveEntries && !libraryHits && dirPage && (
            <div className="explorer-page-controls">
              <span role="status">
                {entries.length} of {dirPage.total ?? entries.length} items
                {dirPage.partial ? ` · ${dirPage.skipped} unavailable` : ""}
                {dirPage.observed_at && (
                  <>
                    {" "}
                    · Checked{" "}
                    <time
                      dateTime={dirPage.observed_at}
                      title={dirPage.observed_at}
                    >
                      {new Date(dirPage.observed_at).toLocaleTimeString()}
                    </time>
                  </>
                )}
              </span>
              {dirPage.next_cursor && (
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={loading}
                  onClick={() =>
                    void loadDir(currentPath, dirPage.next_cursor!)
                  }
                >
                  Load more items
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                disabled={loading}
                onClick={() => void loadDir(currentPath)}
              >
                Refresh folder
              </Button>
            </div>
          )}
          {libraryHits && searchPage && (
            <div className="explorer-page-controls">
              <span role="status">
                {libraryHits.length} matches · {searchPage.scanned} entries
                checked
                {searchPage.next_cursor
                  ? " · Search incomplete"
                  : searchPage.skipped
                    ? " · Partial results"
                    : " · Search complete"}
                {searchPage.skipped
                  ? ` · ${searchPage.skipped} unavailable`
                  : ""}
              </span>
              {searchPage.next_cursor && (
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={librarySearching}
                  onClick={() => void runLibrarySearch(searchPage.next_cursor!)}
                >
                  Continue search
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                disabled={librarySearching}
                onClick={() => void runLibrarySearch()}
              >
                Refresh search
              </Button>
            </div>
          )}
          {!libraryHits && pathQuery.trim() && !loading && !archiveEntries && (
            <p className="count-muted">
              Folder filter · {filteredEntries.length} of {entries.length}{" "}
              loaded items
            </p>
          )}

          {!loading && archiveEntries && (
            <div className="file-explorer-list">
              <p className="count-muted">
                Archive contents ({archiveEntries.length} entries) — listed
                without extracting
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
              emptyMessage={
                pathQuery || kindFilter !== "all"
                  ? "No files match these filters."
                  : "This location is empty."
              }
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
                  autoAudition={
                    hoverAuditionPath === entry.path &&
                    isAuditionableFile(entry.name)
                  }
                  onHover={(active) =>
                    setHoverAuditionDebounced(active ? entry.path : null)
                  }
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
        </div>
        <aside className="library-asset-inspector" aria-label="Asset inspector">
          <h3>Inspector</h3>
          <div className="library-inspector-title">
            <LibraryAssetIcon
              kind={selectedEntry ? assetKind(selectedEntry) : "folder"}
              large
            />
            <strong title={selectedEntry?.path || currentPath}>
              {selectedEntry?.name || lastSegment(currentPath)}
            </strong>
            <span>{selectedEntry ? assetKind(selectedEntry) : "Location"}</span>
          </div>
          {selectedEntry ? (
            <>
              {isAuditionableFile(selectedEntry.name) &&
                !selectedEntry.is_dir && (
                  <div
                    className="explorer-spot-preview"
                    aria-label="Spot preview"
                  >
                    <AudioPreviewStrip
                      key={selectedEntry.path}
                      path={selectedEntry.path}
                      name={selectedEntry.name}
                      onTrimChange={(start, end) => {
                        auditionTrim.current = {
                          path: selectedEntry.path,
                          start,
                          end,
                        };
                      }}
                    />
                    <Button
                      variant="primary"
                      onClick={() => {
                        const params = new URLSearchParams({
                          path: selectedEntry.path,
                        });
                        if (stamp) params.set("run", stamp);
                        close();
                        navigate(
                          { pathname: "/studio", search: params.toString() },
                          {
                            state: {
                              studioImport: crypto.randomUUID(),
                              sourceTrim:
                                auditionTrim.current.path === selectedEntry.path
                                  ? [
                                      auditionTrim.current.start,
                                      auditionTrim.current.end,
                                    ]
                                  : undefined,
                            },
                          },
                        );
                      }}
                    >
                      Add to mix
                    </Button>
                  </div>
                )}
              <dl>
                <dt>File size</dt>
                <dd>{formatSize(selectedEntry.size)}</dd>
                {selectedEntry.vendor && (
                  <>
                    <dt>Vendor</dt>
                    <dd>{selectedEntry.vendor}</dd>
                  </>
                )}
                {selectedEntry.status && (
                  <>
                    <dt>Audit</dt>
                    <dd>{selectedEntry.status}</dd>
                  </>
                )}
              </dl>
              <details className="library-location-details">
                <summary>Full path</summary>
                <p>{selectedEntry.path}</p>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => void copyPath(selectedEntry.path)}
                >
                  Copy path
                </Button>
              </details>
              {!!selectedEntry.is_dir && (
                <Button onClick={() => void openEntry(selectedEntry)}>
                  Browse folder
                </Button>
              )}
              {!selectedEntry.is_dir && isArchiveName(selectedEntry.name) && (
                <Button onClick={() => void openEntry(selectedEntry)}>
                  List archive
                </Button>
              )}
              {!selectedEntry.is_dir && isPeBinaryFile(selectedEntry.name) && (
                <Button
                  disabled={peHintBusy}
                  onClick={() => void handlePeHints(selectedEntry.path)}
                >
                  Inspect binary
                </Button>
              )}
            </>
          ) : (
            <>
              <dl>
                <dt>Loaded items</dt>
                <dd>{entries.length}</dd>
                <dt>Audio files</dt>
                <dd>
                  {entries.filter((e) => assetKind(e) === "audio").length}
                </dd>
                <dt>Folders</dt>
                <dd>{entries.filter((e) => e.is_dir).length}</dd>
              </dl>
              <p className="library-inspector-hint">
                Select a file to inspect its details or audition audio.
              </p>
            </>
          )}
          <PeHintBanner result={peHint} busy={peHintBusy} />
          {acoustIdMsg && <p role="status">{acoustIdMsg}</p>}
        </aside>
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
  const auditLabel = [entry.vendor, entry.status, entry.investigation_bucket]
    .filter(Boolean)
    .join(" · ");

  return (
    <tr
      className={[entry.is_dir ? "dir-row" : "", selected ? "selected" : ""]
        .filter(Boolean)
        .join(" ")}
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
          <LibraryAssetIcon kind={assetKind(entry)} />
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
            aria-label={
              entry.is_dir
                ? `Open folder ${entry.name}`
                : isArchiveName(entry.name)
                  ? `List archive ${entry.name}`
                  : `Select ${entry.name}`
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
            <AudioPreviewStrip
              path={entry.path}
              name={entry.name}
              autoPlay={autoAudition}
              compact
            />
          )}
        </div>
      </td>
      <td className="library-type-cell">
        {assetKind(entry) === "audio"
          ? entry.name.split(".").pop()?.toUpperCase()
          : entry.is_dir
            ? "Folder"
            : isArchiveName(entry.name)
              ? "Archive"
              : "File"}
      </td>
      <td>{formatSize(entry.size)}</td>
      <td className="explorer-audit-cell">{auditLabel || "—"}</td>
    </tr>
  );
}

interface Props {
  initialPath: string;
  fullPage?: boolean;
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
  fullPage = false,
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
  const { openPath } = useFileExplorer();
  const [compare, setCompare] = useState(false);
  const [compareStart, setCompareStart] = useState("");
  const [primaryPath, setPrimaryPath] = useState(initialPath);
  const [secondaryCurrentPath, setSecondaryCurrentPath] = useState(
    secondaryPath ?? "",
  );
  const [diffPair, setDiffPair] = useState<{
    archivePath: string;
    folderPath: string;
  } | null>(null);

  useEffect(() => {
    let active = true;
    void browseDirectoryEnriched("", stamp ?? "")
      .then((data) => {
        if (active) setTreeRoots(data.entries.filter((e) => e.is_dir));
      })
      .catch(() => {
        if (active) setTreeRoots([]);
      });
    return () => {
      active = false;
    };
  }, [stamp]);

  useEffect(() => {
    if (fullPage) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && !pinned) onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, pinned, fullPage]);

  const shellClass = [
    "file-explorer-shell",
    fullPage ? "route-explorer" : pinned ? "pinned" : "modal",
    popOut ? "popout" : "",
    (dualPane && secondaryPath) || compare ? "dual-pane" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div
      className={
        fullPage
          ? "library-workspace"
          : pinned
            ? "file-explorer-dock"
            : `file-explorer-backdrop${popOut ? " popout-mode" : ""}`
      }
      onClick={pinned || fullPage ? undefined : onClose}
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
        role={fullPage ? "region" : "dialog"}
        aria-label="Library explorer"
      >
        {fullPage ? (
          <div className="library-view-tools">
            <div className="library-view-mode">
              <Button
                size="sm"
                active={!compare}
                aria-pressed={!compare}
                onClick={() => setCompare(false)}
              >
                Browse
              </Button>
              <Button
                size="sm"
                active={compare}
                aria-pressed={compare}
                onClick={() => {
                  setCompareStart(primaryPath || treeRoots[0]?.path || "");
                  setCompare(true);
                }}
              >
                Compare folders
              </Button>
            </div>
            <Button
              size="sm"
              variant="ghost"
              disabled={!primaryPath && !treeRoots.length}
              onClick={() => openPath(primaryPath || treeRoots[0].path)}
            >
              Open as panel
            </Button>
          </div>
        ) : (
          <header className="file-explorer-header">
            <div>
              <h2>Library explorer</h2>
              {subtreeRoot && (
                <p
                  className="count-muted"
                  title="Subtree filter for current tab"
                >
                  Filtered to: {subtreeRoot}
                </p>
              )}
            </div>
            <div className="file-explorer-header-actions">
              <Button
                variant="secondary"
                size="sm"
                active={popOut}
                title={
                  popOut ? "Standard width panel" : "Pop out wide explorer"
                }
                onClick={onTogglePopOut}
              >
                {popOut ? "Standard" : "Pop out"}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                active={pinned}
                title={
                  pinned
                    ? "Unpin panel (closes on backdrop click)"
                    : "Pin panel docked on the right"
                }
                onClick={onTogglePin}
              >
                {pinned ? "Unpin" : "Pin"}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={onClose}
                title="Close explorer (Esc)"
              >
                Close
              </Button>
            </div>
          </header>
        )}

        <div
          className={
            (dualPane && secondaryPath) || compare
              ? "file-explorer-dual"
              : "file-explorer-single"
          }
        >
          <ExplorerPane
            workspace={fullPage}
            paneId={
              (dualPane && secondaryPath) || compare ? "primary" : "single"
            }
            initialPath={
              initialPath ||
              (fullPage && treeRoots.length === 1 ? treeRoots[0].path : "")
            }
            stamp={stamp}
            subtreeRoot={subtreeRoot ?? null}
            treeRoots={treeRoots}
            showTree
            onPathChange={setPrimaryPath}
            peerPath={
              (dualPane && secondaryPath) || compare
                ? secondaryCurrentPath
                : null
            }
            onRequestDiff={
              stamp
                ? (archivePath, folderPath) =>
                    setDiffPair({ archivePath, folderPath })
                : undefined
            }
          />
          {((dualPane && secondaryPath) || compare) && (
            <ExplorerPane
              workspace={fullPage}
              paneId="secondary"
              initialPath={secondaryPath ?? compareStart}
              stamp={stamp}
              subtreeRoot={subtreeRoot ?? null}
              treeRoots={treeRoots}
              showTree={false}
              onPathChange={setSecondaryCurrentPath}
              peerPath={primaryPath}
              onRequestDiff={
                stamp
                  ? (archivePath, folderPath) =>
                      setDiffPair({ archivePath, folderPath })
                  : undefined
              }
            />
          )}
        </div>
      </aside>
    </div>
  );
}

export function LibraryWorkspace({ stamp }: { stamp?: string | null }) {
  const { search } = useLocation();
  const [last] = useState(() => {
    try {
      return sessionStorage.getItem(LAST_PATH_KEY) ?? "";
    } catch {
      return "";
    }
  });
  const initial = new URLSearchParams(search).get("path") || last;
  return (
    <FileExplorerPanel
      fullPage
      initialPath={initial}
      stamp={stamp}
      onClose={() => undefined}
    />
  );
}
