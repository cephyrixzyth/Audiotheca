import { useCallback, useState } from "react";
import { postExplorerDrop } from "../api/client";

type Props = {
  onRouted?: (paths: string[]) => void;
};

type FileWithPath = File & { path?: string };

/** DRP-ZONE: accept dropped paths/files and POST to explorer drop handler. */
export function DropZoneOverlay({ onRouted }: Props) {
  const [active, setActive] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDrop = useCallback(
    async (event: React.DragEvent) => {
      event.preventDefault();
      setActive(false);
      setError(null);
      setMsg(null);
      const paths: string[] = [];
      const items = event.dataTransfer.items;
      if (items?.length) {
        for (let i = 0; i < items.length; i += 1) {
          const item = items[i];
          if (item.kind === "file") {
            const file = item.getAsFile() as FileWithPath | null;
            if (file?.path) paths.push(file.path);
          }
        }
      }
      if (!paths.length && event.dataTransfer.getData("text/plain")) {
        paths.push(...event.dataTransfer.getData("text/plain").split(/\r?\n/).filter(Boolean));
      }
      if (!paths.length) {
        setError("No file paths in drop payload");
        return;
      }
      try {
        const res = await postExplorerDrop(paths);
        setMsg(`Routed ${res.count} path(s)`);
        onRouted?.(paths);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Drop failed");
      }
    },
    [onRouted],
  );

  return (
    <div
      className={`drop-zone-overlay ${active ? "active" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setActive(true);
      }}
      onDragLeave={() => setActive(false)}
      onDrop={(e) => void handleDrop(e)}
    >
      <span className="drop-zone-label">Drop files or paths to inspect (DRP-ZONE)</span>
      {msg && <span className="count-muted">{msg}</span>}
      {error && <span className="error-text">{error}</span>}
    </div>
  );
}
