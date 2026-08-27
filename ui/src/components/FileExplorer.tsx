import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  browseDirectoryEnriched,
  listArchiveContents,
  openInExplorer,
  type BrowseEntry,
} from "../api/client";
import { useExplorerPathDrag } from "../contexts/FileExplorerContext";
import { Button } from "../ui";
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
    window.addEventListener("click", dismiss);
    window.addEventListener("scroll", dismiss, true);
    return () => {
      window.removeEventListener("click", dismiss);
      window.removeEventListener("scroll", dismiss, true);
    };
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

  const crumbs = useMemo(() => pathSegments(currentPath), [currentPath]);

  return (
    <div className="file-explorer-pane" data-pane={paneId}>
      <nav className="file-explorer-breadcrumbs" aria-label="Current path">
        <button type="button" className="text-btn" title="Library roots" onClick={() => void loadDir("")}>
          Roots
        </button>
        {crumbs.map((crumb, index) => (
          <span key={`${crumb.path}:${index}`} className="breadcrumb-segment">
            <span className="breadcrumb-sep">/</span>
            <button
              type="button"
              className="text-btn breadcrumb-link"
              title={crumb.path}
              onClick={() => void loadDir(crumb.path)}
            >
              {crumb.label}
            </button>
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
          </div>

          {loading && <p className="count-muted">Loading…</p>}
          {error && <div className="error">{error}</div>}
          {archiveError && <div className="error">{archiveError}</div>}

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
            <table className="data-table file-explorer-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Type</th>
                  <th>Size</th>
                  <th>Audit</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <ExplorerRow
                    key={entry.path}
                    entry={entry}
                    autoAudition={hoverAuditionPath === entry.path && isAuditionableFile(entry.name)}
                    onHover={(active) => setHoverAuditionDebounced(active ? entry.path : null)}
                    onOpen={() => void openEntry(entry)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      setContextMenu({ x: e.clientX, y: e.clientY, entry });
                    }}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {contextMenu && (
        <menu
          className="explorer-context-menu"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          <li>
            <button type="button" onClick={() => void openEntry(contextMenu.entry)}>
              {contextMenu.entry.is_dir ? "Browse" : isArchiveName(contextMenu.entry.name) ? "List archive" : "Open"}
            </button>
          </li>
          <li>
            <button
              type="button"
              onClick={() => {
                void openInExplorer(contextMenu.entry.path);
                setContextMenu(null);
              }}
            >
              Reveal in OS
            </button>
          </li>
          <li>
            <button type="button" onClick={() => void copyPath(contextMenu.entry.path)}>
              Copy path
            </button>
          </li>
          {isArchiveName(contextMenu.entry.name) && peerPath && onRequestDiff && (
            <li>
              <button
                type="button"
                onClick={() => {
                  onRequestDiff(contextMenu.entry.path, peerPath);
                  setContextMenu(null);
                }}
              >
                Diff vs other pane
              </button>
            </li>
          )}
        </menu>
      )}
    </div>
  );
}

function ExplorerRow({
  entry,
  onOpen,
  onContextMenu,
  onHover,
  autoAudition = false,
}: {
  entry: BrowseEntry;
  onOpen: () => void;
  onContextMenu: (e: React.MouseEvent) => void;
  onHover?: (active: boolean) => void;
  autoAudition?: boolean;
}) {
  const drag = useExplorerPathDrag(entry.path);
  const auditLabel = [entry.vendor, entry.status, entry.investigation_bucket].filter(Boolean).join(" · ");

  return (
    <tr
      className={entry.is_dir ? "dir-row" : ""}
      onDoubleClick={onOpen}
      onContextMenu={onContextMenu}
      onMouseEnter={() => onHover?.(true)}
      onMouseLeave={() => onHover?.(false)}
      draggable={drag.draggable}
      onDragStart={drag.onDragStart}
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
                  : "Drag to Scan path fields"
            }
            onClick={onOpen}
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
