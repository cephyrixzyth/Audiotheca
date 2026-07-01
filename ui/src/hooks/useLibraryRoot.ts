import { useEffect, useState } from "react";
import { defaultLibraryRootSync, getDefaultLibraryRoot } from "../platform";

/** Resolves the configured library root (API env or build default). */
export function useLibraryRoot(): string {
  const [root, setRoot] = useState(defaultLibraryRootSync());

  useEffect(() => {
    void getDefaultLibraryRoot().then(setRoot).catch(() => undefined);
  }, []);

  return root;
}
