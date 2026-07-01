import { useFileExplorer } from "../contexts/FileExplorerContext";

interface Props {
  path: string;
  className?: string;
}

export function PathLink({ path, className = "path" }: Props) {
  const { openPath } = useFileExplorer();

  if (!path) return null;
  return (
    <div className="path-row">
      <span className={className}>{path}</span>
      <button
        type="button"
        className="icon-btn"
        title="Browse this path in the built-in library explorer (no external window)"
        onClick={() => openPath(path)}
      >
        Browse
      </button>
    </div>
  );
}
