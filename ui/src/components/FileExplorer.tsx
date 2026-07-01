import { useCallback, useEffect, useRef, useState } from "react";
import { browseDirectory, listArchiveContents, type BrowseEntry } from "../api/client";

const ARCHIVE_EXT = /\.(zip|rar|7z|iso|tar(\.(gz|bz2|xz))?|gz|001)$/i;

function isArchiveName(name: string): boolean {
  const lower = name.toLowerCase();
  if (/\.tar\.(gz|bz2|xz)$/.test(lower)) return true;
  return ARCHIVE_EXT.test(name);
}

interface Props {
  initialPath: string;
  onClose: () => void;
}

function formatSize(size: number | null | undefined): string {
  if (size == null) return "—";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  return `${(size / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function FileExplorerPanel({ initialPath, onClose }: Props) {
  const [currentPath, setCurrentPath] = useState(initialPath);
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<BrowseEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [archiveEntries, setArchiveEntries] = useState<string[] | null>(null);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const loadSeq = useRef(0);

  const loadDir = useCallback(async (path: string) => {
    const seq = ++loadSeq.current;
    setLoading(true);
    setError(null);
    setArchiveEntries(null);
    setArchiveError(null);
    try {
      const data = await browseDirectory(path);
      if (seq !== loadSeq.current) return;
      setCurrentPath(data.path || path);
      setParent(data.parent);
      setEntries(data.entries);
    } catch (err) {
      if (seq !== loadSeq.current) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (seq === loadSeq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDir(initialPath);
  }, [initialPath, loadDir]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

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

  return (
    <div className="file-explorer-backdrop" onClick={onClose} role="presentation">
      <aside
        className="file-explorer-panel"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Library browser"
      >
        <header className="file-explorer-header">
          <div>
            <h2>Library browser</h2>
            <p className="count-muted" title="Current folder or archive being viewed">
              {currentPath || "Library roots"}
            </p>
          </div>
          <button type="button" className="icon-btn" onClick={onClose} title="Close browser (Esc)">
            Close
          </button>
        </header>

        <div className="file-explorer-toolbar">
          <button
            type="button"
            className="text-btn"
            disabled={!parent}
            title="Go to parent folder"
            onClick={() => parent && void loadDir(parent)}
          >
            ↑ Up
          </button>
          {archiveEntries && (
            <button
              type="button"
              className="text-btn"
              title="Return to folder listing"
              onClick={() => parent && void loadDir(parent)}
            >
              Back to folder
            </button>
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
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr
                  key={entry.path}
                  className={entry.is_dir ? "dir-row" : ""}
                  onDoubleClick={() => void openEntry(entry)}
                >
                  <td>
                    <button
                      type="button"
                      className="linkish-btn"
                      title={
                        entry.is_dir
                          ? "Open this folder"
                          : isArchiveName(entry.name)
                            ? "List archive contents without extracting"
                            : "File (double-click does nothing)"
                      }
                      onClick={() => void openEntry(entry)}
                    >
                      {entry.name}
                    </button>
                  </td>
                  <td>{entry.is_dir ? "Folder" : isArchiveName(entry.name) ? "Archive" : "File"}</td>
                  <td>{formatSize(entry.size)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </aside>
    </div>
  );
}
