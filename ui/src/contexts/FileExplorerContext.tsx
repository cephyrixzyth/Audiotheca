import {
  createContext,
  lazy,
  Suspense,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { LoadingStatus } from "../ui/LoadingStatus";
const FileExplorerPanel = lazy(() =>
  import("../components/FileExplorer").then((module) => ({
    default: module.FileExplorerPanel,
  })),
);

const LAST_PATH_KEY = "audiotheca.explorer.lastPath";
const PINNED_KEY = "audiotheca.explorer.pinned";

export type OpenPathOptions = {
  secondary?: string;
  dualPane?: boolean;
};

type Ctx = {
  openPath: (path: string, opts?: OpenPathOptions) => void;
  openAtRoots: () => void;
  openDualPane: (left: string, right: string) => void;
  close: () => void;
  togglePin: () => void;
  setPopOut: (enabled: boolean) => void;
  panelOpen: boolean;
  pinned: boolean;
  popOut: boolean;
  dualPane: boolean;
  stamp: string | null;
  subtreeRoot: string | null;
};

const FileExplorerContext = createContext<Ctx | null>(null);

function loadPinned(): boolean {
  try {
    return sessionStorage.getItem(PINNED_KEY) === "1";
  } catch {
    return false;
  }
}

function loadLastPath(): string | null {
  try {
    const value = sessionStorage.getItem(LAST_PATH_KEY);
    return value?.trim() || null;
  } catch {
    return null;
  }
}

function saveLastPath(path: string): void {
  try {
    sessionStorage.setItem(LAST_PATH_KEY, path);
  } catch {
    /* ignore */
  }
}

type ProviderProps = {
  children: ReactNode;
  stamp?: string;
  subtreeRoot?: string | null;
};

export function FileExplorerProvider({
  children,
  stamp = "",
  subtreeRoot = null,
}: ProviderProps) {
  const [path, setPath] = useState<string | null>(null);
  const [secondaryPath, setSecondaryPath] = useState<string | null>(null);
  const [dualPane, setDualPane] = useState(false);
  const [pinned, setPinned] = useState(loadPinned);
  const [popOut, setPopOut] = useState(false);

  const openPath = useCallback((next: string, opts?: OpenPathOptions) => {
    const trimmed = next?.trim();
    if (!trimmed) return;
    saveLastPath(trimmed);
    setPath(trimmed);
    if (opts?.dualPane && opts.secondary?.trim()) {
      setDualPane(true);
      setSecondaryPath(opts.secondary.trim());
    } else if (opts?.secondary?.trim()) {
      setDualPane(true);
      setSecondaryPath(opts.secondary.trim());
    } else {
      setDualPane(false);
      setSecondaryPath(null);
    }
  }, []);

  const openAtRoots = useCallback(() => {
    const last = loadLastPath();
    setPath(last ?? "");
    setDualPane(false);
    setSecondaryPath(null);
  }, []);

  const openDualPane = useCallback(
    (left: string, right: string) => {
      openPath(left, { secondary: right, dualPane: true });
    },
    [openPath],
  );

  const close = useCallback(() => {
    setPath(null);
    setSecondaryPath(null);
    setDualPane(false);
    setPopOut(false);
  }, []);

  const togglePin = useCallback(() => {
    setPinned((prev) => {
      const next = !prev;
      try {
        sessionStorage.setItem(PINNED_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({
      openPath,
      openAtRoots,
      openDualPane,
      close,
      togglePin,
      setPopOut,
      panelOpen: path != null,
      pinned,
      popOut,
      dualPane,
      stamp: stamp || null,
      subtreeRoot,
    }),
    [
      openPath,
      openAtRoots,
      openDualPane,
      close,
      togglePin,
      path,
      pinned,
      popOut,
      dualPane,
      stamp,
      subtreeRoot,
    ],
  );

  return (
    <FileExplorerContext.Provider value={value}>
      {children}
      {path != null && (
        <Suspense fallback={<LoadingStatus>Opening library…</LoadingStatus>}>
          <FileExplorerPanel
            initialPath={path}
            secondaryPath={secondaryPath}
            dualPane={dualPane}
            stamp={stamp || null}
            subtreeRoot={subtreeRoot}
            pinned={pinned}
            popOut={popOut}
            onTogglePopOut={() => setPopOut((v) => !v)}
            onTogglePin={togglePin}
            onClose={close}
          />
        </Suspense>
      )}
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

/** Drag-and-drop MIME type for explorer paths. */
export const EXPLORER_PATH_MIME = "application/x-audiotheca-path";

export function useExplorerPathDrag(path: string): {
  draggable: boolean;
  onDragStart: (e: React.DragEvent) => void;
} {
  const onDragStart = useCallback(
    (e: React.DragEvent) => {
      e.dataTransfer.setData("text/plain", path);
      e.dataTransfer.setData(EXPLORER_PATH_MIME, path);
      e.dataTransfer.effectAllowed = "copy";
    },
    [path],
  );
  return { draggable: Boolean(path), onDragStart };
}
