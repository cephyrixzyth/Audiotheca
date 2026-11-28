import { useCallback, useEffect, useState } from "react";
import {
  errorText,
  fetchSimilarityStatus,
  findSimilar,
  indexSimilarity,
  saveSimilarityRoots,
  searchSimilarityIndex,
  type SimilarSample,
  type SimilarityStatus,
} from "../api/features";
import { Button } from "../ui";
import { PathLink } from "./PathLink";
import { WorkIssue, WorkScope } from "./ReviewWorkbench";

function seconds(value: number | null | undefined): string {
  if (value == null) return "—";
  return value >= 10 ? `${value.toFixed(0)} s` : `${value.toFixed(2)} s`;
}

function SimilarTable({ rows }: { rows: SimilarSample[] }) {
  if (rows.length === 0) return <p className="empty">No close matches in the index.</p>;
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Match</th>
          <th>Sound</th>
          <th>Length</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.path}>
            <td>{Math.round(Math.max(0, r.score) * 100)}%</td>
            <td>
              {r.name}
              <PathLink path={r.path} className="path count-muted" />
            </td>
            <td>{seconds(r.duration_s)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Index management and "more like this" search across the sample library. */
export function SampleFinderView() {
  const [status, setStatus] = useState<SimilarityStatus | null>(null);
  const [roots, setRoots] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Array<{ path: string; name: string; duration_s: number | null }>>([]);
  const [picked, setPicked] = useState<string | null>(null);
  const [results, setResults] = useState<SimilarSample[] | null>(null);
  const [otherFolders, setOtherFolders] = useState(true);

  const reload = useCallback(() => {
    fetchSimilarityStatus()
      .then((s) => {
        setStatus(s);
        setRoots((current) => current || s.roots.join("\n"));
      })
      .catch((err) => setError(errorText(err)));
  }, []);
  useEffect(() => reload(), [reload]);

  async function index() {
    setBusy(true);
    setError(null);
    try {
      await saveSimilarityRoots(roots.split("\n").map((r) => r.trim()).filter(Boolean));
      setStatus(await indexSimilarity());
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function search() {
    setError(null);
    try {
      setMatches((await searchSimilarityIndex(query)).results);
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function similar(path: string) {
    setPicked(path);
    setResults(null);
    setError(null);
    try {
      setResults((await findSimilar(path, { excludeSameFolder: otherFolders, limit: 30 })).results);
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <section>
      <WorkScope
        title="Sample finder"
        detail="Find sounds that sound alike, across packs and vendors. Audiotheca measures each sample's tone, brightness, noisiness and shape on this computer; nothing is uploaded. Index your sample folders once, then pick a sound to see its closest matches. Select an audio file in the Library to do the same from there."
      />
      {error && <WorkIssue message={error} />}
      <label className="field-stack">
        <span className="context-label">Sample folders (one per line, inside a library root)</span>
        <textarea className="field-input" rows={3} value={roots} onChange={(e) => setRoots(e.target.value)} />
      </label>
      <div className="toolbar">
        <Button variant="primary" disabled={busy || !roots.trim()} onClick={() => void index()}>
          {busy ? "Indexing…" : status?.remaining ? "Index the next batch" : "Save and index"}
        </Button>
        {status && (
          <span className="count-muted">
            {status.count.toLocaleString()} sounds indexed
            {status.skipped > 0 && ` · ${status.skipped.toLocaleString()} skipped`}
            {status.remaining ? ` · ${status.remaining.toLocaleString()} still to analyse` : ""}
            {" · "}
            {status.method}
            {status.indexed_at && ` · ${new Date(status.indexed_at).toLocaleString()}`}
          </span>
        )}
      </div>
      {status && status.skipped > 0 && (
        <details className="work-disclosure">
          <summary>Why some files were skipped</summary>
          <ul>
            {Object.entries(status.skip_reasons).map(([reason, n]) => (
              <li key={reason}>
                {reason}: {n}
              </li>
            ))}
          </ul>
          <p className="count-muted">FLAC, MP3, OGG and M4A need the optional soundfile package.</p>
        </details>
      )}
      <form
        className="toolbar"
        onSubmit={(e) => {
          e.preventDefault();
          void search();
        }}
      >
        <input
          className="field-input"
          placeholder="Find a sound in the index by name, e.g. kick 808"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <Button type="submit" disabled={!query.trim() || !status?.count}>
          Search
        </Button>
        <label>
          <input type="checkbox" checked={otherFolders} onChange={(e) => setOtherFolders(e.target.checked)} /> Only
          other folders
        </label>
      </form>
      {matches.length > 0 && (
        <ul className="count-muted" style={{ maxHeight: "12rem", overflowY: "auto" }}>
          {matches.map((m) => (
            <li key={m.path}>
              <button type="button" className="quick-link" onClick={() => void similar(m.path)}>
                {m.name}
              </button>{" "}
              <span>{m.path}</span>
            </li>
          ))}
        </ul>
      )}
      {picked && (
        <>
          <h3>Sounds like {picked.split(/[\\/]/).pop()}</h3>
          {results ? <SimilarTable rows={results} /> : <p className="count-muted">Comparing…</p>}
        </>
      )}
    </section>
  );
}

/** Compact "Find similar sounds" block for the Library inspector. */
export function SimilarSounds({ path }: { path: string }) {
  const [rows, setRows] = useState<SimilarSample[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRows(null);
    setError(null);
  }, [path]);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setRows((await findSimilar(path, { limit: 8 })).results);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="library-similar">
      <Button size="sm" disabled={busy} onClick={() => void run()}>
        {busy ? "Comparing…" : "Find similar sounds"}
      </Button>
      {error && <p className="error">{error}</p>}
      {rows && rows.length === 0 && (
        <p className="count-muted">
          No close matches. If you have not indexed your samples yet, do it in System → Automation → Sample finder.
        </p>
      )}
      {rows && rows.length > 0 && (
        <ul className="count-muted">
          {rows.map((r) => (
            <li key={r.path}>
              {Math.round(Math.max(0, r.score) * 100)}% · <PathLink path={r.path} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
