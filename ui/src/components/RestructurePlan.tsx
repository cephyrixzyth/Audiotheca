import { useEffect, useMemo, useState } from "react";
import {
  approveRestructureSection,
  executeRestructure,
  fetchRestructure,
  fetchRestructureFeedback,
  overrideRestructureDest,
  type RestructureExecuteResponse,
} from "../api/client";
import type { RestructureItem } from "../types";
import { Badge, Button } from "../ui";
import { useLibraryRoot } from "../hooks/useLibraryRoot";
import { PathLink } from "./PathLink";
import { useContextSidebar } from "./ContextSidebar";
import {
  ExecuteResultsPanel,
  restructureExecuteRows,
  type ExecuteResultRow,
} from "./ExecuteResultsPanel";

interface Props {
  stamp: string;
}

export function RestructurePlan({ stamp }: Props) {
  const libraryRoot = useLibraryRoot();
  const { query } = useContextSidebar();
  const [items, setItems] = useState<RestructureItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("READY");
  const [loading, setLoading] = useState(true);
  const [approvedSections, setApprovedSections] = useState<string[]>([]);
  const [destOverrides, setDestOverrides] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [executeResults, setExecuteResults] = useState<ExecuteResultRow[]>([]);
  const [executeDryRun, setExecuteDryRun] = useState(true);
  const [executeSummary, setExecuteSummary] = useState<{ staged: number; failed: number } | null>(
    null,
  );

  useEffect(() => {
    fetchRestructureFeedback(stamp)
      .then((state) => {
        setApprovedSections(state.section_approvals ?? []);
        setDestOverrides(state.path_dest_overrides ?? {});
      })
      .catch(() => {
        setApprovedSections([]);
        setDestOverrides({});
      });
  }, [stamp]);

  useEffect(() => {
    setLoading(true);
    const timer = setTimeout(() => {
      fetchRestructure(stamp, {
        status: status || undefined,
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
  }, [stamp, status, query]);

  const sections = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const row of items) {
      counts[row.section] = (counts[row.section] ?? 0) + 1;
    }
    return Object.entries(counts).sort(([a], [b]) => a.localeCompare(b));
  }, [items]);

  async function handleApproveSection(section: string) {
    const res = await approveRestructureSection(stamp, section);
    setApprovedSections(res.state.section_approvals ?? []);
    setMsg(`Section '${section}' approved for next live run (cli.py --live)`);
  }

  async function handleOverride(row: RestructureItem) {
    const dest = window.prompt(
      "Relative destination (e.g. a/Vendor/Product):",
      destOverrides[row.current_path] ?? row.planned_destination,
    )?.trim();
    if (!dest) return;
    const res = await overrideRestructureDest(stamp, {
      path: row.current_path,
      destination: dest,
      item_name: row.item_name,
      old_destination: row.planned_destination,
    });
    setDestOverrides(res.state.path_dest_overrides ?? {});
    setMsg(`Destination override saved for ${row.item_name}`);
  }

  async function handleExecute(dryRun: boolean, confirmLive = false) {
    const res: RestructureExecuteResponse = await executeRestructure(stamp, {
      dry_run: dryRun,
      confirm_live: confirmLive || undefined,
      root: libraryRoot || undefined,
    });
    if (!res.ok && !res.results?.length) {
      setExecuteResults([]);
      setExecuteSummary(null);
      setMsg(res.error ?? "Approve sections with READY items first");
      return;
    }
    setExecuteDryRun(dryRun);
    setExecuteResults(restructureExecuteRows(res.results ?? [], dryRun));
    setExecuteSummary({ staged: res.moved, failed: res.failed });
    setMsg(
      dryRun
        ? `Dry run: ${res.moved} move(s) in sections ${res.approved_sections?.join(", ")}`
        : `Live: ${res.moved} move(s) applied (${res.failed} failed)`,
    );
  }

  return (
    <div>
      <div className="banner dry">
        Approve sections here for CLI or UI execute. Destination overrides apply on the next scan.
      </div>

      <div className="toolbar" style={{ marginBottom: "0.5rem" }}>
        <Button
          variant="secondary"
          title="Simulate moves for approved sections without changing disk"
          onClick={() => void handleExecute(true)}
        >
          Dry-run approved sections
        </Button>
        <Button
          variant="primary"
          title="Apply READY moves in approved sections on the library share"
          onClick={() => {
            if (window.confirm("Move READY items in approved sections on disk?")) {
              void handleExecute(false, true);
            }
          }}
          disabled={approvedSections.length === 0}
        >
          Execute approved ({approvedSections.length} sections)
        </Button>
      </div>

      {sections.length > 0 && (
        <div className="toolbar" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
          {sections.map(([section, count]) => {
            const approved = approvedSections.includes(section);
            return (
              <Button
                key={section}
                variant={approved ? "primary" : "secondary"}
                title={
                  approved
                    ? `Section ${section} is approved for live execute`
                    : `Approve all READY routes in section ${section}`
                }
                onClick={() => void handleApproveSection(section)}
              >
                {approved ? "✓ " : ""}Section {section} ({count})
              </Button>
            );
          })}
        </div>
      )}

      <div className="toolbar">
        <label title="Filter by route readiness — READY items can move when section is approved">
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            <option value="READY">READY</option>
            <option value="NEEDS REVIEW">NEEDS REVIEW</option>
            <option value="DEST EXISTS (merge)">DEST EXISTS (merge)</option>
          </select>
        </label>
        <span className="count-muted">
          {loading ? "Loading…" : `${total.toLocaleString()} routes`}
          {approvedSections.length ? ` · ${approvedSections.length} sections approved` : ""}
        </span>
      </div>

      {msg && <div className="banner dry">{msg}</div>}

      {executeResults.length > 0 && (
        <ExecuteResultsPanel
          title="Restructure execute results"
          dryRun={executeDryRun}
          results={executeResults}
          staged={executeSummary?.staged}
          failed={executeSummary?.failed}
        />
      )}

      {!loading && items.length === 0 && (
        <div className="empty">No restructure routes match your filters.</div>
      )}

      {items.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Section</th>
              <th>Item</th>
              <th>Vendor</th>
              <th>ID</th>
              <th>Status</th>
              <th>Destination</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => {
              const override = destOverrides[row.current_path];
              return (
                <tr key={`${row.current_path}-${row.item_name}`}>
                  <td>
                    <code>{row.section}</code>
                    {approvedSections.includes(row.section) && (
                      <Badge tone="ready">approved</Badge>
                    )}
                  </td>
                  <td>
                    <div>{row.item_name}</div>
                    <PathLink
                      path={row.current_path}
                      secondaryPath={override ?? row.planned_destination}
                      dualPane
                    />
                  </td>
                  <td>{row.vendor}</td>
                  <td>
                    {row.id_method}
                    <div className="path">{row.id_confidence}</div>
                  </td>
                  <td>
                    <Badge tone={row.status === "READY" ? "ready" : "review"}>{row.status}</Badge>
                  </td>
                  <td>
                    <PathLink path={override ?? row.planned_destination} />
                    {override && <div className="count-muted">override</div>}
                  </td>
                  <td>
                    <Button
                      variant="secondary"
                      size="sm"
                      title="Override planned destination relative to library root (e.g. a/Vendor/Product)"
                      onClick={() => void handleOverride(row)}
                    >
                      Edit dest
                    </Button>
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
