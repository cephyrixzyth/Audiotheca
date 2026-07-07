import { PathLink } from "./PathLink";

export type ExecuteResultRow = {
  path: string;
  action: string;
  ok: boolean;
  detail?: string;
  error?: string;
};

interface Props {
  title: string;
  dryRun?: boolean;
  results: ExecuteResultRow[];
  staged?: number;
  failed?: number;
  okDryRunLabel?: string;
  okLiveLabel?: string;
}

function statusLabel(
  ok: boolean,
  dryRun?: boolean,
  okDryRunLabel = "Would move",
  okLiveLabel = "Moved",
): string {
  if (!ok) return "Failed";
  return dryRun ? okDryRunLabel : okLiveLabel;
}

function statusClass(ok: boolean): string {
  return ok ? "ready" : "review";
}

export function ExecuteResultsPanel({
  title,
  dryRun = false,
  results,
  staged,
  failed,
  okDryRunLabel,
  okLiveLabel,
}: Props) {
  if (!results.length) return null;

  const okCount = staged ?? results.filter((row) => row.ok).length;
  const failCount = failed ?? results.filter((row) => !row.ok).length;

  return (
    <section className="execute-results-panel panel-inset" aria-label={title}>
      <header className="execute-results-header">
        <h3>{title}</h3>
        <span className="count-muted">
          {dryRun ? "Dry run" : "Live"} · {okCount} ok
          {failCount ? ` · ${failCount} failed` : ""}
        </span>
      </header>
      <div className="execute-results-table-wrap">
        <table className="data-table compact execute-results-table">
          <thead>
            <tr>
              <th>Path</th>
              <th>Action</th>
              <th>Status</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {results.map((row) => (
              <tr key={`${row.path}:${row.action}`} className={row.ok ? "" : "row-failed"}>
                <td>
                  <PathLink path={row.path} />
                </td>
                <td>{row.action}</td>
                <td>
                  <span className={`badge ${statusClass(row.ok)}`}>
                    {statusLabel(row.ok, dryRun, okDryRunLabel, okLiveLabel)}
                  </span>
                </td>
                <td className="execute-results-detail">
                  {row.error ? (
                    <span className="error-text">{row.error}</span>
                  ) : (
                    row.detail ?? "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function duplicateExecuteRows(
  results: Array<{
    path: string;
    ok: boolean;
    dry_run?: boolean;
    staged_to?: string;
    error?: string;
  }>,
  dryRun: boolean,
): ExecuteResultRow[] {
  return results.map((row) => ({
    path: row.path,
    action: dryRun || row.dry_run ? "Preview stage" : "Stage discard",
    ok: row.ok,
    detail: row.ok && row.staged_to ? `→ ${row.staged_to}` : undefined,
    error: row.error,
  }));
}

export function restructureExecuteRows(
  results: Array<{
    path: string;
    ok: boolean;
    dry_run?: boolean;
    destination?: string;
    relative_dest?: string;
    error?: string;
  }>,
  dryRun: boolean,
): ExecuteResultRow[] {
  return results.map((row) => ({
    path: row.path,
    action: dryRun || row.dry_run ? "Preview move" : "Move",
    ok: row.ok,
    detail:
      row.ok && row.destination
        ? `→ ${row.relative_dest ?? row.destination}`
        : undefined,
    error: row.error,
  }));
}

export function sceneExecuteRows(
  results: Array<{
    path: string;
    ok: boolean;
    dry_run?: boolean;
    proposed_name?: string;
    destination?: string;
    error?: string;
  }>,
  dryRun: boolean,
): ExecuteResultRow[] {
  return results.map((row) => ({
    path: row.path,
    action: dryRun || row.dry_run ? "Preview rename" : "Rename",
    ok: row.ok,
    detail:
      row.ok && (row.proposed_name || row.destination)
        ? `→ ${row.proposed_name ?? row.destination}`
        : undefined,
    error: row.error,
  }));
}

export function archiveExecuteRows(
  results: Array<{
    path: string;
    ok: boolean;
    dry_run?: boolean;
    staged_to?: string;
    multipart?: boolean;
    error?: string;
  }>,
  dryRun: boolean,
): ExecuteResultRow[] {
  return results.map((row) => ({
    path: row.path,
    action: dryRun || row.dry_run ? "Preview stage" : "Stage archive",
    ok: row.ok,
    detail:
      row.ok && row.staged_to
        ? `→ ${row.staged_to}${row.multipart ? " (multipart)" : ""}`
        : undefined,
    error: row.error,
  }));
}
