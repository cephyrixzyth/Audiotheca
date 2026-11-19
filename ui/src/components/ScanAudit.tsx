import { WorkScope, WorkIssue, useReviewDecision } from "./ReviewWorkbench";
import { LoadingStatus } from "../ui/LoadingStatus";
import { useEffect, useState } from "react";
import { correctInvestigation, fetchInvestigationFeedback, fetchScanAudit, fetchScanInsights } from "../api/client";
import type { ScanAuditItem } from "../types";
import { Badge, Button, VirtualTable } from "../ui";
import { PathLink } from "./PathLink";
import { useContextSidebar, useSidebarFilters } from "./ContextSidebar";

const STATUS_FILTER_DEFS = [
  {
    key: "status",
    label: "Status",
    title: "Route status from the scan audit CSV",
    options: [
      { value: "", label: "All statuses" },
      { value: "READY", label: "READY" },
      { value: "NEEDS REVIEW", label: "NEEDS REVIEW" },
      { value: "DEST EXISTS (merge)", label: "DEST EXISTS (merge)" },
      { value: "SCAN_FAILED", label: "SCAN_FAILED" },
    ],
  },
];

interface Props {
  stamp: string;
}

const QUICK_FILTERS = [
  { id: "unknown", label: "UNKNOWN vendor", flags: "unknown_vendor", title: "Rows flagged unknown_vendor — need vendor ID or feedback" },
  { id: "tentative", label: "Tentative ID", flags: "tentative_id", title: "Identification confidence is tentative — review before live run" },
  { id: "not_ready", label: "Not READY", status: "NEEDS REVIEW", title: "Routes blocked until investigation or override" },
  { id: "failed", label: "Scan failed", status: "SCAN_FAILED", title: "Engine could not complete scan for this path" },
];

