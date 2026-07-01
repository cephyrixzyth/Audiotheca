import { useEffect, useState } from "react";
import { correctInvestigation, fetchInvestigationFeedback, fetchScanAudit } from "../api/client";
import type { ScanAuditItem } from "../types";
import { PathLink } from "./PathLink";

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
  const [items, setItems] = useState<ScanAuditItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("");
  const [flags, setFlags] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);
  const [bucketOptions, setBucketOptions] = useState<string[]>([]);

  useEffect(() => {
    fetchInvestigationFeedback(stamp)
      .then((state) => setBucketOptions(state.bucket_options ?? []))
      .catch(() => setBucketOptions([]));
  }, [stamp]);

  useEffect(() => {
    setLoading(true);
    const timer = setTimeout(() => {
      fetchScanAudit(stamp, {
        status: status || undefined,
        flags: flags || undefined,
        q: query || undefined,
        limit: 500,
      })
        .then((res) => {
          setItems(res.items);
          setTotal(res.total);
        })
        .finally(() => setLoading(false));
    }, query ? 250 : 0);
    return () => clearTimeout(timer);
  }, [stamp, status, flags, query]);

  async function handleSetVendor(row: ScanAuditItem) {
    const vendor = window.prompt("Vendor name:", row.vendor === "UNKNOWN" ? "" : row.vendor)?.trim();
    if (!vendor) return;
    await correctInvestigation(stamp, {
      path: row.current_path,
      action: "set_vendor",
      value: vendor,
      item_name: row.item_name,
      old_bucket: row.investigation_bucket,
    });
    setMsg(`Vendor override saved for ${row.item_name}`);
  }

  return (
    <div>
      <div className="banner dry">
        Full scan audit — every folder/archive target. Fix vendors here; overrides apply on the next scan.
      </div>

      <div className="toolbar" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
        {QUICK_FILTERS.map((filter) => (
          <button
            key={filter.id}
            type="button"
            className={
              (filter.status && status === filter.status) ||
              (filter.flags && flags === filter.flags)
                ? "primary-btn"
                : "keeper-btn"
            }
            title={filter.title ?? filter.label}
            onClick={() => {
              setStatus(filter.status ?? "");
              setFlags(filter.flags ?? "");
            }}
          >
            {filter.label}
          </button>
        ))}
        <button
          type="button"
          className="keeper-btn"
          title="Clear status and flag filters"
          onClick={() => { setStatus(""); setFlags(""); }}
        >
          All rows
        </button>
        <button
          type="button"
          className="keeper-btn"
          title="Show only routes ready to move on next live run"
          onClick={() => { setStatus("READY"); setFlags(""); }}
        >
          READY only
        </button>
      </div>

      <div className="toolbar">
        <label>
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            <option value="READY">READY</option>
            <option value="NEEDS REVIEW">NEEDS REVIEW</option>
            <option value="DEST EXISTS (merge)">DEST EXISTS (merge)</option>
            <option value="SCAN_FAILED">SCAN_FAILED</option>
          </select>
        </label>
        <label>
          Search
          <input
            type="search"
            placeholder="Name, path, vendor, fingerprint…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <span className="count-muted">
          {loading ? "Loading…" : `${total.toLocaleString()} audit rows`}
        </span>
      </div>

      {msg && <div className="banner dry">{msg}</div>}

      {!loading && items.length === 0 && (
        <div className="empty">No audit rows — run a scan or open a run with Scan_Audit CSV.</div>
      )}

      {items.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Section</th>
              <th>Item</th>
              <th>Vendor / ID</th>
              <th>Status</th>
              <th>Flags</th>
              <th>Destination</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.current_path}>
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
                  <span className={`badge ${row.status === "READY" ? "ready" : "bucket"}`}>
                    {row.status}
                  </span>
                  {row.investigation_bucket && (
                    <div className="count-muted">{row.investigation_bucket}</div>
                  )}
                </td>
                <td><code style={{ fontSize: "0.75rem" }}>{row.flags || "—"}</code></td>
                <td><PathLink path={row.planned_destination} /></td>
                <td>
                  <button
                    type="button"
                    className="keeper-btn"
                    title="Override vendor for this path on the next scan"
                    onClick={() => void handleSetVendor(row)}
                  >
                    Set vendor
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {bucketOptions.length > 0 && (
        <p className="count-muted" style={{ marginTop: "1rem" }}>
          Tip: use Investigation tab for bucket reassignment and parent links.
        </p>
      )}
    </div>
  );
}
