import { useEffect, useState } from "react";
import {
  approveSceneRename,
  executeSceneRenames,
  fetchSceneFeedback,
  fetchSceneRenames,
  flagSceneMissingPart01,
  overrideSceneName,
  rejectSceneRename,
} from "../api/client";
import type { SceneRenameItem } from "../types";
import { PathLink } from "./PathLink";

interface Props {
  stamp: string;
}

export function SceneRenames({ stamp }: Props) {
  const [items, setItems] = useState<SceneRenameItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [approved, setApproved] = useState<string[]>([]);
  const [rejected, setRejected] = useState<Record<string, string>>({});
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    fetchSceneFeedback(stamp)
      .then((state) => {
        setApproved(state.approved_renames ?? []);
        setRejected(state.rejected_paths ?? {});
        setOverrides(state.name_overrides ?? {});
      })
      .catch(() => {
        setApproved([]);
        setRejected({});
        setOverrides({});
      });
  }, [stamp]);

  useEffect(() => {
    setLoading(true);
    fetchSceneRenames(stamp)
      .then(setItems)
      .finally(() => setLoading(false));
  }, [stamp]);

  async function handleApprove(row: SceneRenameItem) {
    const res = await approveSceneRename(stamp, {
      source_path: row.source_path,
      scene_id: row.scene_id,
    });
    setApproved(res.state.approved_renames ?? []);
    setMsg(`Approved rename for ${row.scene_id}`);
  }

  async function handleReject(row: SceneRenameItem) {
    await rejectSceneRename(stamp, {
      source_path: row.source_path,
      scene_id: row.scene_id,
      reason: "bad_inference",
    });
    setRejected((prev) => ({ ...prev, [row.source_path]: "bad_inference" }));
    setApproved((prev) => prev.filter((path) => path !== row.source_path));
    setMsg(`Rejected rename for ${row.scene_id}`);
  }

  async function handleOverride(row: SceneRenameItem) {
    const proposed = window
      .prompt("Proposed folder name:", overrides[row.source_path] ?? row.proposed_name)
      ?.trim();
    if (!proposed) return;
    const res = await overrideSceneName(stamp, {
      source_path: row.source_path,
      proposed_name: proposed,
      scene_id: row.scene_id,
      old_name: row.proposed_name,
    });
    setOverrides(res.state.name_overrides ?? {});
    setMsg(`Name override saved for ${row.scene_id}`);
  }

  async function handleMissingPart01(row: SceneRenameItem) {
    await flagSceneMissingPart01(stamp, {
      source_path: row.source_path,
      scene_id: row.scene_id,
    });
    setRejected((prev) => ({ ...prev, [row.source_path]: "missing_part01" }));
    setMsg(`Flagged ${row.scene_id} as missing part01`);
  }

  async function handleExecute(dryRun: boolean) {
    const res = await executeSceneRenames(stamp, {
      dry_run: dryRun,
      confirm_live: !dryRun ? true : undefined,
    });
    if (res.error) {
      setMsg(res.error);
      return;
    }
    setMsg(
      dryRun
        ? `Dry run: ${res.renamed} rename(s) would apply`
        : `Live: ${res.renamed} folder(s) renamed (${res.failed} failed)`,
    );
  }

  if (loading) return <div className="count-muted">Loading scene renames…</div>;
  if (items.length === 0) return <div className="empty">No scene rename plans for this run.</div>;

  return (
    <div>
      <div className="banner dry">
        Approve renames here, then dry-run execute. Live renames require explicit confirmation.
      </div>

      <div className="toolbar">
        <button type="button" className="keeper-btn" onClick={() => void handleExecute(true)}>
          Dry-run approved
        </button>
        <button
          type="button"
          className="primary-btn"
          onClick={() => {
            if (window.confirm("Apply approved scene renames on disk? This moves folders.")) {
              void handleExecute(false);
            }
          }}
          disabled={approved.length === 0}
        >
          Execute approved ({approved.length})
        </button>
        {msg && <span className="count-muted">{msg}</span>}
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th>Scene ID</th>
            <th>Proposed name</th>
            <th>Multipart</th>
            <th>Source</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => {
            const isApproved = approved.includes(row.source_path);
            const isRejected = row.source_path in rejected;
            const displayName = overrides[row.source_path] ?? row.proposed_name;
            return (
              <tr key={row.source_path} className={isRejected ? "rejected-row" : undefined}>
                <td>
                  <code>{row.scene_id}</code>
                  {isApproved && <span className="badge ready">approved</span>}
                  {isRejected && <span className="badge bucket">rejected</span>}
                </td>
                <td>
                  <strong>{displayName}</strong>
                  <PathLink path={row.destination_path} />
                </td>
                <td>
                  <span className="badge bucket">{row.multipart_diagnosis || "—"}</span>
                </td>
                <td>
                  <PathLink path={row.source_path} />
                </td>
                <td>
                  <button type="button" className="keeper-btn" onClick={() => void handleApprove(row)}>
                    Approve
                  </button>{" "}
                  <button type="button" className="keeper-btn" onClick={() => void handleOverride(row)}>
                    Edit name
                  </button>{" "}
                  <button type="button" className="keeper-btn" onClick={() => void handleReject(row)}>
                    Reject
                  </button>{" "}
                  <button type="button" className="keeper-btn" onClick={() => void handleMissingPart01(row)}>
                    Missing part01
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
