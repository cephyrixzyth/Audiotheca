import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { FileExplorerPanel } from "../components/FileExplorer";

type Ctx = {
  openPath: (path: string) => void;
  close: () => void;
};

const FileExplorerContext = createContext<Ctx | null>(null);

export function FileExplorerProvider({ children }: { children: ReactNode }) {
  const [path, setPath] = useState<string | null>(null);

  const openPath = useCallback((next: string) => {
    if (next?.trim()) setPath(next.trim());
  }, []);

  const close = useCallback(() => setPath(null), []);

  const value = useMemo(() => ({ openPath, close }), [openPath, close]);

  return (
    <FileExplorerContext.Provider value={value}>
      {children}
      {path != null && <FileExplorerPanel initialPath={path} onClose={close} />}
    </FileExplorerContext.Provider>
  );
}

export function useFileExplorer(): Ctx {
  const ctx = useContext(FileExplorerContext);
  if (!ctx) {
    throw new Error("useFileExplorer must be used within FileExplorerProvider");
  }
  return ctx;
}
