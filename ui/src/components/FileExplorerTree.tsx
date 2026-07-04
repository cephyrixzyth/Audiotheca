import { useCallback, useEffect, useRef, useState } from "react";
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
  const expanded = expandedPaths.has(entry.path);
  const loadSeq = useRef(0);

  useEffect(() => {
    if (!expanded) {
      setChildren(null);
      return;
    }
    const seq = ++loadSeq.current;
    setLoading(true);
    void browseTreeChildren(entry.path)
      .then((data) => {
        if (seq !== loadSeq.current) return;
        setChildren(data.children);
      })
      .catch(() => {
        if (seq !== loadSeq.current) return;
        setChildren([]);
      })
      .finally(() => {
        if (seq === loadSeq.current) setLoading(false);
      });
  }, [entry.path, expanded]);

  return (
    <li className="explorer-tree-node">
      <div
        className={`explorer-tree-row ${selectedPath === entry.path ? "selected" : ""}`}
        style={{ paddingLeft: `${depth * 0.75 + 0.25}rem` }}
      >
        <button
          type="button"
          className="explorer-tree-toggle"
          title={expanded ? "Collapse folder" : "Expand folder"}
          aria-expanded={expanded}
          onClick={() => onToggle(entry.path)}
        >
          {loading ? "…" : expanded ? "▾" : "▸"}
        </button>
        <button
          type="button"
          className="explorer-tree-label"
          title={entry.path}
          onClick={() => onSelect(entry.path)}
        >
          {entry.name}
        </button>
      </div>
      {expanded && children && children.length > 0 && (
        <ul className="explorer-tree-children">
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
    </li>
  );
}

interface Props {
  roots: BrowseEntry[];
  selectedPath: string;
  onSelect: (path: string) => void;
}

function ancestorPaths(fullPath: string): string[] {
  if (!fullPath) return [];
  const sep = fullPath.includes("\\") ? "\\" : "/";
  const parts = fullPath.split(/[/\\]/).filter(Boolean);
  const paths: string[] = [];
  let acc = "";
  for (let i = 0; i < parts.length; i += 1) {
    const part = parts[i];
    if (i === 0 && /^[a-zA-Z]:/.test(part)) {
      acc = part.endsWith(":") ? `${part}${sep}` : part.includes(sep) ? part : `${part}${sep}`;
    } else {
      acc = acc ? `${acc}${sep}${part}` : part;
    }
    paths.push(acc);
  }
  return paths;
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
      for (const path of ancestorPaths(selectedPath)) {
        next.add(path);
      }
      return next;
    });
  }, [selectedPath]);

  return (
    <nav className="explorer-tree" aria-label="Folder tree">
      <ul className="explorer-tree-roots">
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
