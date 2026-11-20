import { useReviewDecision, WorkIssue, WorkScope } from "./ReviewWorkbench";
import { LoadingStatus } from "../ui/LoadingStatus";
import { useEffect, useMemo, useState } from "react";
import {
  bulkAddVendorGaps,
  bulkCorrectInvestigation,
  correctInvestigation,
  fetchBuckets,
  fetchInvestigation,
  fetchInvestigationFeedback,
  fetchInvestigationGroups,
  investigationFeedbackExportDownload,
  type InvestigationGroup,
  type InvestigationFeedbackState,
} from "../api/client";
import type { InvestigationItem } from "../types";
import { Badge, Button, Tabs, VirtualTable } from "../ui";
import type { BadgeTone } from "../ui";
import { pathKey } from "../utils/pathKey";
import { useContextSidebar, useSidebarFilters } from "./ContextSidebar";
import { HoverMenu } from "./HoverMenu";
import { InvestigationLookupPanel } from "./InvestigationLookupPanel";
import { PathLink } from "./PathLink";
import { VendorHintBadges } from "./VendorHintBadges";

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

function methodTone(method: string, confidence: string): BadgeTone {
  if (method === "NONE") return "review";
  if (confidence === "TENTATIVE") return "accent";
  return "ready";
}

function confidenceTierTone(confidence: string): BadgeTone {
  const conf = (confidence || "UNKNOWN").toUpperCase();
  if (conf === "CONFIRMED") return "ready";
  if (conf === "TENTATIVE") return "accent";
  return "review";
}

