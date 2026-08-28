import { useCallback, useEffect, useState } from "react";
import {
  compareRuns,
  fetchCacheHits,
  fetchCoexistence,
  fetchCoverageGaps,
  fetchInventory,
  fetchNestedIssues,
  fetchProbeTruncations,
  fetchScanFailures,
  fetchSkipImpact,
  fetchSkippedItems,
  invalidateCache,
  queueSkippedInvestigation,
  rescanPaths,
} from "../api/client";
import type {
  CacheHitItem,
  CoexistenceItem,
  CoverageGapItem,
  InventoryItem,
  NestedIssueItem,
  ProbeTruncationItem,
  RunComparison,
  RunListItem,
  ScanFailureItem,
  SkipPhaseImpact,
  SkippedItem,
} from "../types";
import { Button, LabeledSelect, Tabs, VirtualTable } from "../ui";
import { PathLink } from "./PathLink";
import { useContextSidebar } from "./ContextSidebar";

interface Props {
  stamp: string;
  runs: RunListItem[];
}

type SubView =
  | "hub"
  | "failures"
  | "coverage"
  | "cache"
  | "nested"
  | "coexistence"
  | "inventory"
  | "truncations"
  | "compare";

const REASON_LABELS: Record<string, string> = {
  SCAN_FAILED: "Scan failed",
  CACHE_HIT: "Cache hit",
  LOOSE_FILE: "Loose file",
  LOOSE_ARCHIVE: "Loose archive",
  NOT_A_TARGET: "Not a target",
  NESTED_NOT_TARGET: "Nested not target",
  CONTENT_CHECK_SKIPPED: "Content check skipped",
  FEEDBACK_SKIPPED: "Feedback skipped",
  SKIPPED_BY_USER: "Skipped by user",
};

