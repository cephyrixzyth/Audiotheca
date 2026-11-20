import { useReviewDecision, WorkIssue, WorkScope } from "./ReviewWorkbench";
import { LoadingStatus } from "../ui/LoadingStatus";
import { useEffect, useMemo, useState } from "react";
import {
  approveSceneRename,
  executeSceneRenames,
  fetchSceneFeedback,
  fetchSceneRenames,
  flagSceneMissingPart01,
  overrideSceneName,
  rejectSceneRename,
  type SceneExecuteResponse,
} from "../api/client";
import type { SceneRenameItem } from "../types";
import { Badge, Button, VirtualTable } from "../ui";
import { listHasPath, lookupByPath, pathKey } from "../utils/pathKey";
import { useContextSidebar } from "./ContextSidebar";
import { PathLink } from "./PathLink";
import {
  ExecuteResultsPanel,
  sceneExecuteRows,
  type ExecuteResultRow,
} from "./ExecuteResultsPanel";

interface Props {
  stamp: string;
}

export function SceneRenames({ stamp }: Props) {
  const { ask, dialog } = useReviewDecision();
  const [readError, setReadError] = useState("");
  const [revision, setRevision] = useState(0);
  const { query } = useContextSidebar();
  const [items, setItems] = useState<SceneRenameItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [approved, setApproved] = useState<string[]>([]);
  const [rejected, setRejected] = useState<Record<string, string>>({});
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);
  const [executeResults, setExecuteResults] = useState<ExecuteResultRow[]>([]);
  const [executeDryRun, setExecuteDryRun] = useState(true);
  const [executeSummary, setExecuteSummary] = useState<{ staged: number; failed: number } | null>(
    null,
  );

  async function refreshFeedback() {
    const state = await fetchSceneFeedback(stamp);
    setApproved(state.approved_renames ?? []);
    setRejected(state.rejected_paths ?? {});
    setOverrides(state.name_overrides ?? {});
  }

  useEffect(() => {
    refreshFeedback().catch(() => {
      setApproved([]);
      setRejected({});
      setOverrides({});
    });
  }, [stamp]);

  useEffect(() => {
    let current = true;
    setReadError(""); setLoading(true);
    fetchSceneRenames(stamp)
      .then(rows => { if (current) setItems(rows); })
      .catch((err: Error) => { if (current) setReadError(err.message); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [stamp, revision]);

  async function handleApprove(row: SceneRenameItem) {
    try {
      const res = await approveSceneRename(stamp, {
        source_path: row.source_path,
        scene_id: row.scene_id,
      });
      setApproved(res.state.approved_renames ?? []);
      setMsg(`Approved rename for ${row.scene_id}`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Approve failed");
    }
  }

  async function handleReject(row: SceneRenameItem) {
    try {
      await rejectSceneRename(stamp, {
        source_path: row.source_path,
        scene_id: row.scene_id,
        reason: "bad_inference",
      });
      await refreshFeedback();
      setMsg(`Rejected rename for ${row.scene_id}`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Reject failed");
    }
  }

  async function handleOverride(row: SceneRenameItem) {
    const current = lookupByPath(overrides, row.source_path) ?? row.proposed_name;
    ask({ title: "Edit folder name", detail: row.source_path, action: "Save folder name", fields: [{ label: "Proposed folder name", value: current }], accept: async ([proposed]) => {
      const res = await overrideSceneName(stamp, {
        source_path: row.source_path,
        proposed_name: proposed,
        scene_id: row.scene_id,
        old_name: row.proposed_name,
      });
      setOverrides(res.state.name_overrides ?? {});
      setMsg(`Name override saved for ${row.scene_id}`);
    }});
  }

  async function handleMissingPart01(row: SceneRenameItem) {
    try {
      await flagSceneMissingPart01(stamp, {
        source_path: row.source_path,
        scene_id: row.scene_id,
      });
      await refreshFeedback();
      setMsg(`Flagged ${row.scene_id} as missing part01`);
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Flag failed");
    }
  }

  async function handleExecute(dryRun: boolean) {
    try {
      const res: SceneExecuteResponse = await executeSceneRenames(stamp, {
        dry_run: dryRun,
        confirm_live: !dryRun ? true : undefined,
      });
      if (!res.ok && !res.partial && !res.results?.length) {
        setExecuteResults([]);
        setExecuteSummary(null);
        setMsg(res.error ?? "Approve scene renames first");
        return;
      }
      setExecuteDryRun(dryRun);
      setExecuteResults(sceneExecuteRows(res.results ?? [], dryRun));
      setExecuteSummary({ staged: res.renamed, failed: res.failed });
      const outcome = res.partial ? "partial" : res.ok ? "ok" : "failed";
      setMsg(
        dryRun
          ? `Dry run (${outcome}): ${res.renamed} rename(s) would apply (${res.failed} failed)`
          : `Live (${outcome}): ${res.renamed} folder(s) renamed (${res.failed} failed)`,
      );
      if (!dryRun) {
        const [nextItems] = await Promise.all([fetchSceneRenames(stamp), refreshFeedback()]);
        setItems(nextItems);
      }
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Execute failed");
    }
  }

  const visibleItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (row) =>
        row.scene_id.toLowerCase().includes(q) ||
        row.proposed_name.toLowerCase().includes(q) ||
        row.source_path.toLowerCase().includes(q) ||
        (lookupByPath(overrides, row.source_path) ?? "").toLowerCase().includes(q),
    );
  }, [items, query, overrides]);

  if (loading) return <LoadingStatus>Loading scene renames…</LoadingStatus>;
  if (readError) return <WorkIssue message={readError} retry={() => setRevision(v => v + 1)} />;
  if (items.length === 0) return <div className="empty">No scene rename plans for this run.</div>;

  return (
    <div className="review-workspace">
      {dialog}
      <WorkScope title="Rename approved folders" detail="Compare the scene ID and source folder with the proposed product name. Approvals apply across the current run.">
        <Button
          variant="secondary"
          title="Simulate approved scene folder renames without moving disk"
          onClick={() => void handleExecute(true).catch((err: Error) => setMsg(err.message))}
        >
          Dry-run approved
        </Button>
        <Button
          variant="danger"
          title="Rename approved scene-hash folders to product names on disk"
          onClick={() => ask({title: "Rename approved folders?", detail: "This applies the saved approvals for run " + stamp + " on disk.", scope: <pre>{approved.join("\n")}</pre>, writesFiles: true, action: "Rename approved folders", accept: () => handleExecute(false)})}
          disabled={approved.length === 0}
        >
          Execute approved ({approved.length})
        </Button>
      </WorkScope>
      {visibleItems.length === 0 && <p className="empty">No scene renames match this search. Saved approvals are listed in the execution confirmation.</p>}
      {msg && <p role="status" className="banner dry">{msg}</p>}
      {executeResults.length > 0 && (
        <ExecuteResultsPanel
          title="Scene rename execute results"
          dryRun={executeDryRun}
          results={executeResults}
          staged={executeSummary?.staged}
          failed={executeSummary?.failed}
          okDryRunLabel="Would rename"
          okLiveLabel="Renamed"
        />
      )}

      <VirtualTable
        items={visibleItems}
        colCount={5}
        estimateSize={80}
        header={
          <tr>
            <th>Scene ID</th>
            <th>Proposed name</th>
            <th>Multipart</th>
            <th>Source</th>
            <th>Actions</th>
          </tr>
        }
        renderRow={(row, _index, rowAttrs) => {
          const isApproved = listHasPath(approved, row.source_path);
          const isRejected = lookupByPath(rejected, row.source_path) != null;
          const displayName = lookupByPath(overrides, row.source_path) ?? row.proposed_name;
          return (
            <tr key={pathKey(row.source_path)} className={isRejected ? "rejected-row" : undefined} {...rowAttrs}>
              <td>
                <code>{row.scene_id}</code>
                {isApproved && <Badge tone="ready">approved</Badge>}
                {isRejected && <Badge tone="accent">rejected</Badge>}
              </td>
              <td>
                <strong>{displayName}</strong>
                <PathLink path={row.destination_path} />
              </td>
              <td>
                <Badge tone="accent" title={row.multipart_diagnosis || undefined}>
                  {row.multipart_diagnosis_label || row.multipart_diagnosis || "—"}
                </Badge>
              </td>
              <td>
                <PathLink path={row.source_path} />
              </td>
              <td>
                <Button
                  variant="secondary"
                  size="sm"
                  title="Include this rename in the next dry-run or live execute"
                  onClick={() => void handleApprove(row)}
                >
                  Approve
                </Button>{" "}
                <Button
                  variant="secondary"
                  size="sm"
                  title="Edit the proposed product folder name"
                  onClick={() => void handleOverride(row)}
                >
                  Edit name
                </Button>{" "}
                <Button
                  variant="secondary"
                  size="sm"
                  title="Skip this rename — engine will not propose it again"
                  onClick={() => void handleReject(row)}
                >
                  Reject
                </Button>{" "}
                <Button
                  variant="secondary"
                  size="sm"
                  title="Mark multipart set as missing part 01 — defers rename"
                  onClick={() => void handleMissingPart01(row)}
                >
                  Missing part01
                </Button>
              </td>
            </tr>
          );
        }}
      />
    </div>
  );
}
