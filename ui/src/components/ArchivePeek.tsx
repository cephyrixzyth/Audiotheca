import { useEffect, useState } from "react";
import {
  confirmArchiveDelete,
  executeArchiveStaging,
  fetchArchiveFeedback,
  fetchArchivePeek,
  rejectArchiveVerdict,
  setArchiveKeeper,
} from "../api/client";
import type { ArchivePeekItem } from "../types";
import { Badge, Button, Kpi } from "../ui";
import { useLibraryRoot } from "../hooks/useLibraryRoot";
import { lookupByPath, pathKey } from "../utils/pathKey";
import { ArchiveDiffWizard } from "./ArchiveDiffWizard";
import {
  archiveExecuteRows,
  ExecuteResultsPanel,
  type ExecuteResultRow,
} from "./ExecuteResultsPanel";
import { PathLink } from "./PathLink";
import { useContextSidebar } from "./ContextSidebar";

const VERDICT_LABELS: Record<string, string> = {
  MATCHES_EXTRACTED_FOLDER: "Matches extracted folder",
  NO_TOP_LEVEL_ARCHIVE: "No top-level archive",
  LOOKS_LIKE_PRODUCT: "Looks like product",
  NEEDS_7ZIP: "Needs 7-Zip",
  DISK_IMAGE_ISO: "ISO disk image",
  NO_MULTIPART_ARCHIVES: "Not multipart RAR",
  SINGLE_ARCHIVE_ONLY: "Single archive only",
  SCENE_CRACK_JUNK: "Scene / crack junk",
  UNKNOWN_CONTENT: "Unknown content",
};

function verdictLabel(code: string): string {
  return VERDICT_LABELS[code] ?? code.replaceAll("_", " ").toLowerCase();
}

interface Props {
  stamp: string;
}

