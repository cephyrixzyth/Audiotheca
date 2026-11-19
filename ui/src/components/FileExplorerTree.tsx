import { useCallback, useEffect, useRef, useState } from "react";
import { explorerBreadcrumbs } from "../utils/explorerBreadcrumbs";
import { browseTreeChildren, type BrowseEntry } from "../api/client";

interface TreeNodeProps {
  entry: BrowseEntry;
  depth: number;
  selectedPath: string;
  expandedPaths: Set<string>;
  onToggle: (path: string) => void;
  onSelect: (path: string) => void;
}

function TreeNode({ entry, depth, selectedPath, expandedPaths, onToggle, onSelect }: TreeNodeProps) {
  const [children, setChildren] = useState<BrowseEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState("");
  const expanded = expandedPaths.has(entry.path);
  const loadSeq = useRef(0);

  const load = useCallback((next = "") => {
    const seq = ++loadSeq.current;
    setLoading(true);
    setError("");
    void browseTreeChildren(entry.path, next)
      .then((data) => {
        if (seq !== loadSeq.current) return;
        setChildren((prior) => next ? [...(prior ?? []), ...data.children] : data.children);
        setCursor(data.next_cursor);
      })
      .catch((reason) => {
        if (seq === loadSeq.current) setError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => { if (seq === loadSeq.current) setLoading(false); });
  }, [entry.path]);

  useEffect(() => {
    if (expanded) load();
    else { setChildren(null); setCursor(null); setError(""); }
    return () => { loadSeq.current += 1; };
  }, [expanded, load]);

  const selected = selectedPath === entry.path;

  return (
    <li
      className="explorer-tree-node"
      role="treeitem"
      aria-label={entry.name}
      aria-level={depth + 1}
      aria-selected={selected}
      aria-expanded={entry.is_dir ? expanded : undefined}
    >
      <div
        className={`explorer-tree-row ${selected ? "selected" : ""}`}
        style={{ paddingLeft: `${depth * 0.75 + 0.25}rem` }}
      >
        {entry.is_dir ? (
          <button
            type="button"
            className="explorer-tree-toggle"
            title={expanded ? `Collapse ${entry.name}` : `Expand ${entry.name}`}
            aria-label={expanded ? `Collapse ${entry.name}` : `Expand ${entry.name}`}
            onClick={() => onToggle(entry.path)}
          >
            {loading ? "…" : expanded ? "▾" : "▸"}
          </button>
        ) : (
          <span className="explorer-tree-toggle" aria-hidden />
        )}
        <button
          type="button"
          className="explorer-tree-label"
          title={entry.path}
          onClick={() => onSelect(entry.path)}
        >
          {entry.name}
        </button>
      </div>
      {entry.is_dir && expanded && children && children.length > 0 && (
        <ul className="explorer-tree-children" role="group">
          {children.map((child) => (
            <TreeNode
              key={child.path}
              entry={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              expandedPaths={expandedPaths}
              onToggle={onToggle}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}
      {expanded && cursor && <button disabled={loading} onClick={() => load(cursor)}>More folders</button>}
      {expanded && error && <span role="status">{error} <button onClick={() => load()}>Refresh folders</button></span>}
    </li>
  );
}

interface Props {
  roots: BrowseEntry[];
  selectedPath: string;
  onSelect: (path: string) => void;
}

export function FileExplorerTree({ roots, selectedPath, onSelect }: Props) {
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(() => new Set());

  const handleToggle = useCallback((path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  useEffect(() => {
    if (!selectedPath) return;
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      for (const path of explorerBreadcrumbs(selectedPath).map((crumb) => crumb.path)) {
        next.add(path);
      }
      return next;
    });
  }, [selectedPath]);

  return (
    <nav className="explorer-tree" aria-label="Folder tree">
      <ul className="explorer-tree-roots" role="tree">
        {roots.map((root) => (
          <TreeNode
            key={root.path}
            entry={root}
            depth={0}
            selectedPath={selectedPath}
            expandedPaths={expandedPaths}
            onToggle={handleToggle}
            onSelect={onSelect}
          />
        ))}
      </ul>
    </nav>
  );
}