export function SkippedFiles({ stamp, runs }: Props) {
  const { query } = useContextSidebar();
  const [view, setView] = useState<SubView>("hub");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const [skipped, setSkipped] = useState<SkippedItem[]>([]);
  const [skippedTotal, setSkippedTotal] = useState(0);
  const [counts, setCounts] = useState<Record<string, number>>({});

  const [failures, setFailures] = useState<ScanFailureItem[]>([]);
  const [gaps, setGaps] = useState<CoverageGapItem[]>([]);
  const [cacheHits, setCacheHits] = useState<CacheHitItem[]>([]);
  const [nested, setNested] = useState<NestedIssueItem[]>([]);
  const [coexistence, setCoexistence] = useState<CoexistenceItem[]>([]);
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [truncations, setTruncations] = useState<ProbeTruncationItem[]>([]);
  const [skipImpact, setSkipImpact] = useState<SkipPhaseImpact[]>([]);

  const [compareA, setCompareA] = useState(stamp);
  const [compareB, setCompareB] = useState(runs[1]?.stamp ?? stamp);
  const [comparison, setComparison] = useState<RunComparison | null>(null);

  const loadHub = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetchSkippedItems(stamp, { reason: reason || undefined, q: query || undefined, limit: 500 }),
      fetchSkipImpact(stamp),
    ])
      .then(([skippedRes, impactRes]) => {
        setSkipped(skippedRes.items);
        setSkippedTotal(skippedRes.total);
        setCounts(skippedRes.counts);
        setSkipImpact(impactRes.phases);
      })
      .finally(() => setLoading(false));
  }, [stamp, reason, query]);

  useEffect(() => {
    if (view === "hub") loadHub();
  }, [view, loadHub]);

  useEffect(() => {
    if (view === "failures") {
      setLoading(true);
      fetchScanFailures(stamp, { q: query || undefined, limit: 500 })
        .then((r) => setFailures(r.items))
        .finally(() => setLoading(false));
    } else if (view === "coverage") {
      setLoading(true);
      fetchCoverageGaps(stamp, { q: query || undefined, limit: 500 })
        .then((r) => setGaps(r.items))
        .finally(() => setLoading(false));
    } else if (view === "cache") {
      setLoading(true);
      fetchCacheHits(stamp, { q: query || undefined, limit: 500 })
        .then((r) => setCacheHits(r.items))
        .finally(() => setLoading(false));
    } else if (view === "nested") {
      setLoading(true);
      fetchNestedIssues(stamp, { q: query || undefined, limit: 500 })
        .then((r) => setNested(r.items))
        .finally(() => setLoading(false));
    } else if (view === "coexistence") {
      setLoading(true);
      fetchCoexistence(stamp, { q: query || undefined, limit: 500 })
        .then((r) => setCoexistence(r.items))
        .finally(() => setLoading(false));
    } else if (view === "inventory") {
      setLoading(true);
      fetchInventory(stamp, { q: query || undefined, limit: 500 })
        .then((r) => setInventory(r.items))
        .finally(() => setLoading(false));
    } else if (view === "truncations") {
      setLoading(true);
      fetchProbeTruncations(stamp, { q: query || undefined, limit: 500 })
        .then((r) => setTruncations(r.items))
        .finally(() => setLoading(false));
    }
  }, [view, stamp, query]);

  function toggleSelect(path: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  async function handleRescanSelected() {
    const paths = [...selected].filter(Boolean);
    if (!paths.length) return;
    try {
      await invalidateCache(paths);
      const res = await rescanPaths(stamp, { paths, invalidate_cache: true, dry_run: true });
      setMsg(`Rescan job started: ${res.job.job_id}`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Rescan failed");
    }
  }

  async function handleQueueInvestigation() {
    const paths = [...selected].filter(Boolean);
    if (!paths.length) return;
    try {
      const res = await queueSkippedInvestigation(stamp, { paths, bucket: "_manual_rescan" });
      setMsg(`Queued ${res.applied} path(s) for investigation`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Queue failed");
    }
  }

  async function handleCompare() {
    setLoading(true);
    try {
      const res = await compareRuns(compareA, compareB);
      setComparison(res);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Compare failed");
    } finally {
      setLoading(false);
    }
  }

  const subTabs: { id: SubView; label: string; title?: string }[] = [
    { id: "hub", label: "All skipped", title: "Every skipped or deferred path with reason codes" },
    { id: "failures", label: "Scan failures", title: "Paths where the scan phase threw or timed out" },
    { id: "coverage", label: "Coverage gaps", title: "Library areas not reached by the last scan pass" },
    { id: "cache", label: "Cache hits", title: "Items skipped because fingerprint cache said unchanged" },
    { id: "nested", label: "Nested issues", title: "Archives or folders nested inside other products" },
    { id: "coexistence", label: "Coexistence", title: "Archive and extracted folder both present — needs archive peek" },
    { id: "inventory", label: "Inventory", title: "Loose files and unpackaged items outside normal routes" },
    { id: "truncations", label: "Probe limits", title: "Paths cut off by max depth or size probe limits" },
    { id: "compare", label: "Compare runs", title: "Diff skipped sets between two scan stamps" },
  ];

  return (
    <div>
      <div className="banner dry">
        Skipped &amp; uncovered files — scan failures, cache hits, coverage gaps, phase skips, and probe
        depth limits. Select rows to force rescan or queue for investigation.
      </div>

      <Tabs
        aria-label="Skipped file views"
        value={view}
        onValueChange={(next) => setView(next as SubView)}
        items={subTabs.map((t) => ({
          value: t.id,
          label: t.label,
          title: t.title,
        }))}
      />

      {view !== "compare" && (
        <div className="toolbar">
          {view === "hub" && (
            <select
              className="field-input"
              aria-label="Filter by skip reason"
              value={reason}
              title="Filter by why the engine skipped or deferred this path"
              onChange={(e) => setReason(e.target.value)}
            >
              <option value="">All reasons</option>
              {Object.entries(counts).map(([key, n]) => (
                <option key={key} value={key}>
                  {REASON_LABELS[key] ?? key} ({n})
                </option>
              ))}
            </select>
          )}
          {selected.size > 0 && (
            <>
              <Button
                variant="primary"
                title="Force a targeted rescan of selected paths on the next run"
                onClick={handleRescanSelected}
              >
                Rescan selected ({selected.size})
              </Button>
              <Button
                variant="secondary"
                title="Send selected paths to the investigation inbox"
                onClick={handleQueueInvestigation}
              >
                Queue investigation
              </Button>
            </>
          )}
        </div>
      )}

      {msg && (
        <div className="banner" style={{ marginBottom: "0.75rem" }}>
          {msg}
          <Button variant="secondary" size="sm" style={{ marginLeft: "0.5rem" }} onClick={() => setMsg(null)}>
            Dismiss
          </Button>
        </div>
      )}

      {skipImpact.length > 0 && view === "hub" && (
        <div className="banner" style={{ marginBottom: "0.75rem" }}>
          Phase skip impact:{" "}
          {skipImpact.map((p) => (
            <span key={p.phase} style={{ marginRight: "1rem" }}>
              <strong>{p.phase}</strong>: {p.count} — {p.detail}
            </span>
          ))}
        </div>
      )}

      {loading && <p className="count-muted">Loading…</p>}

      {!loading && view === "hub" && (
        <>
          <p className="count-muted">{skippedTotal.toLocaleString()} items</p>
          <VirtualTable
            items={skipped}
            colCount={6}
            header={
              <tr>
                <th />
                <th>Reason</th>
                <th>Section</th>
                <th>Item</th>
                <th>Path</th>
                <th>Detail</th>
              </tr>
            }
            renderRow={(row, _index, rowAttrs) => (
              <tr key={`${row.reason}-${row.path}-${row.item_name}`} {...rowAttrs}>
                <td>
                  {row.path && (
                    <input
                      type="checkbox"
                      checked={selected.has(row.path)}
                      onChange={() => toggleSelect(row.path)}
                      aria-label={`Select ${row.item_name || row.path}`}
                    />
                  )}
                </td>
                <td>
                  <code>{REASON_LABELS[row.reason] ?? row.reason}</code>
                </td>
                <td>{row.section}</td>
                <td>{row.item_name}</td>
                <td>{row.path ? <PathLink path={row.path} /> : "—"}</td>
                <td className="count-muted">{row.detail}</td>
              </tr>
            )}
          />
        </>
      )}

      {!loading && view === "failures" && (
        <VirtualTable
          items={failures}
          colCount={5}
          header={
            <tr>
              <th />
              <th>Section</th>
              <th>Item</th>
              <th>Path</th>
              <th>Error</th>
            </tr>
          }
          renderRow={(row, _index, rowAttrs) => (
            <tr key={row.path} {...rowAttrs}>
              <td>
                <input
                  type="checkbox"
                  checked={selected.has(row.path)}
                  onChange={() => toggleSelect(row.path)}
                  aria-label={`Select ${row.item_name || row.path}`}
                />
              </td>
              <td>{row.section}</td>
              <td>{row.item_name}</td>
              <td>
                <PathLink path={row.path} />
              </td>
              <td className="count-muted">{row.error}</td>
            </tr>
          )}
        />
      )}

      {!loading && view === "coverage" && (
        <VirtualTable
          items={gaps}
          colCount={6}
          header={
            <tr>
              <th />
              <th>Reason</th>
              <th>Section</th>
              <th>Name</th>
              <th>Path</th>
              <th>Detail</th>
            </tr>
          }
          renderRow={(row, _index, rowAttrs) => (
            <tr key={row.path} {...rowAttrs}>
              <td>
                <input
                  type="checkbox"
                  checked={selected.has(row.path)}
                  onChange={() => toggleSelect(row.path)}
                  aria-label={`Select ${row.name || row.path}`}
                />
              </td>
              <td>
                <code>{row.reason}</code>
              </td>
              <td>{row.section}</td>
              <td>{row.name}</td>
              <td>
                <PathLink path={row.path} />
              </td>
              <td className="count-muted">{row.detail}</td>
            </tr>
          )}
        />
      )}

      {!loading && view === "cache" && (
        <VirtualTable
          items={cacheHits}
          colCount={4}
          header={
            <tr>
              <th />
              <th>Section</th>
              <th>Name</th>
              <th>Path</th>
            </tr>
          }
          renderRow={(row, _index, rowAttrs) => (
            <tr key={row.path} {...rowAttrs}>
              <td>
                <input
                  type="checkbox"
                  checked={selected.has(row.path)}
                  onChange={() => toggleSelect(row.path)}
                  aria-label={`Select ${row.name || row.path}`}
                />
              </td>
              <td>{row.section}</td>
              <td>{row.name}</td>
              <td>
                <PathLink path={row.path} />
              </td>
            </tr>
          )}
        />
      )}

      {!loading && view === "nested" && (
        <VirtualTable
          items={nested}
          colCount={5}
          header={
            <tr>
              <th>Section</th>
              <th>Item</th>
              <th>Issue</th>
              <th>Nested path</th>
              <th>Fix</th>
            </tr>
          }
          renderRow={(row, _index, rowAttrs) => (
            <tr key={row.nested_path} {...rowAttrs}>
              <td>{row.section}</td>
              <td>{row.item_name}</td>
              <td>
                <code>{row.issue_type}</code>
              </td>
              <td>
                <PathLink path={row.nested_path} />
              </td>
              <td className="count-muted">{row.suggested_fix}</td>
            </tr>
          )}
        />
      )}

      {!loading && view === "coexistence" && (
        <VirtualTable
          items={coexistence}
          colCount={6}
          header={
            <tr>
              <th>Section</th>
              <th>Item</th>
              <th>Issue</th>
              <th>Archive</th>
              <th>Folder</th>
              <th>Similarity</th>
            </tr>
          }
          renderRow={(row, _index, rowAttrs) => (
            <tr key={`${row.item_path}-${row.archive_or_installer}`} {...rowAttrs}>
              <td>{row.section}</td>
              <td>{row.item_name}</td>
              <td>
                <code>{row.issue_type}</code>
              </td>
              <td>{row.archive_or_installer}</td>
              <td>{row.extracted_folder}</td>
              <td>{row.name_similarity_pct != null ? `${row.name_similarity_pct}%` : "—"}</td>
            </tr>
          )}
        />
      )}

      {!loading && view === "inventory" && (
        <VirtualTable
          items={inventory}
          colCount={6}
          header={
            <tr>
              <th>Bin</th>
              <th>Item</th>
              <th>Vendor</th>
              <th>ID</th>
              <th>Fingerprint</th>
              <th>Type</th>
            </tr>
          }
          renderRow={(row, _index, rowAttrs) => (
            <tr key={`${row.root_bin}-${row.item_name}`} {...rowAttrs}>
              <td>{row.root_bin}</td>
              <td>{row.item_name}</td>
              <td>{row.vendor}</td>
              <td>{row.id_method}</td>
              <td>{row.fingerprint}</td>
              <td>{row.item_type}</td>
            </tr>
          )}
        />
      )}

      {!loading && view === "truncations" && (
        <VirtualTable
          items={truncations}
          colCount={6}
          header={
            <tr>
              <th>Section</th>
              <th>Item</th>
              <th>Kind</th>
              <th>Truncated path</th>
              <th>Depth / limit</th>
              <th>Detail</th>
            </tr>
          }
          renderRow={(row, _index, rowAttrs) => (
            <tr key={`${row.item_path}-${row.truncated_path}`} {...rowAttrs}>
              <td>{row.section}</td>
              <td>{row.item_name}</td>
              <td>
                <code>{row.kind}</code>
              </td>
              <td>{row.truncated_path ? <PathLink path={row.truncated_path} /> : row.relative_path}</td>
              <td>
                {row.depth}/{row.limit}
              </td>
              <td className="count-muted">{row.detail}</td>
            </tr>
          )}
        />
      )}

      {view === "compare" && (
        <div>
          <div className="toolbar">
            <LabeledSelect label="Run A" value={compareA} onChange={(e) => setCompareA(e.target.value)}>
              {runs.map((r) => (
                <option key={r.stamp} value={r.stamp}>
                  {r.stamp}
                </option>
              ))}
            </LabeledSelect>
            <LabeledSelect label="Run B" value={compareB} onChange={(e) => setCompareB(e.target.value)}>
              {runs.map((r) => (
                <option key={r.stamp} value={r.stamp}>
                  {r.stamp}
                </option>
              ))}
            </LabeledSelect>
            <Button variant="primary" onClick={handleCompare}>
              Compare
            </Button>
          </div>
          {comparison && (
            <div className="dash-grid" style={{ marginTop: "1rem" }}>
              <section className="dash-panel">
                <header className="dash-panel-header">
                  <h3>Status changes</h3>
                </header>
                <div className="dash-panel-body">
                  <p className="count-muted">{comparison.deltas.length} delta(s)</p>
                  <ul className="compact-list">
                    {comparison.deltas.slice(0, 50).map((d) => (
                      <li key={`${d.path}-${d.change_type}`}>
                        <code>{d.change_type}</code> {d.path.slice(-60)} — {d.old_value} → {d.new_value}
                      </li>
                    ))}
                  </ul>
                </div>
              </section>
              <section className="dash-panel">
                <header className="dash-panel-header">
                  <h3>Failures &amp; cache</h3>
                </header>
                <div className="dash-panel-body">
                  <p>New failures: {comparison.new_failures.length}</p>
                  <p>Resolved failures: {comparison.resolved_failures.length}</p>
                  <p>New cache hits: {comparison.new_cache_hits.length}</p>
                  <p>Fresh scans (was cached): {comparison.fresh_scans.length}</p>
                </div>
              </section>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