export function ScanAudit({ stamp }: Props) {
  const { ask, dialog } = useReviewDecision();
  const [revision, setRevision] = useState(0);
  const [loadError, setLoadError] = useState("");
  const { query } = useContextSidebar();
  const { filters, setFilter } = useSidebarFilters(STATUS_FILTER_DEFS);
  const status = filters.status ?? "";
  const [items, setItems] = useState<ScanAuditItem[]>([]);
  const [total, setTotal] = useState(0);
  const [flags, setFlags] = useState("");
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [bucketOptions, setBucketOptions] = useState<string[]>([]);
  const [insights, setInsights] = useState<Record<string, unknown> | null>(null);
  const [insightsStatus, setInsightsStatus] = useState<"loading" | "ready" | "empty" | "error">(
    "loading",
  );

  useEffect(() => {
    setInsightsStatus("loading");
    void fetchScanInsights(stamp)
      .then((payload) => {
        setInsights(payload);
        const recs = payload.recommendations;
        setInsightsStatus(Array.isArray(recs) && recs.length > 0 ? "ready" : "empty");
      })
      .catch(() => {
        setInsights(null);
        setInsightsStatus("error");
      });
  }, [stamp]);

  useEffect(() => {
    fetchInvestigationFeedback(stamp)
      .then((state) => setBucketOptions(state.bucket_options ?? []))
      .catch(() => setBucketOptions([]));
  }, [stamp]);

  useEffect(() => {
    let current = true;
    setLoadError(""); setLoading(true);
    const timer = setTimeout(() => {
      fetchScanAudit(stamp, {
        status: status || undefined,
        flags: flags || undefined,
        q: query || undefined,
        limit: 500,
      })
        .then((res) => {
          if (!current) return;
          setItems(res.items);
          setTotal(res.total);
        })
        .catch((err: Error) => { if (current) { setLoadError(err.message); setItems([]); } })
        .finally(() => { if (current) setLoading(false); });
    }, query ? 250 : 0);
    return () => { current = false; clearTimeout(timer); };
  }, [stamp, status, flags, query, revision]);

  async function handleSetVendor(row: ScanAuditItem) {
    ask({title: "Correct vendor", detail: row.current_path, action: "Save vendor", fields: [{ label: "Company name", value: row.vendor === "UNKNOWN" ? "" : row.vendor }], accept: async ([vendor]) => {
    await correctInvestigation(stamp, {
      path: row.current_path,
      action: "set_vendor",
      value: vendor,
      item_name: row.item_name,
      old_bucket: row.investigation_bucket,
    });
    setMsg(`Vendor override saved for ${row.item_name}`);
    }});
  }

  return (
    <div className="review-workspace">
      {dialog}
      <WorkScope title="Find routes that need attention" detail="Filter the scan by its outcome, inspect the path and vendor evidence, and save corrections for the next scan." />
      {loadError && <WorkIssue message={loadError} retry={() => setRevision(v => v + 1)} />}
      {insightsStatus === "loading" && (
        <div className="count-muted" style={{ marginBottom: "1rem" }}>
          <LoadingStatus>Loading scan insights…</LoadingStatus>
        </div>
      )}
      {insightsStatus === "error" && (
        <div className="banner warn" style={{ marginBottom: "1rem" }}>
          Scan insights could not be loaded for this run.
        </div>
      )}
      {insightsStatus === "empty" && (
        <div className="count-muted" style={{ marginBottom: "1rem" }}>
          This run recorded no tuning suggestions.
        </div>
      )}
      {insightsStatus === "ready" &&
        insights &&
        Array.isArray(insights.recommendations) &&
        insights.recommendations.length > 0 && (
        <details className="log-panel" style={{ marginBottom: "1rem" }}>
          <summary>
            Scan insights ({insights.recommendations.length} recommendation
            {insights.recommendations.length === 1 ? "" : "s"})
          </summary>
          <ul style={{ margin: "0.5rem 0 0", paddingLeft: "1.25rem" }}>
            {(insights.recommendations as Array<{ priority?: string; action?: string; detail?: string }>).map(
              (rec) => (
                <li key={`${rec.action}-${rec.detail}`}>
                  <strong>{rec.priority ?? "info"}:</strong> {rec.action}
                  {rec.detail ? ` — ${rec.detail}` : ""}
                </li>
              ),
            )}
          </ul>
        </details>
      )}

      <div className="toolbar" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
        {QUICK_FILTERS.map((filter) => (
          <Button
            key={filter.id}
            variant={
              (filter.status && status === filter.status) ||
              (filter.flags && flags === filter.flags)
                ? "primary"
                : "secondary"
            }
            aria-pressed={Boolean((filter.status && status === filter.status) || (filter.flags && flags === filter.flags))}
            title={filter.title ?? filter.label}
            onClick={() => {
              setFilter("status", filter.status ?? "");
              setFlags(filter.flags ?? "");
            }}
          >
            {filter.label}
          </Button>
        ))}
        <Button
          variant="secondary"
          title="Clear status and flag filters"
          onClick={() => { setFilter("status", ""); setFlags(""); }}
        >
          All rows
        </Button>
        <Button
          variant="secondary"
          title="Show only routes ready to move on next live run"
          onClick={() => { setFilter("status", "READY"); setFlags(""); }}
        >
          READY only
        </Button>
      </div>

      <div className="toolbar">
        <span className="count-muted">
          {loading ? <LoadingStatus /> : `${total.toLocaleString()} audit rows`}
        </span>
      </div>

      {msg && <div className="banner dry" role="status">{msg}</div>}

      {!loading && !loadError && items.length === 0 && (
        <div className="empty">No audit rows match this view. Choose All rows or open a run with a scan audit.</div>
      )}

      {items.length > 0 && (
        <VirtualTable
          items={items}
          colCount={7}
          estimateSize={72}
          header={
            <tr>
              <th>Section</th>
              <th>Item</th>
              <th>Vendor / ID</th>
              <th>Status</th>
              <th>Flags</th>
              <th>Destination</th>
              <th>Actions</th>
            </tr>
          }
          renderRow={(row, _index, rowAttrs) => (
            <tr key={row.current_path} {...rowAttrs}>
              <td><code>{row.section}</code></td>
              <td>
                <div>{row.item_name}</div>
                <PathLink path={row.current_path} />
                <div className="count-muted">
                  {row.fingerprint}
                  {row.version_key ? ` · v${row.version_key}` : ""}
                  {row.size_mb != null ? ` · ${row.size_mb} MB` : ""}
                </div>
              </td>
              <td>
                <div>{row.vendor}</div>
                <div className="path">{row.id_method} · {row.id_confidence || "—"}</div>
              </td>
              <td>
                <Badge tone={row.status === "READY" ? "ready" : "accent"}>{row.status}</Badge>
                {row.investigation_bucket && (
                  <div className="count-muted">{row.investigation_bucket}</div>
                )}
              </td>
              <td><code style={{ fontSize: "0.75rem" }}>{row.flags || "—"}</code></td>
              <td><PathLink path={row.planned_destination} /></td>
              <td>
                <Button
                  variant="secondary"
                  size="sm"
                  title="Override vendor for this path on the next scan"
                  onClick={() => void handleSetVendor(row)}
                >
                  Set vendor
                </Button>
              </td>
            </tr>
          )}
        />
      )}

      {bucketOptions.length > 0 && (
        <p className="count-muted" style={{ marginTop: "1rem" }}>
          Tip: use Investigation tab for bucket reassignment and parent links.
        </p>
      )}
    </div>
  );
}
