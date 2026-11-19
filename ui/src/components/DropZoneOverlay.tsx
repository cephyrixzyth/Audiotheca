import { useCallback, useEffect, useRef, useState } from "react";
import { postExplorerDrop, type DropResult } from "../api/client";
import { isTauri } from "../platform";
import { LoadingStatus } from "../ui/LoadingStatus";
import { Button } from "../ui";

interface Props {
  onOpen: (row: DropResult) => void;
  receiveDesktopDrops: boolean;
}

function textPaths(text: string) {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

export function DropZoneOverlay({ onOpen, receiveDesktopDrops }: Props) {
  const [active, setActive] = useState(false);
  const [input, setInput] = useState("");
  const [message, setMessage] = useState("");
  const [rows, setRows] = useState<DropResult[]>([]);
  const [busy, setBusy] = useState(false);
  const request = useRef(0);
  const openRef = useRef(onOpen);
  useEffect(() => {
    openRef.current = onOpen;
  }, [onOpen]);
  useEffect(
    () => () => {
      request.current += 1;
    },
    [],
  );

  const inspect = useCallback(async (paths: string[]) => {
    if (!paths.length) return;
    const id = ++request.current;
    setBusy(true);
    setMessage("");
    setRows([]);
    try {
      const result = await postExplorerDrop([...new Set(paths)]);
      if (id !== request.current) return;
      setRows(result.routed);
      if (result.routed.length === 1 && result.routed[0].action !== "error") {
        openRef.current(result.routed[0]);
      }
    } catch (error) {
      if (id === request.current)
        setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      if (id === request.current) setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (!receiveDesktopDrops || !isTauri()) return;
    let disposed = false;
    let remove: (() => void) | undefined;
    void import("@tauri-apps/api/webview")
      .then(async ({ getCurrentWebview }) => {
        if (disposed) return;
        const unlisten = await getCurrentWebview().onDragDropEvent(
          ({ payload }) => {
            if (disposed) return;
            setActive(payload.type === "enter" || payload.type === "over");
            if (payload.type === "drop") void inspect(payload.paths);
          },
        );
        if (disposed) unlisten();
        else remove = unlisten;
      })
      .catch(() => {
        if (!disposed)
          setMessage(
            "Desktop drops are unavailable. Paste a library path to continue.",
          );
      });
    return () => {
      disposed = true;
      remove?.();
    };
  }, [inspect, receiveDesktopDrops]);

  return (
    <div
      className={`drop-zone-overlay ${active ? "active" : ""}`}
      aria-label="Inspect library paths"
      onDragOver={(event) => {
        event.preventDefault();
        setActive(true);
      }}
      onDragLeave={() => setActive(false)}
      onDrop={(event) => {
        event.preventDefault();
        setActive(false);
        const paths = textPaths(event.dataTransfer.getData("text/plain"));
        if (paths.length) void inspect(paths);
        else if (!isTauri()) {
          setMessage(
            "Browser file drops do not include a server path. Choose the file in this explorer or paste its library path below.",
          );
        }
      }}
    >
      <div className="library-drop-target" aria-hidden="true">
        <span>↓</span>
        <strong>{active ? "Release to inspect" : "Drop a library path"}</strong>
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void inspect(textPaths(input));
        }}
      >
        <input
          aria-label="Library path to inspect"
          placeholder={
            isTauri()
              ? "Drop a file or paste a library path"
              : "Paste a server library path"
          }
          value={input}
          onChange={(event) => setInput(event.target.value)}
        />
        <Button
          type="submit"
          variant="secondary"
          size="sm"
          disabled={busy || !input.trim()}
        >
          Inspect path
        </Button>
      </form>
      {busy && <LoadingStatus>Inspecting library paths…</LoadingStatus>}
      {message && <p role="status">{message}</p>}
      {rows.length > 0 && (
        <ul aria-label="Drop results">
          {rows.map((row) => (
            <li key={row.path}>
              {row.action === "error" ? (
                <span>
                  {row.path} · {row.error}
                </span>
              ) : (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => onOpen(row)}
                  title={row.path}
                >
                  {row.action === "browse"
                    ? "Browse"
                    : row.action === "audition"
                      ? "Audition"
                      : "Open"}{" "}
                  {row.path.split(/[/\\]/).pop()}
                </Button>
              )}
              {row.result && (
                <details>
                  <summary>Inspection details</summary>
                  <pre>{JSON.stringify(row.result, null, 2)}</pre>
                </details>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
