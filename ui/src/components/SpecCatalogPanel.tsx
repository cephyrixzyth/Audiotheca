import { useEffect, useMemo, useState } from "react";
import { fetchMountEvents, fetchSpecCatalog } from "../api/client";
import { Badge } from "../ui";
import type { BadgeTone } from "../ui";

type SpecEntry = {
  code: string;
  section: string;
  title: string;
  description: string;
  status: "done" | "partial" | "mvp";
  module: string;
};

const STATUS_TONE: Record<SpecEntry["status"], BadgeTone> = {
  done: "ready",
  partial: "review",
  mvp: "medium",
};

export function SpecCatalogPanel() {
  const [entries, setEntries] = useState<SpecEntry[]>([]);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  useEffect(() => {
    void fetchSpecCatalog()
      .then((payload) => {
        setEntries((payload.entries ?? []) as SpecEntry[]);
        setSummary(payload.summary ?? null);
      })
      .catch(() => undefined);
  }, []);

  const sections = useMemo(() => {
    const set = new Set(entries.map((e) => e.section));
    return ["all", ...Array.from(set).sort()];
  }, [entries]);

  const visible = entries.filter((entry) => {
    if (filter !== "all" && entry.section !== filter) return false;
    if (statusFilter !== "all" && entry.status !== statusFilter) return false;
    return true;
  });

  const byStatus = summary?.by_status as Record<string, number> | undefined;

  return (
    <div className="spec-catalog-panel">
      {byStatus && (
        <p className="count-muted">
          {summary?.total as number} codes · done {byStatus.done ?? 0} · partial {byStatus.partial ?? 0} · mvp{" "}
          {byStatus.mvp ?? 0}
        </p>
      )}
      <div className="log-toolbar">
        <div className="log-level-filters" role="group" aria-label="Spec section">
          {sections.map((section) => (
            <button
              key={section}
              type="button"
              className={`log-level-btn ${filter === section ? "active" : ""}`}
              aria-pressed={filter === section}
              onClick={() => setFilter(section)}
            >
              {section === "all" ? "All sections" : section}
            </button>
          ))}
        </div>
        <div className="log-level-filters" role="group" aria-label="Spec status">
          {(["all", "done", "partial", "mvp"] as const).map((status) => (
            <button
              key={status}
              type="button"
              className={`log-level-btn ${statusFilter === status ? "active" : ""}`}
              aria-pressed={statusFilter === status}
              onClick={() => setStatusFilter(status)}
            >
              {status}
            </button>
          ))}
        </div>
      </div>
      <div className="spec-catalog-grid">
        {visible.map((entry) => (
          <article key={entry.code} className="spec-catalog-card">
            <header>
              <code>{entry.code}</code>
              <Badge tone={STATUS_TONE[entry.status]}>{entry.status}</Badge>
            </header>
            <strong>{entry.title}</strong>
            <p className="count-muted">{entry.description}</p>
            <footer className="count-muted">{entry.module}</footer>
          </article>
        ))}
      </div>
    </div>
  );
}

export function MountEventsPanel() {
  const [events, setEvents] = useState<Array<Record<string, unknown>>>([]);
  const [meta, setMeta] = useState<{ enabled?: boolean; active?: boolean; watchdog_available?: boolean; roots?: string[] }>({});

  useEffect(() => {
    const load = () => {
      void fetchMountEvents(80)
        .then((payload) => {
          setEvents(payload.events ?? []);
          setMeta({
            enabled: payload.enabled,
            active: payload.active,
            watchdog_available: payload.watchdog_available,
            roots: payload.roots,
          });
        })
        .catch(() => undefined);
    };
    load();
    const timer = window.setInterval(load, 15_000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="mount-events-panel">
      <p className="count-muted">
        Watcher{" "}
        <span className={`env-badge ${meta.active ? "env-ok" : meta.enabled ? "env-degraded" : "env-missing"}`}>
          {meta.active ? "active" : meta.enabled ? "enabled (idle)" : "disabled"}
        </span>
        · watchdog {meta.watchdog_available ? "available" : "missing"}
        {meta.roots?.length ? ` · ${meta.roots.length} root(s)` : null}
      </p>
      <div className="log-lines log-lines-fixed">
        {events.length === 0 ? (
          <div className="log-line log-detail">No mount or library change events recorded yet.</div>
        ) : (
          events
            .slice()
            .reverse()
            .map((row, index) => (
              <div key={`${String(row.ts)}-${index}`} className="log-line log-info">
                [{String(row.type ?? "event")}] {String(row.path ?? "")}
              </div>
            ))
        )}
      </div>
    </div>
  );
}
