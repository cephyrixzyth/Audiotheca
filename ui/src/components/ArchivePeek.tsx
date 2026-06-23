import { useEffect, useState } from "react";
import { fetchArchivePeek } from "../api/client";
import type { ArchivePeekItem } from "../types";
import { PathLink } from "./PathLink";

interface Props {
  stamp: string;
}

export function ArchivePeek({ stamp }: Props) {
  const [items, setItems] = useState<ArchivePeekItem[]>([]);
  const [total, setTotal] = useState(0);
  const [verdictCounts, setVerdictCounts] = useState<Record<string, number>>({});
  const [deleteFiles, setDeleteFiles] = useState(0);
  const [deleteMb, setDeleteMb] = useState(0);
  const [verdict, setVerdict] = useState("MATCHES_EXTRACTED_FOLDER");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const timer = setTimeout(() => {
      fetchArchivePeek(stamp, {
        verdict: verdict || undefined,
        q: query || undefined,
        limit: 200,
      })
        .then((res) => {
          setItems(res.items);
          setTotal(res.total);
          setVerdictCounts(res.verdict_counts);
          setDeleteFiles(res.delete_candidate_files);
          setDeleteMb(res.delete_candidate_mb);
        })
        .finally(() => setLoading(false));
    }, query ? 250 : 0);
    return () => clearTimeout(timer);
  }, [stamp, verdict, query]);

  return (
    <div>
      <div className="kpi-grid" style={{ marginBottom: "1rem" }}>
        <div className="kpi">
          <div className="label">Delete candidates</div>
          <div className="value">{deleteFiles}</div>
        </div>
        <div className="kpi">
          <div className="label">Recoverable</div>
          <div className="value">{(deleteMb / 1024).toFixed(1)} GB</div>
        </div>
      </div>

      <div className="bucket-grid" style={{ marginBottom: "1rem" }}>
        {Object.entries(verdictCounts).map(([name, count]) => (
          <button
            key={name}
            type="button"
            className={`bucket-chip ${verdict === name ? "active-chip" : ""}`}
            onClick={() => setVerdict(name)}
          >
            {name}
            <strong>{count}</strong>
          </button>
        ))}
        <button
          type="button"
          className={`bucket-chip ${verdict === "" ? "active-chip" : ""}`}
          onClick={() => setVerdict("")}
        >
          All
        </button>
      </div>

      <div className="toolbar">
        <label>
          Search
          <input
            type="search"
            placeholder="Archive path, product…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <span className="count-muted">
          {loading ? "Loading…" : `${total} archive rows`}
        </span>
      </div>

      {items.length === 0 && !loading && (
        <div className="empty">No archive peek rows for this filter.</div>
      )}

      {items.length > 0 && (
        <table className="data-table">
          <thead>
            <tr>
              <th>Verdict</th>
              <th>Item</th>
              <th>Archive</th>
              <th>Size</th>
              <th>Extracted folder</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={row.archive_path}>
                <td>
                  <span
                    className={`badge ${
                      row.verdict === "MATCHES_EXTRACTED_FOLDER" ? "ready" : "bucket"
                    }`}
                  >
                    {row.verdict}
                  </span>
                </td>
                <td>
                  <div>{row.item_name}</div>
                  <PathLink path={row.item_path} />
                </td>
                <td>
                  <div>{row.archive_name}</div>
                  <PathLink path={row.archive_path} />
                </td>
                <td>{row.archive_size_mb != null ? `${row.archive_size_mb} MB` : "—"}</td>
                <td>{row.extracted_folder}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
