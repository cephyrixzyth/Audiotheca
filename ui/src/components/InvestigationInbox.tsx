import { useEffect, useState } from "react";
import {
  correctInvestigation,
  fetchBuckets,
  fetchInvestigation,
  fetchInvestigationFeedback,
  investigationFeedbackExportUrl,
  type InvestigationFeedbackState,
} from "../api/client";
import type { InvestigationItem } from "../types";
import { PathLink } from "./PathLink";

interface Props {
  stamp: string;
}

function pathKey(path: string) {
  return path.toLowerCase().replace(/\\/g, "/");
}

export function InvestigationInbox({ stamp }: Props) {
  const [items, setItems] = useState<InvestigationItem[]>([]);
  const [total, setTotal] = useState(0);
  const [buckets, setBuckets] = useState<Record<string, number>>({});
  const [bucket, setBucket] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<InvestigationFeedbackState | null>(null);
  const [exportUrl, setExportUrl] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [newBucket, setNewBucket] = useState("");

  useEffect(() => {
    fetchBuckets(stamp)
      .then(setBuckets)
      .catch(() => setBuckets({}));
    fetchInvestigationFeedback(stamp)
      .then(setFeedback)
      .catch(() => setFeedback(null));
    void investigationFeedbackExportUrl(stamp).then(setExportUrl);
  }, [stamp]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const timer = setTimeout(() => {
      fetchInvestigation(stamp, {
        bucket: bucket || undefined,
        q: query || undefined,
        limit: 500,
      })
        .then((res) => {
          setItems(res.items);
          setTotal(res.total);
        })
        .catch((err: Error) => setError(err.message))
        .finally(() => setLoading(false));
    }, query ? 250 : 0);
    return () => clearTimeout(timer);
  }, [stamp, bucket, query]);

  const resolvedSet = new Set(
    (feedback?.resolved_paths ?? []).map((p) => pathKey(p)),
  );
  const vendorMap = feedback?.path_vendor_overrides ?? {};
  const bucketMap = feedback?.path_bucket_overrides ?? {};
  const parentMap = feedback?.parent_links ?? {};
  const bucketOptions = feedback?.bucket_options ?? Object.keys(buckets);

  async function apply(
    row: InvestigationItem,
    action: string,
    value = "",
    extra?: { keywords?: string[]; reason?: string },
  ) {
    const res = await correctInvestigation(stamp, {
      path: row.current_path,
      action,
      value,
      item_name: row.item_name,
      old_bucket: row.investigation_bucket,
      reason: extra?.reason ?? "other",
      keywords: extra?.keywords,
    });
    setFeedback(res.state);
    setExportUrl(await investigationFeedbackExportUrl(stamp));
    setMsg(`Saved: ${action} for ${row.item_name}`);
  }

  async function handleSetVendor(row: InvestigationItem) {
    const vendor = window.prompt("Vendor / company name:", "")?.trim();
    if (!vendor) return;
    const keywords = window.prompt("Keywords (comma-separated, optional):", row.item_name)?.trim();
    await apply(row, "set_vendor", vendor, {
      reason: "vendor_known",
      keywords: keywords ? keywords.split(",").map((k) => k.trim()).filter(Boolean) : [],
    });
  }

  async function handleReassign(row: InvestigationItem, targetBucket: string) {
    if (!targetBucket) return;
    await apply(row, "reassign_bucket", targetBucket, { reason: "wrong_bucket" });
  }

  async function handleNewBucket(row: InvestigationItem) {
    const name = newBucket.trim() || window.prompt("New bucket name (e.g. _awaiting_license):", "")?.trim();
    if (!name) return;
    const desc = window.prompt("Bucket description:", "User-defined bucket") ?? "";
    await correctInvestigation(stamp, {
      path: row.current_path,
      action: "reassign_bucket",
      value: name,
      note: desc,
      item_name: row.item_name,
      old_bucket: row.investigation_bucket,
      reason: "wrong_bucket",
    }).then((res) => {
      setFeedback(res.state);
      setNewBucket("");
      setMsg(`Created bucket ${name} and assigned ${row.item_name}`);
    });
  }

  async function handleLinkParent(row: InvestigationItem) {
    const parent = window.prompt("Parent product path:", "")?.trim();
    if (!parent) return;
    await apply(row, "link_parent", parent, { reason: "is_component" });
  }

  async function handleResolved(row: InvestigationItem) {
    await apply(row, "mark_resolved", "", { reason: "false_positive" });
  }

  async function handleAddVendor() {
    const company = window.prompt("Company name:", "")?.trim();
    if (!company) return;
    const keywords = window.prompt("Keywords (comma-separated):", "")?.trim();
    await correctInvestigation(stamp, {
      path: "",
      action: "add_vendor",
      value: company,
      keywords: keywords ? keywords.split(",").map((k) => k.trim()).filter(Boolean) : [company],
      reason: "vendor_known",
    }).then((res) => {
      setFeedback(res.state);
      setMsg(`Added vendor ${company} to feedback`);
    });
  }

  function rowStatus(row: InvestigationItem) {
    const key = pathKey(row.current_path);
    if (resolvedSet.has(key)) return "resolved";
    if (vendorMap[row.current_path] || vendorMap[key]) return "vendor-set";
    if (bucketMap[row.current_path]) return "bucket-override";
    if (parentMap[row.current_path]) return "linked";
    return "";
  }

  return (
    <div>
      <div className="toolbar">
        <label>
          Bucket
          <select value={bucket} onChange={(e) => setBucket(e.target.value)}>
            <option value="">All ({Object.values(buckets).reduce((a, b) => a + b, 0)})</option>
            {Object.entries(buckets).map(([name, count]) => (
              <option key={name} value={name}>
                {name} ({count})
              </option>
            ))}
          </select>
        </label>
        <label>
          Search
          <input
            type="search"
            placeholder="Name, path, fingerprint…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <span className="count-muted">
          {loading ? "Loading…" : `${total.toLocaleString()} items`}
          {feedback ? ` · ${feedback.corrections.length} corrections` : ""}
        </span>
        <button type="button" className="keeper-btn" onClick={() => void handleAddVendor()}>
          Add vendor
        </button>
        {exportUrl && (
          <a className="text-btn" href={exportUrl} download>
            Export feedback CSV
          </a>
        )}
      </div>

      {msg && <div className="banner dry">{msg}</div>}
      {error && <div className="error">{error}</div>}

      {!loading && items.length === 0 && !error && (
        <div className="empty">No investigation items match your filters.</div>
      )}

      {items.length > 0 && (
        <table className="data-table investigation-table">
          <thead>
            <tr>
              <th>Section</th>
              <th>Item</th>
              <th>Bucket</th>
              <th>ID</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => {
              const status = rowStatus(row);
              const vendorOverride = vendorMap[row.current_path];
              return (
                <tr key={`${row.current_path}-${row.item_name}`} className={status ? `inv-${status}` : ""}>
                  <td>
                    <code>{row.section}</code>
                  </td>
                  <td>
                    <div>{row.item_name}</div>
                    <PathLink path={row.current_path} />
                    {vendorOverride && (
                      <div className="count-muted">vendor → {vendorOverride}</div>
                    )}
                    {parentMap[row.current_path] && (
                      <div className="count-muted">parent → {parentMap[row.current_path]}</div>
                    )}
                  </td>
                  <td>
                    <span className="badge bucket">
                      {bucketMap[row.current_path] ?? row.investigation_bucket}
                    </span>
                    {status === "resolved" && <span className="badge ready">resolved</span>}
                  </td>
                  <td>
                    <span className="badge review">{row.id_method}</span>
                    <div className="path">{row.id_confidence}</div>
                    <div className="count-muted">{row.size_mb != null ? `${row.size_mb} MB` : ""}</div>
                  </td>
                  <td className="inv-actions">
                    <button type="button" className="keeper-btn" onClick={() => void handleSetVendor(row)}>
                      Set vendor
                    </button>
                    <select
                      className="reject-select"
                      defaultValue=""
                      onChange={(e) => {
                        if (e.target.value === "__new__") {
                          void handleNewBucket(row);
                        } else if (e.target.value) {
                          void handleReassign(row, e.target.value);
                        }
                        e.target.value = "";
                      }}
                    >
                      <option value="">Reassign…</option>
                      {bucketOptions.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                      <option value="__new__">+ New bucket…</option>
                    </select>
                    <button type="button" className="keeper-btn" onClick={() => void handleLinkParent(row)}>
                      Link parent
                    </button>
                    <button type="button" className="text-btn" onClick={() => void handleResolved(row)}>
                      Resolved
                    </button>
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
