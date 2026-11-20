import { WorkDialog, WorkIssue } from "./ReviewWorkbench";
import { LoadingStatus } from "../ui/LoadingStatus";
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
  onDecision?: () => Promise<void>;
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
  onDecision, onClose,
}: Props) {
  const [data, setData] = useState<ArchiveDiffResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [working, setWorking] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(null);
    fetchArchiveDiff(stamp, { archive_path: archivePath, folder_path: folderPath })
      .then(next => { if (current) setData(next); })
      .catch((err: Error) => { if (current) setError(err.message || "Failed to load diff"); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [stamp, archivePath, folderPath, revision]);

  async function record(action: () => Promise<void>) {
    setWorking(true);
    try { await action(); await onDecision?.(); }
    catch (cause) { setMsg(cause instanceof Error ? cause.message : "Could not record decision"); }
    finally { setWorking(false); }
  }

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
    setMsg("Approved archive for staging");
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
    <WorkDialog wide title="Compare archive contents" detail={title} close={onClose}>
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

        {loading && <LoadingStatus>Loading diff…</LoadingStatus>}
        {error && <WorkIssue message={error} retry={() => setRevision(v => v + 1)} />}

        {!loading && !error && data && (
          <>
            <div className="archive-diff-summary">
              <Badge tone={data.complete ? "neutral" : "review"}>{data.complete ? "Inventory complete" : "Partial inventory"}</Badge>
              <span className="count-muted">
                {data.matched.length} matching paths · {data.checksums_checked ?? 0} file checksums checked · {data.only_in_archive.length} only in archive · {data.only_on_disk.length} only on disk
              </span>
              {data.report_verdict && <span className="count-muted">Earlier scan: {data.report_verdict}</span>}
              {data.folder_error && <span className="error">{data.folder_error}</span>}
              {Boolean(data.different_contents?.length) && <p className="error">Different contents: {data.different_contents?.join(", ")}</p>}
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
                    data.only_in_archive.map((name, index) => <li key={`${index}:${name}`}>{name}</li>)
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
                    data.only_on_disk.map((name, index) => <li key={`${index}:${name}`}>{name}</li>)
                  )}
                </ul>
              </section>
            </div>

            <div className="toolbar">
              <Button variant="secondary" disabled={working || !data.complete || !data.matched.length || Boolean(data.only_in_archive.length || data.different_contents?.length)} onClick={() => void record(handleConfirm)}>
                Approve archive for staging
              </Button>
              <Button variant="secondary" disabled={working} onClick={() => void record(handleReject)}>
                Not redundant
              </Button>
              <Button variant="secondary" disabled={working} onClick={() => void record(() => handleKeeper("folder"))}>
                Keep folder
              </Button>
              <Button variant="secondary" disabled={working} onClick={() => void record(() => handleKeeper("archive"))}>
                Keep archive
              </Button>
              {msg && <span className="count-muted" role="status">{msg}</span>}
            </div>
          </>
        )}
    </WorkDialog>
  );
}
