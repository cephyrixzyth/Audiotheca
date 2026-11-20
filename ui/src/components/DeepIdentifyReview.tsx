import { WorkScope, WorkIssue } from "./ReviewWorkbench";
import { LoadingStatus } from "../ui/LoadingStatus";
import { useEffect, useMemo, useState } from "react";
import { fetchDeepIdentify } from "../api/client";
import type { DeepIdentifyItem } from "../types";
import { matchesDeepIdentifyQuery } from "../utils/deepIdentifyQuery";
import { Badge, VirtualTable } from "../ui";
import { useContextSidebar } from "./ContextSidebar";
import { PathLink } from "./PathLink";

interface Props {
  stamp: string;
}

export function DeepIdentifyReview({ stamp }: Props) {
  const [revision, setRevision] = useState(0);
  const [method, setMethod] = useState("");
  const { query } = useContextSidebar();
  const [items, setItems] = useState<DeepIdentifyItem[]>([]);
  const [fetchedTotal, setFetchedTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchDeepIdentify(stamp, { limit: 2000 })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setFetchedTotal(res.total);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setItems([]);
        setFetchedTotal(0);
        setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [stamp, revision]);

  const q = query.trim().toLowerCase();
  const visible = useMemo(() => items.filter((row) => matchesDeepIdentifyQuery(row, q)), [items, q]);

  const methodCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const row of visible) {
      const key = row.method || "UNKNOWN";
      counts[key] = (counts[key] ?? 0) + 1;
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [visible]);

  const matches = method ? visible.filter(row => (row.method || "UNKNOWN") === method) : visible;
  if (loading) return <LoadingStatus>Loading deep identify results…</LoadingStatus>;
  if (error) return <WorkIssue message={error} retry={() => setRevision(v => v + 1)} />;
  if (items.length === 0) {
    return (
      <div className="empty">
        No deep-identify recoveries for this run. Enable the deep identify phase on the next scan.
      </div>
    );
  }
  if (visible.length === 0) {
    return <div className="empty">No deep-identify recoveries match your search.</div>;
  }

  return (
    <div className="review-workspace">
      <WorkScope title="Inspect recovered identities" detail="Check which method identified a vendor and read the evidence before using it in a move plan.">
        <label>Identification method <select value={method} onChange={event => setMethod(event.target.value)}>
          <option value="">All methods</option>
          {methodCounts.map(([name, count]) => <option key={name} value={name}>{name} ({count})</option>)}
        </select></label>
      </WorkScope>
      {fetchedTotal > items.length ? (
        <div className="banner warn">
          Showing the first {items.length.toLocaleString()} of {fetchedTotal.toLocaleString()} recoveries.
        </div>
      ) : null}
      <div className="toolbar compact-toolbar">
        <span className="count-muted">
          {matches.length.toLocaleString()} recover{matches.length === 1 ? "y" : "ies"}
          {q ? ` matching “${query.trim()}”` : ""}
          {q && visible.length !== items.length ? ` · ${items.length.toLocaleString()} total` : ""}
        </span>
      </div>
      {matches.length === 0 && <p className="empty">No recoveries use this method in the current search.</p>}
      <VirtualTable
        items={matches}
        colCount={5}
        estimateSize={72}
        header={
          <tr>
            <th>Item</th>
            <th>Vendor</th>
            <th>Method</th>
            <th>Score</th>
            <th>Evidence</th>
          </tr>
        }
        renderRow={(row, _index, rowAttrs) => (
          <tr key={`${row.path}:${row.method}:${row.vendor}`} {...rowAttrs}>
            <td>
              <strong>{row.item_name}</strong>
              <PathLink path={row.path} />
              {row.section ? <div className="count-muted">section {row.section}</div> : null}
            </td>
            <td>
              <Badge tone="ready">{row.vendor || "—"}</Badge>
              {row.previous_vendor ? (
                <div className="count-muted">was {row.previous_vendor}</div>
              ) : null}
            </td>
            <td>
              <code>{row.method || "—"}</code>
            </td>
            <td>{row.score || "—"}</td>
            <td>
              <span className="count-muted" title={row.evidence}>
                {row.evidence || "—"}
              </span>
            </td>
          </tr>
        )}
      />
    </div>
  );
}
