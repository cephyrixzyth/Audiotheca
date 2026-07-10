/** Stable path key matching backend `api.path_logic.normalize_logical_path`. */
export function pathKey(path: string): string {
  return path.replace(/\\/g, "/").trim().toLowerCase();
}

/** True when two filesystem paths refer to the same feedback key. */
export function pathsEqual(a: string, b: string): boolean {
  return pathKey(a) === pathKey(b);
}

/** Find a record value by raw or normalized path key. */
export function lookupByPath<T>(
  map: Record<string, T> | undefined,
  path: string,
): T | undefined {
  if (!map) return undefined;
  if (path in map) return map[path];
  const key = pathKey(path);
  if (key in map) return map[key];
  for (const [stored, value] of Object.entries(map)) {
    if (pathKey(stored) === key) return value;
  }
  return undefined;
}

/** True when `path` appears in a list of raw or normalized paths. */
export function listHasPath(list: string[] | undefined, path: string): boolean {
  if (!list?.length) return false;
  const key = pathKey(path);
  return list.some((entry) => pathKey(entry) === key);
}
