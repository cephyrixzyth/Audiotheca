import { useEffect, useState } from "react";
import { fetchSceneRenames } from "../api/client";
import type { SceneRenameItem } from "../types";
import { PathLink } from "./PathLink";

interface Props {
  stamp: string;
}

export function SceneRenames({ stamp }: Props) {
  const [items, setItems] = useState<SceneRenameItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchSceneRenames(stamp)
      .then(setItems)
      .finally(() => setLoading(false));
  }, [stamp]);

  if (loading) return <div className="count-muted">Loading scene renames…</div>;
  if (items.length === 0) return <div className="empty">No scene rename plans for this run.</div>;

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Scene ID</th>
          <th>Proposed name</th>
          <th>Multipart</th>
          <th>Source</th>
        </tr>
      </thead>
      <tbody>
        {items.map((row) => (
          <tr key={row.source_path}>
            <td>
              <code>{row.scene_id}</code>
            </td>
            <td>
              <strong>{row.proposed_name}</strong>
              <PathLink path={row.destination_path} />
            </td>
            <td>
              <span className="badge bucket">{row.multipart_diagnosis}</span>
            </td>
            <td>
              <PathLink path={row.source_path} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
