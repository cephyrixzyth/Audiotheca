import { openInExplorer } from "../api/client";
import { useFileExplorer } from "../contexts/FileExplorerContext";

interface Props {
  path: string;
  className?: string;
  secondaryPath?: string;
  dualPane?: boolean;
}

export function PathLink({ path, className = "path", secondaryPath, dualPane }: Props) {
  const { openPath, openDualPane } = useFileExplorer();

  if (!path) return null;

  function handleBrowse() {
    if (dualPane && secondaryPath) {
      openDualPane(path, secondaryPath);
      return;
    }
    openPath(path, secondaryPath ? { secondary: secondaryPath, dualPane: true } : undefined);
  }

  return (
    <div className="path-row">
      <span className={className}>{path}</span>
      <button
        type="button"
        className="icon-btn"
        title="Browse this path in the built-in library explorer"
        aria-label={`Browse ${path} in the library explorer`}
        onClick={handleBrowse}
      >
        Browse
      </button>
      <button
        type="button"
        className="icon-btn"
        title="Reveal in the OS file manager"
        aria-label={`Reveal ${path} in the OS file manager`}
        onClick={() => void openInExplorer(path)}
      >
        Reveal
      </button>
    </div>
  );
}