export function InvestigationInbox({ stamp }: Props) {
  const { ask, dialog } = useReviewDecision();
  const [revision, setRevision] = useState(0);
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
  }, [stamp]);

  useEffect(() => {
    let current = true;
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
            if (!current) return;
            setGroups(res.groups);
            setTotal(res.total);
          })
          .catch((err: Error) => { if (current) setError(err.message); })
          .finally(() => { if (current) setLoading(false); });
      } else {
        fetchInvestigation(stamp, {
          bucket: bucket || undefined,
          q: query || undefined,
          limit: 500,
        })
          .then((res) => {
            if (!current) return;
            setItems(res.items);
            setTotal(res.total);
          })
          .catch((err: Error) => { if (current) setError(err.message); })
          .finally(() => { if (current) setLoading(false); });
      }
    }, query ? 250 : 0);
    return () => { current = false; clearTimeout(timer); };
  }, [stamp, bucket, query, view, revision]);

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
    setMsg(`Bulk ${action}: ${res.count} paths`);
  }

  async function handleSetVendor(row: InvestigationItem) {
    ask({ title: "Assign vendor", detail: row.current_path, action: "Save correction", fields: [{ label: "Company name" }, { label: "Keywords (optional, comma-separated)", optional: true, value: row.item_name }], accept: async ([vendor, keywords]) => {
    await apply(row, "set_vendor", vendor, {
      reason: "vendor_known",
      keywords: keywords ? keywords.split(",").map((k) => k.trim()).filter(Boolean) : [],
    });
    }});
  }

  async function handleGroupSetVendor(group: InvestigationGroup) {
    ask({ title: "Assign vendor to group", detail: `${group.paths.length} paths in ${group.group_key}`, action: "Save correction", fields: [{ label: "Company name", value: group.group_key.replace(/\./g, " ") }], accept: async ([vendor]) => {
    await bulkApply(group.paths, "set_vendor", vendor, {
      reason: "vendor_known",
      keywords: [group.group_key.toLowerCase(), vendor.toLowerCase()],
    });
    }});
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
    ask({ title: "Create review bucket", detail: row.current_path, action: "Save correction", fields: [{ label: "Bucket name", value: newBucket }, { label: "Description (optional)", optional: true }], accept: async ([name, desc]) => {
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
    }});
  }

  async function handleLinkParent(row: InvestigationItem) {
    ask({ title: "Link parent product", detail: row.current_path, action: "Save correction", fields: [{ label: "Parent product path" }], accept: async ([parent]) => {
    await apply(row, "link_parent", parent, { reason: "is_component" });
    }});
  }

  async function handleGroupLinkParent(group: InvestigationGroup) {
    ask({ title: "Link group to parent", detail: `${group.paths.length} paths in ${group.group_key}`, action: "Save correction", fields: [{ label: "Parent product path" }], accept: async ([parent]) => {
    await bulkApply(group.paths, "link_parent", parent, { reason: "is_component" });
    }});
  }

  async function handleResolved(row: InvestigationItem) {
    await apply(row, "mark_resolved", "", { reason: "false_positive" });
  }

  async function handleAddVendor() {
    ask({ title: "Add vendor feedback", detail: `Save a vendor correction for run ${stamp}.`, action: "Save correction", fields: [{ label: "Company name" }, { label: "Keywords (optional, comma-separated)", optional: true }], accept: async ([company, keywords]) => {
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
    }});
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
    <div className="review-workspace">
      {dialog}
      <WorkScope title={view === "groups" ? "Resolve matching prefixes" : "Resolve one item at a time"} detail={view === "groups" ? "Bulk corrections apply to every path in a prefix group. Switch to All items when only one path needs a different vendor or parent." : "Inspect the evidence for each path and record its vendor, parent product or review bucket."} />
      <div className="toolbar">
        <Tabs
          aria-label="Investigation view"
          value={view}
          onValueChange={(next) => setView(next as "list" | "groups")}
          items={[
            {
              value: "groups",
              label: "By prefix (bulk)",
              title: "Grouped view for bulk vendor/parent fixes",
            },
            {
              value: "list",
              label: "All items",
              title: "List view for per-item work",
            },
          ]}
        />
        <span className="count-muted">
          {loading ? <LoadingStatus /> : `${total.toLocaleString()} ${view === "groups" ? "groups" : "items"}`}
          {feedback ? ` · ${feedback.corrections.length} corrections` : ""}
        </span>
        <Button
          variant="secondary"
          title="Add a vendor keyword to feedback for the next scan"
          onClick={() => void handleAddVendor()}
        >
          Add vendor
        </Button>
        <Button
          variant="ghost"
          title="Download corrections CSV for engine tuning"
          onClick={() => void investigationFeedbackExportDownload(stamp)}
        >
          Export feedback CSV
        </Button>
      </div>

      {bucket && BUCKET_HINTS[bucket] && (
        <div className="banner dry">{BUCKET_HINTS[bucket]}</div>
      )}

      {msg && <div className="banner dry" role="status">{msg}</div>}
      {error && <WorkIssue message={error} retry={() => setRevision(v => v + 1)} />}

      <details className="work-disclosure"><summary>Look up vendor evidence</summary><InvestigationLookupPanel /></details>

      {!loading && view === "groups" && groups.length === 0 && !error && (
        <div className="empty">No investigation groups match your filters.</div>
      )}

      {!loading && view === "list" && items.length === 0 && !error && (
        <div className="empty">No investigation items match your filters.</div>
      )}

      {view === "groups" && groups.length > 0 && (
        <VirtualTable
          items={groups}
          colCount={6}
          estimateSize={64}
          tableClassName="data-table investigation-table"
          header={
            <tr>
              <th>Prefix / group</th>
              <th>Count</th>
              <th>Bucket</th>
              <th>ID</th>
              <th>Samples</th>
              <th>Bulk actions</th>
            </tr>
          }
          renderRow={(group, _index, rowAttrs) => (
            <tr
              key={group.group_key}
              className={selectedGroup === group.group_key ? "inv-vendor-set" : ""}
              onClick={() => setSelectedGroup(group.group_key)}
              {...rowAttrs}
            >
              <td>
                <Button size="sm" variant="ghost" aria-pressed={selectedGroup === group.group_key} onClick={() => setSelectedGroup(group.group_key)}>{group.group_key}</Button>
              </td>
              <td>{group.count}</td>
              <td>
                <Badge tone="accent">{group.bucket}</Badge>
              </td>
              <td>
                <Badge tone={methodTone(group.id_method, "")}>{group.id_method}</Badge>
              </td>
              <td className="count-muted">
                {group.sample_items.slice(0, 2).join(" · ")}
              </td>
              <td className="inv-actions">
                {group.bucket === "_unverified_vendor" && (
                  <Button
                    variant="primary"
                    size="sm"
                    title="Add this prefix to vendor_overrides.json so future scans recognize the vendor"
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleGroupAddVendorDb(group).catch((err: Error) => setError(err.message));
                    }}
                  >
                    Add to DB
                  </Button>
                )}
                <Button
                  variant="secondary"
                  size="sm"
                  title="Set vendor name for every item in this prefix group"
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleGroupSetVendor(group);
                  }}
                >
                  Set vendor
                </Button>
                {(group.bucket === "_sample_pack" || group.bucket === "_likely_component") && (
                  <Button
                    variant="secondary"
                    size="sm"
                    title="Link all items in this group to a parent product folder"
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleGroupLinkParent(group);
                    }}
                  >
                    Link parent
                  </Button>
                )}
              </td>
            </tr>
          )}
        />
      )}

      {view === "list" && items.length > 0 && (
        <VirtualTable
          items={items}
          colCount={5}
          estimateSize={88}
          tableClassName="data-table investigation-table"
          header={
            <tr>
              <th>Section</th>
              <th>Item</th>
              <th>Bucket</th>
              <th>ID</th>
              <th>Actions</th>
            </tr>
          }
          renderRow={(row, _index, rowAttrs) => {
            const status = rowStatus(row);
            const vendorOverride = vendorMap[row.current_path];
            return (
              <tr
                key={`${row.current_path}-${row.item_name}`}
                className={status ? `inv-${status}` : ""}
                {...rowAttrs}
              >
                <td>
                  <code>{row.section}</code>
                </td>
                <td>
                  <div>{row.item_name}</div>
                  <PathLink path={row.current_path} />
                  <VendorHintBadges path={row.current_path} name={row.item_name} />
                  {vendorOverride && (
                    <div className="count-muted">vendor → {vendorOverride}</div>
                  )}
                  {parentMap[row.current_path] && (
                    <div className="count-muted">parent → {parentMap[row.current_path]}</div>
                  )}
                </td>
                <td>
                  <Badge tone="accent">
                    {bucketMap[row.current_path] ?? row.investigation_bucket}
                  </Badge>
                  {status === "resolved" && <Badge tone="ready">resolved</Badge>}
                </td>
                <td>
                  <Badge tone={methodTone(row.id_method, row.id_confidence)}>
                    {row.id_method}
                  </Badge>
                  <Badge
                    tone={confidenceTierTone(row.id_confidence)}
                    className="conf-cat-badge"
                    title="CONF-CAT tier"
                  >
                    {row.id_confidence || "UNKNOWN"}
                  </Badge>
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
                    aria-label="Reassign investigation bucket"
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
          }}
        />
      )}
    </div>
  );
}
