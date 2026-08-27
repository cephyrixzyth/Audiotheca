import { useEffect, useState } from "react";

import {
  confirmArchiveDelete,
  fetchArchiveDiff,
  rejectArchiveVerdict,
  setArchiveKeeper,
} from "../api/client";
import type { ArchiveDiffResponse, ArchivePeekItem } from "../types";
import { Badge, Button } from "../ui";

import { PathLink } from "./PathLink";

interface Props {
  stamp: string;
  row?: ArchivePeekItem | null;
  archivePath: string;
  folderPath: string;
  archiveName?: string;
  itemName?: string;
  onClose: () => void;
}

function formatSize(size: number | null | undefined): string {
  if (size == null) return "—";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function ArchiveDiffWizard({
  stamp,
  row,
  archivePath,
  folderPath,
  archiveName,
  itemName,
  onClose,
}: Props) {
  const [data, setData] = useState<ArchiveDiffResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchArchiveDiff(stamp, { archive_path: archivePath, folder_path: folderPath })
      .then(setData)
      .catch((err: Error) => setError(err.message || "Failed to load diff"))
      .finally(() => setLoading(false));
  }, [stamp, archivePath, folderPath]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  async function handleReject() {
    await rejectArchiveVerdict(stamp, {
      archive_path: archivePath,
      archive_name: archiveName ?? row?.archive_name ?? "",
      item_name: itemName ?? row?.item_name ?? "",
      reason: "not_redundant",
    });
    setMsg("Marked as not redundant");
  }

  async function handleConfirm() {
    await confirmArchiveDelete(stamp, {
      archive_path: archivePath,
      archive_name: archiveName ?? row?.archive_name ?? "",
      item_name: itemName ?? row?.item_name ?? "",
    });
    setMsg("Confirmed safe to delete archive");
  }

  async function handleKeeper(keeper: "archive" | "folder") {
    await setArchiveKeeper(stamp, {
      archive_path: archivePath,
      keeper,
      archive_name: archiveName ?? row?.archive_name ?? "",
      item_name: itemName ?? row?.item_name ?? "",
    });
    setMsg(`Keeper set to ${keeper}`);
  }

  const title = archiveName ?? row?.archive_name ?? archivePath.split(/[/\\]/).pop() ?? "Archive";

  return (
    <div className="file-explorer-backdrop" onClick={onClose} role="presentation">
      <div
        className="archive-diff-wizard"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Archive diff wizard"
      >
        <header className="archive-diff-header">
          <div>
            <h2>Archive diff</h2>
            <p className="count-muted">{title}</p>
          </div>
          <Button variant="ghost" onClick={onClose} title="Close (Esc)">
            Close
          </Button>
        </header>

        <div className="archive-diff-paths">
          <div>
            <span className="label">Archive</span>
            <PathLink path={archivePath} />
          </div>
          <div>
            <span className="label">Extracted folder</span>
            <PathLink path={folderPath} />
          </div>
        </div>

        {loading && <div className="empty">Loading diff…</div>}
        {error && <div className="empty">{error}</div>}

        {!loading && !error && data && (
          <>
            <div className="archive-diff-summary">
              <Badge tone={data.verdict_hint === "MATCHES_EXTRACTED_FOLDER" ? "ready" : "accent"}>
                {data.verdict_hint}
              </Badge>
              <span className="count-muted">
                {data.matched.length} matched · {data.only_in_archive.length} only in archive ·{" "}
                {data.only_on_disk.length} only on disk
              </span>
              {data.archive_error && (
                <span className="count-muted">Archive list: {data.archive_error}</span>
              )}
            </div>

            <div className="archive-diff-columns">
              <section>
                <h3>Only in archive</h3>
                <ul className="archive-diff-list">
                  {data.only_in_archive.length === 0 ? (
                    <li className="count-muted">—</li>
                  ) : (
                    data.only_in_archive.map((name) => <li key={name}>{name}</li>)
                  )}
                </ul>
              </section>
              <section>
                <h3>Matched</h3>
                <ul className="archive-diff-list">
                  {data.matched.length === 0 ? (
                    <li className="count-muted">—</li>
                  ) : (
                    data.matched.map((rowMatch) => (
                      <li key={rowMatch.name}>
                        {rowMatch.name}
                        <span className="count-muted">
                          {" "}
                          ({formatSize(rowMatch.size_archive)} / {formatSize(rowMatch.size_disk)})
                        </span>
                      </li>
                    ))
                  )}
                </ul>
              </section>
              <section>
                <h3>Only on disk</h3>
                <ul className="archive-diff-list">
                  {data.only_on_disk.length === 0 ? (
                    <li className="count-muted">—</li>
                  ) : (
                    data.only_on_disk.map((name) => <li key={name}>{name}</li>)
                  )}
                </ul>
              </section>
            </div>

            <div className="toolbar">
              <Button variant="secondary" onClick={() => void handleConfirm()}>
                Confirm delete archive
              </Button>
              <Button variant="secondary" onClick={() => void handleReject()}>
                Not redundant
              </Button>
              <Button variant="secondary" onClick={() => void handleKeeper("folder")}>
                Keep folder
              </Button>
              <Button variant="secondary" onClick={() => void handleKeeper("archive")}>
                Keep archive
              </Button>
              {msg && <span className="count-muted">{msg}</span>}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
