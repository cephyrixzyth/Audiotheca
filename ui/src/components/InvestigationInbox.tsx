import { useEffect, useMemo, useState } from "react";
import {
  bulkAddVendorGaps,
  bulkCorrectInvestigation,
  correctInvestigation,
  fetchBuckets,
  fetchInvestigation,
  fetchInvestigationFeedback,
  fetchInvestigationGroups,
  investigationFeedbackExportUrl,
  type InvestigationGroup,
  type InvestigationFeedbackState,
} from "../api/client";
import type { InvestigationItem } from "../types";
import { useContextSidebar, useSidebarFilters } from "./ContextSidebar";
import { HoverMenu } from "./HoverMenu";
import { PathLink } from "./PathLink";

interface Props {
  stamp: string;
}

const BUCKET_HINTS: Record<string, string> = {
  _unverified_vendor: "Add vendor to DB — bulk via Vendors tab",
  _unknown_vendor: "Needs ID tier or archive peek",
  _sample_pack: "Link to parent pack folder",
  _scene_release_id: "Check Scene tab / lower peek threshold",
  _likely_component: "Link to parent product",
  _library_internal: "Merge into parent library",
  _preset_or_snippet: "Link to parent or mark resolved",
};

function pathKey(path: string) {
  return path.toLowerCase().replace(/\\/g, "/");
}

function methodClass(method: string, confidence: string) {
  if (method === "NONE") return "badge review";
  if (confidence === "TENTATIVE") return "badge bucket";
  return "badge ready";
}

