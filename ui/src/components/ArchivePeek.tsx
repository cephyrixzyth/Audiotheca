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
import { useLibraryRoot } from "../hooks/useLibraryRoot";
import { ArchiveDiffWizard } from "./ArchiveDiffWizard";
import {
  archiveExecuteRows,
  ExecuteResultsPanel,
  type ExecuteResultRow,
} from "./ExecuteResultsPanel";
import { PathLink } from "./PathLink";
import { useContextSidebar } from "./ContextSidebar";

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
  const [verdict, setVerdict] = useState("MATCHES_EXTRACTED_FOLDER");
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

  useEffect(() => {
    fetchArchiveFeedback(stamp)
      .then((state) => {
        setRejected(state.rejected_archives ?? {});
        setConfirmed(state.confirmed_deletes ?? {});
        setKeepers(state.keeper_choice ?? {});
      })
      .catch(() => {
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
    await rejectArchiveVerdict(stamp, {
      archive_path: row.archive_path,
      archive_name: row.archive_name,
      item_name: row.item_name,
      reason: "not_redundant",
    });
    setRejected((prev) => ({ ...prev, [row.archive_path]: "not_redundant" }));
    setConfirmed((prev) => {
      const next = { ...prev };
      delete next[row.archive_path];
      return next;
    });
    setMsg(`Marked ${row.archive_name} as not redundant`);
  }

  async function handleConfirm(row: ArchivePeekItem) {
    await confirmArchiveDelete(stamp, {
      archive_path: row.archive_path,
      archive_name: row.archive_name,
      item_name: row.item_name,
    });
    setConfirmed((prev) => ({ ...prev, [row.archive_path]: stamp }));
    setMsg(`Confirmed delete for ${row.archive_name}`);
  }

  async function handleKeeper(row: ArchivePeekItem, keeper: "archive" | "folder") {
    await setArchiveKeeper(stamp, {
      archive_path: row.archive_path,
      keeper,
      archive_name: row.archive_name,
      item_name: row.item_name,
    });
    setKeepers((prev) => ({ ...prev, [row.archive_path]: keeper }));
    setMsg(`Keeper set to ${keeper} for ${row.archive_name}`);
  }

  async function handleExecute(dryRun: boolean, confirmLive = false) {
    const res = await executeArchiveStaging(stamp, {
      dry_run: dryRun,
      confirm_live: confirmLive || undefined,
      root: libraryRoot || undefined,
    });
    if (!res.ok && !res.results?.length) {
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
    setMsg(
      dryRun
        ? `Dry run: ${res.staged} archive(s) would stage to _delete-canidates`
        : `Live: ${res.staged} archive(s) staged (${res.failed} failed)`,
    );
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
        <div className="kpi">
          <div className="label">Delete candidates</div>
          <div className="value">{deleteFiles}</div>
        </div>
        <div className="kpi">
          <div className="label">Recoverable</div>
          <div className="value">{(deleteMb / 1024).toFixed(1)} GB</div>
        </div>
        <div className="kpi">
          <div className="label">Confirmed</div>
          <div className="value">{confirmedCount}</div>
        </div>
      </div>

      <div className="toolbar" style={{ marginBottom: "1rem" }}>
        <button
          type="button"
          className="keeper-btn"
          title="Simulate staging confirmed archives to _delete-canidates without moving files"
          onClick={() => void handleExecute(true)}
        >
          Dry-run confirmed
        </button>
        <button
          type="button"
          className="primary-btn"
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
        </button>
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
            title={`Filter rows with verdict ${name}`}
            onClick={() => setVerdict(name)}
          >
            {name}
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
              const isRejected = row.archive_path in rejected;
              const isConfirmed = row.archive_path in confirmed;
              const keeper = keepers[row.archive_path];
              return (
                <tr key={row.archive_path}>
                  <td>
                    <span
                      className={`badge ${
                        row.verdict === "MATCHES_EXTRACTED_FOLDER" ? "ready" : "bucket"
                      }`}
                    >
                      {row.verdict}
                    </span>
                    {isRejected && <span className="badge bucket">rejected</span>}
                    {isConfirmed && <span className="badge ready">confirmed</span>}
                    {keeper && <span className="badge bucket">keep {keeper}</span>}
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
                      <button
                        type="button"
                        className="keeper-btn"
                        title="Compare archive listing vs extracted folder side by side"
                        onClick={() => setDiffRow(row)}
                      >
                        Diff
                      </button>
                    ) : (
                      <span className="count-muted">—</span>
                    )}{" "}
                    {row.verdict === "MATCHES_EXTRACTED_FOLDER" && !isRejected && (
                      <>
                        <button
                          type="button"
                          className="keeper-btn"
                          title="Mark this archive safe to delete — extracted folder is a match"
                          onClick={() => void handleConfirm(row)}
                        >
                          Confirm delete
                        </button>{" "}
                        <button
                          type="button"
                          className="keeper-btn"
                          title="Archive is not redundant — engine will skip it on future scans"
                          onClick={() => void handleReject(row)}
                        >
                          Not redundant
                        </button>{" "}
                        <button
                          type="button"
                          className="keeper-btn"
                          title="Keep the extracted folder and prefer deleting the archive later"
                          onClick={() => void handleKeeper(row, "folder")}
                        >
                          Keep folder
                        </button>{" "}
                        <button
                          type="button"
                          className="keeper-btn"
                          title="Keep the archive file and treat the extracted folder as disposable"
                          onClick={() => void handleKeeper(row, "archive")}
                        >
                          Keep archive
                        </button>
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
