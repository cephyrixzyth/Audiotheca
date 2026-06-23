import { openInExplorer } from "../api/client";

interface Props {
  path: string;
  className?: string;
}

export function PathLink({ path, className = "path" }: Props) {
  if (!path) return null;
  return (
    <div className="path-row">
      <span className={className}>{path}</span>
      <button
        type="button"
        className="icon-btn"
        title="Open in Explorer"
        onClick={() => void openInExplorer(path)}
      >
        Open
      </button>
    </div>
  );
}
