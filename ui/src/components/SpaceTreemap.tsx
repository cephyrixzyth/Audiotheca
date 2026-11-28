import { useEffect, useMemo, useState } from "react";
import { errorText, fetchCloneSupport, fetchSpaceMap, type SpaceNode } from "../api/features";
import { squarify } from "../utils/treemap";
import { WorkIssue, WorkScope } from "./ReviewWorkbench";

const W = 960;
const H = 520;
const HEADER = 18;

function fmt(mb: number): string {
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb.toFixed(0)} MB`;
}

/** Library size by bin (or status) and vendor. Red share shows copies the duplicate review would stage. */
export function SpaceTreemap({ stamp }: { stamp: string }) {
  const [groupBy, setGroupBy] = useState<"bin" | "status">("bin");
  const [data, setData] = useState<Awaited<ReturnType<typeof fetchSpaceMap>> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState<string | null>(null);
  const [hover, setHover] = useState<string>("");

  useEffect(() => {
    setError(null);
    fetchSpaceMap(stamp, groupBy)
      .then(setData)
      .catch((err) => setError(errorText(err)));
  }, [stamp, groupBy]);

  const groups = useMemo(() => {
    if (!data) return [];
    const top = focus ? data.children.filter((c) => c.name === focus) : data.children;
    return squarify(top, (n) => n.size_mb, { x: 0, y: 0, w: W, h: H }).map((g) => ({
      ...g,
      cells: squarify(g.item.children ?? [], (n: SpaceNode) => n.size_mb, {
        x: g.x + 2,
        y: g.y + HEADER,
        w: Math.max(0, g.w - 4),
        h: Math.max(0, g.h - HEADER - 2),
      }),
    }));
  }, [data, focus]);

  return (
    <section>
      <WorkScope
        title="Where the space goes"
        detail="Each box is a vendor, grouped by bin. Box size is the space it uses; the red part is duplicate copies the duplicate review would stage. Click a bin to zoom in."
      />
      {error && <WorkIssue message={error} />}
      <div className="toolbar">
        <label>
          Group by{" "}
          <select value={groupBy} onChange={(e) => { setFocus(null); setGroupBy(e.target.value as "bin" | "status"); }}>
            <option value="bin">Bin</option>
            <option value="status">Scan status</option>
          </select>
        </label>
        {focus && (
          <button type="button" className="quick-link" onClick={() => setFocus(null)}>
            ← All {groupBy === "bin" ? "bins" : "statuses"}
          </button>
        )}
        {data && (
          <span className="count-muted">
            {fmt(data.total_mb)} scanned · {fmt(data.duplicate_mb)} in duplicate copies
          </span>
        )}
      </div>
      <p className="count-muted" aria-live="polite" style={{ minHeight: "1.4em" }}>{hover}</p>
      {data && data.total_mb === 0 && <p className="empty">This run has no item sizes to map.</p>}
      {groups.length > 0 && (
        <svg
          viewBox={`0 0 ${W} ${H}`}
          role="img"
          aria-label="Treemap of library size by vendor"
          style={{ width: "100%", height: "auto", background: "var(--bg-panel)", borderRadius: 6 }}
        >
          {groups.map((g) => (
            <g key={g.item.name}>
              <rect
                x={g.x}
                y={g.y}
                width={g.w}
                height={g.h}
                fill="var(--bg-elevated)"
                stroke="var(--border-bright)"
                style={{ cursor: focus ? "default" : "zoom-in" }}
                onClick={() => setFocus(g.item.name)}
              />
              {g.w > 50 && (
                <text x={g.x + 4} y={g.y + 13} fontSize={11} fill="var(--text)" style={{ pointerEvents: "none" }}>
                  {g.item.name} · {fmt(g.item.size_mb)}
                </text>
              )}
              {g.cells.map((c) => {
                const dupShare = c.item.size_mb > 0 ? Math.min(1, c.item.duplicate_mb / c.item.size_mb) : 0;
                const label = `${g.item.name} / ${c.item.name}: ${fmt(c.item.size_mb)}, ${c.item.items} items` +
                  (c.item.duplicate_mb > 0 ? `, ${fmt(c.item.duplicate_mb)} duplicate` : "");
                return (
                  <g
                    key={c.item.name}
                    onMouseEnter={() => setHover(label)}
                    onFocus={() => setHover(label)}
                    onClick={() => setFocus(g.item.name)}
                    tabIndex={0}
                  >
                    <title>{label}</title>
                    <rect x={c.x} y={c.y} width={c.w} height={c.h} fill="var(--accent-soft)" stroke="var(--bg-panel)" />
                    {dupShare > 0 && (
                      <rect
                        x={c.x}
                        y={c.y + c.h * (1 - dupShare)}
                        width={c.w}
                        height={c.h * dupShare}
                        fill="var(--danger)"
                        opacity={0.55}
                        style={{ pointerEvents: "none" }}
                      />
                    )}
                    {c.w > 60 && c.h > 16 && (
                      <text x={c.x + 3} y={c.y + 12} fontSize={10} fill="var(--text)" style={{ pointerEvents: "none" }}>
                        {c.item.name.length > c.w / 6 ? `${c.item.name.slice(0, Math.max(3, Math.floor(c.w / 6) - 1))}…` : c.item.name}
                      </text>
                    )}
                  </g>
                );
              })}
            </g>
          ))}
        </svg>
      )}
    </section>
  );
}

/** Which library roots can make copy-on-write clones. */
export function CloneSupportBadges() {
  const [roots, setRoots] = useState<Array<{ path: string; supported: boolean; reason: string }> | null>(null);
  useEffect(() => {
    fetchCloneSupport()
      .then((r) => setRoots(r.roots))
      .catch(() => setRoots(null));
  }, []);
  if (!roots || roots.length === 0) return null;
  return (
    <ul className="count-muted" style={{ marginTop: "0.5rem" }}>
      {roots.map((r) => (
        <li key={r.path}>
          <code>{r.path}</code>:{" "}
          {r.supported ? (
            <span className="env-ok">copy-on-write clones available</span>
          ) : (
            <span className="env-degraded" title={r.reason}>no clone support ({r.reason})</span>
          )}
        </li>
      ))}
    </ul>
  );
}
