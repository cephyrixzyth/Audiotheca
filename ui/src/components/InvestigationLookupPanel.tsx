import { useState } from "react";
import {
  fetchAnonymizeStatus,
  generateTagsFromText,
  parseNfoFile,
  planWebSpiderLookup,
  runWebSpiderLookup,
} from "../api/client";

type Props = {
  defaultPath?: string;
};

/** WEB-SPDR + TAG-GEN + NFO-PARSE + STRIP-DATA hook for Investigation tab. */
export function InvestigationLookupPanel({ defaultPath = "" }: Props) {
  const [query, setQuery] = useState("");
  const [path, setPath] = useState(defaultPath);
  const [nfoText, setNfoText] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [plan, setPlan] = useState<Record<string, unknown> | null>(null);
  const [results, setResults] = useState<Record<string, unknown> | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [nfoParsed, setNfoParsed] = useState<Record<string, unknown> | null>(null);
  const [stripStatus, setStripStatus] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handlePlan() {
    if (!query.trim()) return;
    setBusy("plan");
    setError(null);
    try {
      setPlan(await planWebSpiderLookup(query.trim()));
      setStripStatus(
        await fetchAnonymizeStatus({
          path: path || query,
          original_name: query,
          id_confidence: "TENTATIVE",
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Plan failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleRun() {
    if (!query.trim()) return;
    setBusy("run");
    setError(null);
    try {
      const status = await fetchAnonymizeStatus({
        path: path || query,
        original_name: query,
        id_confidence: "TENTATIVE",
      });
      setStripStatus(status);
      if (!status.ready_for_external) {
        setError("STRIP-DATA: item not ready for external lookup");
        return;
      }
      setResults(await runWebSpiderLookup(query.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lookup failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleTags() {
    setBusy("tags");
    setError(null);
    try {
      const res = await generateTagsFromText({ text: nfoText, path: path || undefined });
      setTags((res.tags as string[]) ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Tag generation failed");
    } finally {
      setBusy(null);
    }
  }

  async function handleNfo() {
    setBusy("nfo");
    setError(null);
    try {
      const res = path
        ? await parseNfoFile(path)
        : await parseNfoFile(undefined, nfoText);
      setNfoParsed(res.parsed as Record<string, unknown>);
    } catch (err) {
      setError(err instanceof Error ? err.message : "NFO parse failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="investigation-lookup-panel">
      <h4 className="ai-section-title">Investigation lookup (WEB-SPDR / TAG-GEN / NFO-PARSE)</h4>
      {stripStatus && (
        <p className="count-muted strip-data-status">
          STRIP-DATA: {stripStatus.ready_for_external ? "anonymized" : "blocked"} · id{" "}
          {String(stripStatus.target_id ?? "—")} · redacted{" "}
          {((stripStatus.fields_redacted as string[]) ?? []).join(", ") || "paths"}
        </p>
      )}
      <div className="log-toolbar">
        <input
          className="log-search-input"
          placeholder="Vendor or product query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button type="button" className="text-btn" disabled={!!busy} onClick={() => void handlePlan()}>
          Plan
        </button>
        <button type="button" className="primary-btn" disabled={!!busy} onClick={() => void handleRun()}>
          Run lookup
        </button>
      </div>
      {plan && (
        <p className="count-muted">
          Preset {String(plan.preset)} · outbound {plan.outbound_allowed ? "allowed" : "blocked"}
        </p>
      )}
      {results && (
        <ul className="ai-lookup-list">
          {((results.results as Array<Record<string, unknown>>) ?? []).slice(0, 6).map((row, i) => (
            <li key={i} className="ai-lookup-line">
              <strong>{String(row.title ?? row.url ?? "result")}</strong>
              {row.url ? ` — ${String(row.url)}` : null}
            </li>
          ))}
        </ul>
      )}
      <div className="log-toolbar" style={{ marginTop: "0.75rem" }}>
        <input
          className="log-search-input"
          placeholder="NFO path or paste release text"
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        <button type="button" className="text-btn" disabled={!!busy} onClick={() => void handleNfo()}>
          Parse NFO
        </button>
        <button type="button" className="text-btn" disabled={!!busy} onClick={() => void handleTags()}>
          Generate tags
        </button>
      </div>
      <textarea
        className="env-manifest-editor"
        rows={3}
        placeholder="Optional release text for tag generation"
        value={nfoText}
        onChange={(e) => setNfoText(e.target.value)}
      />
      {nfoParsed && (
        <p className="count-muted">
          NFO: group {String(nfoParsed.release_group ?? "—")} · product {String(nfoParsed.product_hint ?? "—")}
        </p>
      )}
      {tags.length > 0 && <p className="count-muted">Tags: {tags.join(", ")}</p>}
      {error && <p className="error-text">{error}</p>}
    </div>
  );
}
