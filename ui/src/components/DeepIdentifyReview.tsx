import { useEffect, useMemo, useState } from "react";
import { fetchDeepIdentify } from "../api/client";
import type { DeepIdentifyItem } from "../types";
import { Badge, VirtualTable } from "../ui";
import { useContextSidebar } from "./ContextSidebar";
import { PathLink } from "./PathLink";

interface Props {
  stamp: string;
}

export function DeepIdentifyReview({ stamp }: Props) {
  const { query } = useContextSidebar();
  const [items, setItems] = useState<DeepIdentifyItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchDeepIdentify(stamp, { limit: 2000, q: query.trim() || undefined })
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setItems([]);
        setTotal(0);
        setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [stamp, query]);

  const methodCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const row of items) {
      const key = row.method || "UNKNOWN";
      counts[key] = (counts[key] ?? 0) + 1;
    }
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [items]);

  if (loading) return <div className="count-muted">Loading deep identify results…</div>;
  if (error) return <div className="error">{error}</div>;
  if (total === 0) {
    return (
      <div className="empty">
        No deep-identify recoveries for this run. Enable the deep identify phase on the next scan.
      </div>
    );
  }

  return (
    <div>
      <div className="banner dry">
        Fuzzy / sibling vendor recoveries from Phase 1.7 — review before relying on them in a live
        restructure.
      </div>
      <div className="toolbar compact-toolbar">
        <span className="count-muted">
          {total.toLocaleString()} recover{total === 1 ? "y" : "ies"}
          {query.trim() ? ` matching “${query.trim()}”` : ""}
        </span>
        {methodCounts.slice(0, 6).map(([method, count]) => (
          <Badge key={method} tone="accent" title={`${count} via ${method}`}>
            {method} · {count}
          </Badge>
        ))}
      </div>
      <VirtualTable
        items={items}
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
