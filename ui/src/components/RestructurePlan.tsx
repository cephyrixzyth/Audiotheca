import { useEffect, useState } from "react";
import { fetchRestructure } from "../api/client";
import type { RestructureItem } from "../types";
import { PathLink } from "./PathLink";

interface Props {
  stamp: string;
}

export function RestructurePlan({ stamp }: Props) {
  const [items, setItems] = useState<RestructureItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState("READY");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);

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

  return (
    <div>
      <div className="toolbar">
        <label>
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            <option value="READY">READY</option>
            <option value="NEEDS REVIEW">NEEDS REVIEW</option>
            <option value="DEST EXISTS (merge)">DEST EXISTS (merge)</option>
          </select>
        </label>
        <label>
          Search
          <input
            type="search"
            placeholder="Name, vendor, path…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <span className="count-muted">
          {loading ? "Loading…" : `${total.toLocaleString()} routes`}
        </span>
      </div>

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
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr key={`${row.current_path}-${row.item_name}`}>
                <td>
                  <code>{row.section}</code>
                </td>
                <td>
                  <div>{row.item_name}</div>
                  <PathLink path={row.current_path} />
                </td>
                <td>{row.vendor}</td>
                <td>
                  {row.id_method}
                  <div className="path">{row.id_confidence}</div>
                </td>
                <td>
                  <span
                    className={`badge ${
                      row.status === "READY" ? "ready" : "review"
                    }`}
                  >
                    {row.status}
                  </span>
                </td>
                <td>
                  <PathLink path={row.planned_destination} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