export function InvestigationInbox({ stamp }: Props) {
  const { query } = useContextSidebar();
  const [view, setView] = useState<"list" | "groups">("groups");
  const [items, setItems] = useState<InvestigationItem[]>([]);
  const [groups, setGroups] = useState<InvestigationGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [buckets, setBuckets] = useState<Record<string, number>>({});
  const bucketFilterDefs = useMemo(
    () => [
      {
        key: "bucket",
        label: "Bucket",
        title: "Investigation bucket assigned when the engine could not route confidently",
        options: [
          { value: "", label: `All (${Object.values(buckets).reduce((a, b) => a + b, 0)})` },
          ...Object.entries(buckets).map(([name, count]) => ({
            value: name,
            label: `${name} (${count})`,
          })),
        ],
      },
    ],
    [buckets],
  );
  const { filters } = useSidebarFilters(bucketFilterDefs);
  const bucket = filters.bucket ?? "";
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<InvestigationFeedbackState | null>(null);
  const [exportUrl, setExportUrl] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [newBucket, setNewBucket] = useState("");
  const [selectedGroup, setSelectedGroup] = useState<string>("");

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
      if (view === "groups") {
        fetchInvestigationGroups(stamp, {
          bucket: bucket || undefined,
          group_by: "prefix",
          q: query || undefined,
          limit: 150,
        })
          .then((res) => {
            setGroups(res.groups);
            setTotal(res.total);
          })
          .catch((err: Error) => setError(err.message))
          .finally(() => setLoading(false));
      } else {
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
      }
    }, query ? 250 : 0);
    return () => clearTimeout(timer);
  }, [stamp, bucket, query, view]);

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

  async function bulkApply(
    paths: string[],
    action: string,
    value = "",
    extra?: { keywords?: string[]; reason?: string },
  ) {
    const res = await bulkCorrectInvestigation(stamp, {
      paths,
      action,
      value,
      reason: extra?.reason ?? "other",
      keywords: extra?.keywords,
    });
    setFeedback(res.state);
    setExportUrl(await investigationFeedbackExportUrl(stamp));
    setMsg(`Bulk ${action}: ${res.count} paths`);
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

  async function handleGroupSetVendor(group: InvestigationGroup) {
    const vendor = window.prompt("Vendor for group:", group.group_key.replace(/\./g, " "))?.trim();
    if (!vendor) return;
    await bulkApply(group.paths, "set_vendor", vendor, {
      reason: "vendor_known",
      keywords: [group.group_key.toLowerCase(), vendor.toLowerCase()],
    });
  }

  async function handleGroupAddVendorDb(group: InvestigationGroup) {
    const company = group.group_key.replace(/\./g, " ").replace(/\s+/g, " ").trim();
    const res = await bulkAddVendorGaps(stamp, [group.group_key]);
    if (res.count > 0) {
      setMsg(`Added ${company} to vendor_overrides.json (${group.count} items on next scan)`);
    } else {
      setMsg(`Could not add ${group.group_key} — check Vendors tab`);
    }
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

  async function handleGroupLinkParent(group: InvestigationGroup) {
    const parent = window.prompt("Parent path for all items in group:", "")?.trim();
    if (!parent) return;
    await bulkApply(group.paths, "link_parent", parent, { reason: "is_component" });
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
        <label title="Grouped view for bulk vendor/parent fixes; list view for per-item work">
          View
          <select value={view} onChange={(e) => setView(e.target.value as "list" | "groups")}>
            <option value="groups">By prefix (bulk)</option>
            <option value="list">All items</option>
          </select>
        </label>
        <span className="count-muted">
          {loading ? "Loading…" : `${total.toLocaleString()} ${view === "groups" ? "groups" : "items"}`}
          {feedback ? ` · ${feedback.corrections.length} corrections` : ""}
        </span>
        <button
          type="button"
          className="keeper-btn"
          title="Add a vendor keyword to feedback for the next scan"
          onClick={() => void handleAddVendor()}
        >
          Add vendor
        </button>
        {exportUrl && (
          <a className="text-btn" href={exportUrl} download title="Download corrections CSV for engine tuning">
            Export feedback CSV
          </a>
        )}
      </div>

      {bucket && BUCKET_HINTS[bucket] && (
        <div className="banner dry">{BUCKET_HINTS[bucket]}</div>
      )}

      {msg && <div className="banner dry">{msg}</div>}
      {error && <div className="error">{error}</div>}

      {!loading && view === "groups" && groups.length === 0 && !error && (
        <div className="empty">No investigation groups match your filters.</div>
      )}

      {!loading && view === "list" && items.length === 0 && !error && (
        <div className="empty">No investigation items match your filters.</div>
      )}

      {view === "groups" && groups.length > 0 && (
        <div className="table-wrap">
          <table className="data-table investigation-table">
            <thead>
              <tr>
                <th>Prefix / group</th>
                <th>Count</th>
                <th>Bucket</th>
                <th>ID</th>
                <th>Samples</th>
                <th>Bulk actions</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((group) => (
                <tr
                  key={group.group_key}
                  className={selectedGroup === group.group_key ? "inv-vendor-set" : ""}
                  onClick={() => setSelectedGroup(group.group_key)}
                >
                  <td>
                    <strong>{group.group_key}</strong>
                  </td>
                  <td>{group.count}</td>
                  <td>
                    <span className="badge bucket">{group.bucket}</span>
                  </td>
                  <td>
                    <span className={methodClass(group.id_method, "")}>{group.id_method}</span>
                  </td>
                  <td className="count-muted">
                    {group.sample_items.slice(0, 2).join(" · ")}
                  </td>
                  <td className="inv-actions">
                    {group.bucket === "_unverified_vendor" && (
                      <button
                        type="button"
                        className="primary-btn"
                        title="Add this prefix to vendor_overrides.json so future scans recognize the vendor"
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleGroupAddVendorDb(group);
                        }}
                      >
                        Add to DB
                      </button>
                    )}
                    <button
                      type="button"
                      className="keeper-btn"
                      title="Set vendor name for every item in this prefix group"
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleGroupSetVendor(group);
                      }}
                    >
                      Set vendor
                    </button>
                    {(group.bucket === "_sample_pack" || group.bucket === "_likely_component") && (
                      <button
                        type="button"
                        className="keeper-btn"
                        title="Link all items in this group to a parent product folder"
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleGroupLinkParent(group);
                        }}
                      >
                        Link parent
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {view === "list" && items.length > 0 && (
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
                    <span className={methodClass(row.id_method, row.id_confidence)}>
                      {row.id_method}
                    </span>
                    <div className="path">{row.id_confidence}</div>
                    <div className="count-muted">{row.size_mb != null ? `${row.size_mb} MB` : ""}</div>
                  </td>
                  <td className="inv-actions row-actions-cell">
                    <HoverMenu
                      actions={[
                        {
                          id: "vendor",
                          label: "Set vendor",
                          onClick: () => void handleSetVendor(row),
                        },
                        {
                          id: "parent",
                          label: "Link parent",
                          onClick: () => void handleLinkParent(row),
                        },
                        {
                          id: "resolved",
                          label: "Resolved",
                          tone: "accent",
                          onClick: () => void handleResolved(row),
                        },
                      ]}
                    >
                      <span className="row-actions-trigger" aria-label="Actions">
                        ⋮
                      </span>
                    </HoverMenu>
                    <select
                      className="reject-select"
                      defaultValue=""
                      title="Move item to a different investigation bucket"
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
