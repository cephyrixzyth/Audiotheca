import { useCallback, useEffect, useMemo, useState } from "react";
import {
  confirmAiLookup,
  fetchAiLookupCache,
  fetchAiLookupStatus,
  queryAiLookup,
} from "../api/client";
import type { AiLookupResult, AiLookupStatus, ProgressEvent } from "../types";
import { Button } from "../ui";
import { formatPct } from "../utils/format";

interface Props {
  libraryRoot?: string;
  events?: ProgressEvent[];
}

const AI_EVENT_TYPES = new Set([
  "ai_lookup_start",
  "ai_lookup_progress",
  "ai_lookup_done",
  "ai_lookup_pending",
]);

function confidenceTone(confidence: number): "accent" | "warning" | "danger" {
  if (confidence >= 0.75) return "accent";
  if (confidence >= 0.45) return "warning";
  return "danger";
}

export function AiAnalyzer({ libraryRoot, events = [] }: Props) {
  const [status, setStatus] = useState<AiLookupStatus | null>(null);
  const [cached, setCached] = useState<AiLookupResult[]>([]);
  const [queryPath, setQueryPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    void fetchAiLookupStatus().then(setStatus).catch(() => undefined);
    void fetchAiLookupCache(50).then((res) => setCached(res.items)).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (events.some((e) => AI_EVENT_TYPES.has(e.type))) {
      refresh();
    }
  }, [events, refresh]);

  const liveLines = useMemo(() => {
    const lines: {
      key: string;
      target?: string;
      state: "init" | "progress" | "done" | "pending";
      confidence?: number;
      vendor?: string;
      lookupId?: string;
    }[] = [];
    const byTarget = new Map<string, (typeof lines)[number]>();
    for (const event of events) {
      if (!AI_EVENT_TYPES.has(event.type)) continue;
      const target = (event as ProgressEvent & { relative_path?: string; target_id?: string }).relative_path
        ?? (event as ProgressEvent & { target_id?: string }).target_id
        ?? event.phase
        ?? "target";
      const key = String(target);
      if (event.type === "ai_lookup_start") {
        byTarget.set(key, { key, target: key, state: "init" });
      } else if (event.type === "ai_lookup_progress") {
        const prev = byTarget.get(key) ?? { key, target: key, state: "progress" as const };
        byTarget.set(key, { ...prev, state: "progress" });
      } else if (event.type === "ai_lookup_done" || event.type === "ai_lookup_pending") {
        byTarget.set(key, {
          key,
          target: key,
          state: event.type === "ai_lookup_pending" ? "pending" : "done",
          confidence: (event as ProgressEvent & { confidence?: number }).confidence,
          vendor: (event as ProgressEvent & { vendor?: string }).vendor,
          lookupId: (event as ProgressEvent & { lookup_id?: string }).lookup_id,
        });
      }
    }
    for (const line of byTarget.values()) lines.push(line);
    return lines.slice(-12);
  }, [events]);

  const merged = useMemo(() => {
    const active = status?.active ?? [];
    const seen = new Set(active.map((a) => a.lookup_id));
    const rest = cached.filter((c) => !seen.has(c.lookup_id));
    return [...active, ...rest].slice(0, 20);
  }, [status, cached]);

  const tokenUsed = status?.token_usage?.used ?? 0;
  const tokenLimit = status?.token_usage?.limit ?? 50_000;
  const tokenPct = tokenLimit ? Math.min(100, (100 * tokenUsed) / tokenLimit) : 0;

  const handleQuery = () => {
    const path = queryPath.trim();
    if (!path) return;
    setBusy(true);
    setError(null);
    void queryAiLookup({ path, root: libraryRoot })
      .then(() => {
        setQueryPath("");
        refresh();
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setBusy(false));
  };

  const handleConfirm = (lookupId: string, accepted: boolean) => {
    void confirmAiLookup({ lookup_id: lookupId, accepted })
      .then(refresh)
      .catch((err: Error) => setError(err.message));
  };

  return (
    <div className="ai-analyzer">
      <div className="ai-analyzer-header">
        <div className="ai-token-meter">
          <div className="ai-token-top">
            <span className="gauge-label">Token usage</span>
            <span className="gauge-value">
              {tokenUsed.toLocaleString()} / {tokenLimit.toLocaleString()}
            </span>
          </div>
          <div className="gauge-track">
            <div className="gauge-fill tone-accent" style={{ width: `${tokenPct}%` }} />
          </div>
        </div>
        <div className="toolbar ai-query-row">
          <input
            type="text"
            className="field-input"
            placeholder="Manual lookup path (relative or library path)"
            aria-label="Manual lookup path"
            value={queryPath}
            onChange={(e) => setQueryPath(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleQuery()}
          />
          <Button variant="primary" disabled={busy || !queryPath.trim()} onClick={handleQuery}>
            {busy ? "Querying…" : "Query"}
          </Button>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      {liveLines.length > 0 && (
        <div className="ai-live-block">
          <h4 className="ai-section-title">Active lookups</h4>
          <ul className="ai-lookup-list">
            {liveLines.map((line) => (
              <li key={line.key} className={`ai-lookup-line state-${line.state}`}>
                {line.state === "init" || line.state === "progress" ? (
                  <span className="phase-init-spinner phase-init-spinner-inline" aria-hidden />
                ) : null}
                <span className="ai-target">{line.target}</span>
                {line.confidence != null && (
                  <span className={`ai-confidence tone-${confidenceTone(line.confidence)}`}>
                    {formatPct(line.confidence * 100, 0)}
                  </span>
                )}
                {line.vendor && <span className="count-muted"> · {line.vendor}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="ai-results-block">
        <h4 className="ai-section-title">Discoveries</h4>
        {merged.length === 0 ? (
          <p className="count-muted">No AI lookup results yet — unknown targets queue during scan Phase 1b fallback.</p>
        ) : (
          <ul className="ai-result-cards">
            {merged.map((row) => (
              <li key={row.lookup_id} className="ai-result-card hover-card">
                <div className="ai-result-top">
                  <strong>{row.product ?? row.relative_path ?? row.lookup_id}</strong>
                  <span className={`ai-confidence tone-${confidenceTone(row.confidence)}`}>
                    {formatPct(row.confidence * 100, 0)}
                  </span>
                </div>
                <div className="count-muted ai-result-meta">
                  {row.vendor && <span>{row.vendor}</span>}
                  {row.relative_path && <span> · {row.relative_path}</span>}
                  {row.status && <span> · {row.status}</span>}
                </div>
                {row.reasoning && <p className="ai-reasoning">{row.reasoning}</p>}
                <div className="ai-hover-detail">
                  {row.source_url && (
                    <a href={row.source_url} target="_blank" rel="noreferrer">
                      Source
                    </a>
                  )}
                  {row.developer?.vendor && (
                    <span className="count-muted">Developer: {row.developer.vendor}</span>
                  )}
                  {row.pending_verification && (
                    <div className="toolbar ai-confirm-row">
                      <Button variant="ghost" size="sm" onClick={() => handleConfirm(row.lookup_id, true)}>
                        Accept metadata
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => handleConfirm(row.lookup_id, false)}>
                        Reject
                      </Button>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
