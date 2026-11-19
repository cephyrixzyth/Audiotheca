import { useEffect, useState } from "react";
import { ROOT_CHANGED, defaultLibraryRootSync, getDefaultLibraryRoot } from "../platform";

/** Resolves the configured library root (API env or build default). */
export function useLibraryRoot(): string {
  const [root, setRoot] = useState(defaultLibraryRootSync());

  useEffect(() => {
    let current = true;
    const refresh = () => { void getDefaultLibraryRoot().then(root => { if (current) setRoot(root); }); };
    window.addEventListener(ROOT_CHANGED, refresh);
    refresh();
    return () => { current = false; window.removeEventListener(ROOT_CHANGED, refresh); };
  }, []);

  return root;
}
