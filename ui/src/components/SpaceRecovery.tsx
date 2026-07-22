import { useCallback, useEffect, useMemo, useState } from "react";
import {
  addUnderscoreVendors,
  bulkWhitelistAllUnderscore,
  fetchCoexistence,
  fetchSpaceRecoverySummary,
  fetchUnderscoreVendors,
  removeUnderscoreVendors,
  rescanUnderscorePaths,
  seedKnownUnderscoreVendors,
  spaceRecoveryReportDownload,
} from "../api/client";
import type { CoexistenceItem, JobSnapshot } from "../types";
import { PathLink } from "./PathLink";

interface Props {
  stamp: string;
}

interface UnderscoreRow {
  name: string;
  path: string;
  section: string;
  source: string;
  whitelisted: boolean;
}

export function SpaceRecovery({ stamp }: Props) {
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [underscore, setUnderscore] = useState<UnderscoreRow[]>([]);
  const [whitelistCount, setWhitelistCount] = useState(0);
  const [coexistence, setCoexistence] = useState<CoexistenceItem[]>([]);
  const [coexistenceTotal, setCoexistenceTotal] = useState(0);
  const [issueFilter, setIssueFilter] = useState("DEEP_INSTALLER");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState<JobSnapshot | null>(null);
  const [reportLinks, setReportLinks] = useState<Array<{ label: string; filename: string }>>([]);

  const reload = useCallback(() => {
    setError(null);
    fetchSpaceRecoverySummary(stamp)
      .then(setSummary)
      .catch((err: Error) => setError(err.message));
    fetchUnderscoreVendors(stamp)
      .then((res) => {
        setUnderscore(res.items);
        setWhitelistCount(res.whitelisted_count);
      })
      .catch(() => setUnderscore([]));
    fetchCoexistence(stamp, { issue_type: issueFilter, limit: 100 })
      .then((res) => {
        setCoexistence(res.items);
        setCoexistenceTotal(res.total);
      })
      .catch(() => {
        setCoexistence([]);
        setCoexistenceTotal(0);
      });
  }, [stamp, issueFilter]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    const offline = (summary?.offline_reports as {
      hardlink?: Array<{ stamp: string; csv: string }>;
      bloat?: Array<{ stamp: string; csv: string }>;
    }) || { hardlink: [], bloat: [] };
    const links: Array<{ label: string; filename: string }> = [];
    for (const row of offline.bloat?.slice(0, 3) || []) {
      links.push({ label: `Bloat report ${row.stamp}`, filename: row.csv });
    }
    for (const row of offline.hardlink?.slice(0, 3) || []) {
      links.push({ label: `Hardlink plan ${row.stamp}`, filename: row.csv });
    }
    setReportLinks(links);
  }, [summary]);

  const byIssue = useMemo(() => {
    const raw = (summary?.by_issue_type as Record<string, number>) || {};
    return Object.entries(raw).sort((a, b) => b[1] - a[1]);
  }, [summary]);

  async function toggleWhitelist(row: UnderscoreRow) {
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      if (row.whitelisted) {
        await removeUnderscoreVendors({ folders: [row.name], paths: [row.path] });
        setMsg(`Removed "${row.name}" from whitelist`);
      } else {
        await addUnderscoreVendors({ folders: [row.name], paths: [row.path] });
        setMsg(`Whitelisted "${row.name}" — rescan to include in target discovery`);
      }
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function bulkWhitelistAndRescan() {
    const paths = [...selected];
    if (!paths.length) return;
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      const res = await rescanUnderscorePaths(stamp, {
        paths,
        invalidate_cache: true,
        dry_run: true,
        full_library: true,
      });
      setJob(res.job);
      setMsg(
        `Whitelisted ${paths.length} folder(s) and started full-library dry scan — job ${res.job.job_id}. Check Dashboard when complete.`,
      );
      setSelected(new Set());
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSeedKnown() {
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      const res = await seedKnownUnderscoreVendors();
      setMsg(`Seeded ${res.added_folders.length} known vendor folder name(s) (${res.total_folders ?? "?"} total whitelisted)`);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleWhitelistAllAndScan() {
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      const res = await bulkWhitelistAllUnderscore(stamp, { dry_run: true, invalidate_cache: true });
      setJob(res.job);
      setMsg(
        `Whitelisted all ${res.count} discovered folder(s) and started full-library dry scan — job ${res.job.job_id}`,
      );
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function selectAllNonWhitelisted() {
    setSelected(new Set(underscore.filter((row) => !row.whitelisted).map((row) => row.path)));
  }

  function toggleSelect(path: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Space recovery</h2>
      <p className="count-muted" style={{ marginBottom: "1.25rem" }}>
        Reclaim disk from deep installers, archive siblings, and merge routes. Whitelist `_`-prefixed vendor
        folders so the engine scans them.
      </p>

      {error && <div className="error">{error}</div>}
      {msg && <div className="banner dry" style={{ marginBottom: "0.75rem" }}>{msg}</div>}
      {job && (
        <div className="count-muted" style={{ marginBottom: "0.75rem" }}>
          Rescan job {job.job_id} · {job.status}
          {job.stamp ? ` · stamp ${job.stamp}` : ""}
        </div>
      )}

      <section style={{ marginBottom: "1.5rem" }}>
        <h3>Coexistence summary</h3>
        <div className="kpi-grid" style={{ marginBottom: "1rem" }}>
          <div className="kpi">
            <div className="label">Total findings</div>
            <div className="value">{Number(summary?.total ?? 0).toLocaleString()}</div>
          </div>
          <div className="kpi">
            <div className="label">Deep installers</div>
            <div className="value">{Number(summary?.deep_installer_count ?? 0).toLocaleString()}</div>
          </div>
          <div className="kpi">
            <div className="label">Archive + extract sibling</div>
            <div className="value">{Number(summary?.archive_sibling_count ?? 0).toLocaleString()}</div>
          </div>
          <div className="kpi">
            <div className="label">Merge routes</div>
            <div className="value">{Number(summary?.merge_route_count ?? 0).toLocaleString()}</div>
          </div>
        </div>
        {byIssue.length > 0 && (
          <div className="bar-chart">
            {byIssue.map(([label, value]) => (
              <div key={label} className="bar-row">
                <span className="bar-label">{label}</span>
                <div className="bar-track">
                  <div
                    className="bar-fill"
                    style={{
                      width: `${Math.min(100, (value / Math.max(1, Number(summary?.total ?? 1))) * 100)}%`,
                    }}
                  />
                </div>
                <span className="bar-value">{value.toLocaleString()}</span>
              </div>
            ))}
          </div>
        )}
        <p className="count-muted" style={{ marginTop: "0.75rem" }}>
          Full hardlink / bloat analysis: run{" "}
          <code>python space_recovery.py --root &lt;library&gt;</code> from the project root (slow on network shares).
        </p>
        {reportLinks.length > 0 && (
          <div className="toolbar" style={{ marginTop: "0.5rem" }}>
            {reportLinks.map((link) => (
              <button
                key={link.filename}
                type="button"
                className="primary-btn"
                onClick={() => void spaceRecoveryReportDownload(link.filename)}
              >
                {link.label}
              </button>
            ))}
          </div>
        )}
      </section>

      <section style={{ marginBottom: "1.5rem" }}>
        <div className="toolbar">
          <h3 style={{ margin: 0 }}>Underscore vendor folders</h3>
          <span className="count-muted">
            {whitelistCount} whitelisted · {underscore.length} discovered
          </span>
        </div>
        <p className="count-muted">
          Folders like <code>_8Dio</code> are skipped during target discovery unless whitelisted. After whitelisting,
          run a <strong>full-library</strong> dry scan so route-ready metrics update.
        </p>
        <div className="toolbar">
          <button type="button" className="primary-btn" disabled={busy} onClick={() => void handleSeedKnown()}>
            Seed known vendors
          </button>
          <button
            type="button"
            className="primary-btn"
            disabled={busy || underscore.length === 0}
            onClick={() => void handleWhitelistAllAndScan()}
          >
            Whitelist all &amp; full dry scan
          </button>
          <button type="button" disabled={busy} onClick={selectAllNonWhitelisted}>
            Select non-whitelisted
          </button>
          <button
            type="button"
            className="primary-btn"
            disabled={busy || selected.size === 0}
            onClick={() => void bulkWhitelistAndRescan()}
          >
            Whitelist selected &amp; full dry scan ({selected.size})
          </button>
        </div>
        <div className="table-wrap">
          <table className="data-table compact">
            <thead>
              <tr>
                <th />
                <th>Folder</th>
                <th>Section</th>
                <th>Source</th>
                <th>Status</th>
                <th>Path</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {underscore.map((row) => (
                <tr key={row.path} className={row.whitelisted ? "row-ok" : ""}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selected.has(row.path)}
                      onChange={() => toggleSelect(row.path)}
                      aria-label={`Select ${row.name}`}
                    />
                  </td>
                  <td>{row.name}</td>
                  <td>{row.section}</td>
                  <td>{row.source}</td>
                  <td>{row.whitelisted ? "Whitelisted" : "Skipped"}</td>
                  <td>
                    <PathLink path={row.path} />
                  </td>
                  <td>
                    <button type="button" className="link-btn" disabled={busy} onClick={() => void toggleWhitelist(row)}>
                      {row.whitelisted ? "Remove" : "Whitelist"}
                    </button>
                  </td>
                </tr>
              ))}
              {underscore.length === 0 && (
                <tr>
                  <td colSpan={7} className="empty-cell">
                    No `_`-prefixed vendor folders found for this run.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <div className="toolbar">
          <h3 style={{ margin: 0 }}>Coexistence queue</h3>
          <label>
            Issue type
            <select value={issueFilter} onChange={(e) => setIssueFilter(e.target.value)}>
              <option value="DEEP_INSTALLER">DEEP_INSTALLER</option>
              <option value="ARCHIVE_EXTRACTED_SIBLING">ARCHIVE_EXTRACTED_SIBLING</option>
              <option value="">All types</option>
            </select>
          </label>
        </div>
        <p className="count-muted">
          Showing {coexistence.length} of {coexistenceTotal.toLocaleString()}
        </p>
        <div className="table-wrap">
          <table className="data-table compact">
            <thead>
              <tr>
                <th>Item</th>
                <th>Section</th>
                <th>Archive / installer</th>
                <th>Extracted</th>
                <th>Suggested action</th>
                <th>Path</th>
              </tr>
            </thead>
            <tbody>
              {coexistence.map((row) => (
                <tr key={`${row.item_path}-${row.archive_or_installer}`}>
                  <td>{row.item_name}</td>
                  <td>{row.section}</td>
                  <td>{row.archive_or_installer.split(/[/\\]/).pop()}</td>
                  <td>{row.extracted_folder || "—"}</td>
                  <td className="truncate" title={row.suggested_action}>
                    {row.suggested_action}
                  </td>
                  <td>
                    <PathLink path={row.item_path} />
                  </td>
                </tr>
              ))}
              {coexistence.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty-cell">
                    No rows for this filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