export function ArchivePeek({ stamp }: Props) {
  const libraryRoot = useLibraryRoot();
  const { query } = useContextSidebar();
  const [items, setItems] = useState<ArchivePeekItem[]>([]);
  const [total, setTotal] = useState(0);
  const [verdictCounts, setVerdictCounts] = useState<Record<string, number>>({});
  const [deleteFiles, setDeleteFiles] = useState(0);
  const [deleteMb, setDeleteMb] = useState(0);
  const [verdict, setVerdict] = useState("");
  const [loading, setLoading] = useState(true);
  const [rejected, setRejected] = useState<Record<string, string>>({});
  const [confirmed, setConfirmed] = useState<Record<string, string>>({});
  const [keepers, setKeepers] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [diffRow, setDiffRow] = useState<ArchivePeekItem | null>(null);
  const [executeResults, setExecuteResults] = useState<ExecuteResultRow[]>([]);
  const [executeDryRun, setExecuteDryRun] = useState(true);
  const [executeSummary, setExecuteSummary] = useState<{ staged: number; failed: number } | null>(
    null,
  );

  async function refreshFeedback() {
    const state = await fetchArchiveFeedback(stamp);
    setRejected(state.rejected_archives ?? {});
    setConfirmed(state.confirmed_deletes ?? {});
    setKeepers(state.keeper_choice ?? {});
  }

  useEffect(() => {
    refreshFeedback().catch(() => {
      setRejected({});
      setConfirmed({});
      setKeepers({});
    });
  }, [stamp]);

  useEffect(() => {
    setLoading(true);
    const timer = setTimeout(() => {
      fetchArchivePeek(stamp, {
        verdict: verdict || undefined,
        q: query || undefined,
        limit: 200,
      })
        .then((res) => {
          setItems(res.items);
          setTotal(res.total);
          setVerdictCounts(res.verdict_counts);
          setDeleteFiles(res.delete_candidate_files);
          setDeleteMb(res.delete_candidate_mb);
        })
        .finally(() => setLoading(false));
    }, query ? 250 : 0);
    return () => clearTimeout(timer);
  }, [stamp, verdict, query]);

  async function handleReject(row: ArchivePeekItem) {
    try {
      await rejectArchiveVerdict(stamp, {
        archive_path: row.archive_path,
        archive_name: row.archive_name,
        item_name: row.item_name,
        reason: "not_redundant",
      });
      await refreshFeedback();
      setMsg(`Marked ${row.archive_name} as not redundant`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Reject failed");
    }
  }

  async function handleConfirm(row: ArchivePeekItem) {
    try {
      await confirmArchiveDelete(stamp, {
        archive_path: row.archive_path,
        archive_name: row.archive_name,
        item_name: row.item_name,
      });
      await refreshFeedback();
      setMsg(`Confirmed delete for ${row.archive_name}`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Confirm failed");
    }
  }

  async function handleKeeper(row: ArchivePeekItem, keeper: "archive" | "folder") {
    try {
      await setArchiveKeeper(stamp, {
        archive_path: row.archive_path,
        keeper,
        archive_name: row.archive_name,
        item_name: row.item_name,
      });
      await refreshFeedback();
      setMsg(`Keeper set to ${keeper} for ${row.archive_name}`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Keeper update failed");
    }
  }

  async function handleExecute(dryRun: boolean, confirmLive = false) {
    try {
      const res = await executeArchiveStaging(stamp, {
        dry_run: dryRun,
        confirm_live: confirmLive || undefined,
        root: libraryRoot || undefined,
      });
      if (!res.ok && !(res as { partial?: boolean }).partial && !res.results?.length) {
        setExecuteResults([]);
        setExecuteSummary(null);
        setMsg(res.error ?? "Confirm archive rows first, then preview staging");
        return;
      }
      setExecuteDryRun(dryRun);
      setExecuteResults(
        archiveExecuteRows(
          (res.results ?? []) as Array<{
            path: string;
            ok: boolean;
            dry_run?: boolean;
            staged_to?: string;
            multipart?: boolean;
            error?: string;
          }>,
          dryRun,
        ),
      );
      setExecuteSummary({ staged: res.staged, failed: res.failed });
      const partial = Boolean((res as { partial?: boolean }).partial);
      const outcome = partial ? "partial" : res.ok ? "ok" : "failed";
      setMsg(
        dryRun
          ? `Dry run (${outcome}): ${res.staged} archive(s) would stage to _delete-canidates`
          : `Live (${outcome}): ${res.staged} archive(s) staged (${res.failed} failed)`,
      );
      if (!dryRun) {
        await refreshFeedback();
      }
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Execute failed");
    }
  }

  const confirmedCount = Object.keys(confirmed).length;

  return (
    <div>
      {diffRow && diffRow.extracted_folder && (
        <ArchiveDiffWizard
          stamp={stamp}
          row={diffRow}
          archivePath={diffRow.archive_path}
          folderPath={diffRow.extracted_folder}
          onClose={() => setDiffRow(null)}
        />
      )}
      <div className="kpi-grid" style={{ marginBottom: "1rem" }}>
        <Kpi label="Delete candidates" value={deleteFiles} />
        <Kpi label="Recoverable" value={`${(deleteMb / 1024).toFixed(1)} GB`} />
        <Kpi label="Confirmed" value={confirmedCount} />
      </div>

      <div className="toolbar" style={{ marginBottom: "1rem" }}>
        <Button
          variant="secondary"
          title="Simulate staging confirmed archives to _delete-canidates without moving files"
          onClick={() => void handleExecute(true)}
        >
          Dry-run confirmed
        </Button>
        <Button
          variant="primary"
          title="Move confirmed redundant archives to _delete-canidates on the library share"
          onClick={() => {
            if (
              window.confirm(
                "Stage confirmed archives to _delete-canidates? Files will be moved on disk.",
              )
            ) {
              void handleExecute(false, true);
            }
          }}
          disabled={confirmedCount === 0}
        >
          Stage confirmed ({confirmedCount})
        </Button>
        {msg && <span className="count-muted">{msg}</span>}
      </div>

      {executeResults.length > 0 && (
        <ExecuteResultsPanel
          title="Archive staging results"
          dryRun={executeDryRun}
          results={executeResults}
          staged={executeSummary?.staged}
          failed={executeSummary?.failed}
        />
      )}

      <div className="bucket-grid" style={{ marginBottom: "1rem" }}>
        {Object.entries(verdictCounts).map(([name, count]) => (
          <button
            key={name}
            type="button"
            className={`bucket-chip ${verdict === name ? "active-chip" : ""}`}
            title={`Filter rows with verdict ${verdictLabel(name)}`}
            onClick={() => setVerdict(name)}
          >
            {verdictLabel(name)}
            <strong>{count}</strong>
          </button>
        ))}
        <button
          type="button"
          className={`bucket-chip ${verdict === "" ? "active-chip" : ""}`}
          title="Show all archive verdicts"
          onClick={() => setVerdict("")}
        >
          All
        </button>
      </div>

      <div className="toolbar">
        <span className="count-muted">
          {loading ? "Loading…" : `${total} archive rows`}
        </span>
      </div>

      {items.length === 0 && !loading && (
        <div className="empty">No archive peek rows for this filter.</div>
      )}

      {items.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Verdict</th>
              <th>Item</th>
              <th>Archive</th>
              <th>Size</th>
              <th>Extracted folder</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => {
              const isRejected = lookupByPath(rejected, row.archive_path) != null;
              const isConfirmed = lookupByPath(confirmed, row.archive_path) != null;
              const keeper = lookupByPath(keepers, row.archive_path);
              return (
                <tr key={pathKey(row.archive_path)}>
                  <td>
                    <Badge
                      tone={row.verdict === "MATCHES_EXTRACTED_FOLDER" ? "ready" : "accent"}
                      title={row.verdict}
                    >
                      {verdictLabel(row.verdict)}
                    </Badge>
                    {isRejected && <Badge tone="accent">rejected</Badge>}
                    {isConfirmed && <Badge tone="ready">confirmed</Badge>}
                    {keeper && <Badge tone="accent">keep {keeper}</Badge>}
                  </td>
                  <td>
                    <div>{row.item_name}</div>
                    <PathLink path={row.item_path} secondaryPath={row.archive_path} dualPane />
                  </td>
                  <td>
                    <div>{row.archive_name}</div>
                    <PathLink path={row.archive_path} />
                  </td>
                  <td>{row.archive_size_mb != null ? `${row.archive_size_mb} MB` : "—"}</td>
                  <td>{row.extracted_folder}</td>
                  <td>
                    {row.extracted_folder ? (
                      <Button
                        variant="secondary"
                        size="sm"
                        title="Compare archive listing vs extracted folder side by side"
                        onClick={() => setDiffRow(row)}
                      >
                        Diff
                      </Button>
                    ) : (
                      <span className="count-muted">—</span>
                    )}{" "}
                    {row.verdict === "MATCHES_EXTRACTED_FOLDER" && !isRejected && (
                      <>
                        <Button
                          variant="secondary"
                          size="sm"
                          title="Mark this archive safe to delete — extracted folder is a match"
                          onClick={() => void handleConfirm(row)}
                        >
                          Confirm delete
                        </Button>{" "}
                        <Button
                          variant="secondary"
                          size="sm"
                          title="Archive is not redundant — engine will skip it on future scans"
                          onClick={() => void handleReject(row)}
                        >
                          Not redundant
                        </Button>{" "}
                        <Button
                          variant="secondary"
                          size="sm"
                          title="Keep the extracted folder and prefer deleting the archive later"
                          onClick={() => void handleKeeper(row, "folder")}
                        >
                          Keep folder
                        </Button>{" "}
                        <Button
                          variant="secondary"
                          size="sm"
                          title="Keep the archive file and treat the extracted folder as disposable"
                          onClick={() => void handleKeeper(row, "archive")}
                        >
                          Keep archive
                        </Button>
                      </>
                    )}
                    {isRejected && <span className="count-muted">Skipped next run</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
