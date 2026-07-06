import { useCallback, useEffect, useState } from "react";
import { fetchVirtualPaths, saveVirtualPaths } from "../api/client";

type VirtualEntry = { virtual: string; physical: string; exists?: boolean };

/** SYM-AGG virtual path management UI. */
export function VirtualPathsPanel() {
  const [entries, setEntries] = useState<VirtualEntry[]>([]);
  const [virtual, setVirtual] = useState("/libraries/sfx");
  const [physical, setPhysical] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const reload = useCallback(() => {
    void fetchVirtualPaths()
      .then((data) => setEntries((data.entries ?? []) as VirtualEntry[]))
      .catch(() => setEntries([]));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function handleSave() {
    if (!physical.trim()) return;
    const mappings = Object.fromEntries(entries.map((e) => [e.virtual, e.physical]));
    mappings[virtual.trim()] = physical.trim();
    await saveVirtualPaths(mappings);
    setMsg("Virtual path mapping saved");
    reload();
  }

  return (
    <div className="virtual-paths-panel">
      <p className="count-muted">Map virtual browse prefixes to physical library roots without moving files.</p>
      <div className="preview-session-grid">
        <label>
          Virtual prefix
          <input value={virtual} onChange={(e) => setVirtual(e.target.value)} />
        </label>
        <label>
          Physical root
          <input value={physical} onChange={(e) => setPhysical(e.target.value)} placeholder="D:\Libraries\SFX" />
        </label>
      </div>
      <button type="button" className="text-btn" onClick={() => void handleSave()}>
        Save mapping
      </button>
      {msg && <p className="count-muted">{msg}</p>}
      <ul className="virtual-path-list">
        {entries.map((entry) => (
          <li key={entry.virtual}>
            <code>{entry.virtual}</code> → <code>{entry.physical}</code>
            {!entry.exists && <span className="badge review">missing</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
