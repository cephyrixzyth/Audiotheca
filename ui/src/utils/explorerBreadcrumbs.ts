/** Construct absolute ancestor paths for POSIX, drive-letter and UNC libraries. */
export function explorerBreadcrumbs(path: string) {
  const sep = path.includes("\\") ? "\\" : "/";
  const parts = path.split(/[/\\]/).filter(Boolean);
  const unc = path.startsWith("\\\\") || path.startsWith("//");
  let prefix = unc ? sep + sep : path.startsWith("/") ? "/" : "";
  return parts.map((name) => {
    prefix = prefix && !prefix.endsWith(sep) ? prefix + sep + name : prefix + name;
    if (/^[a-z]:$/i.test(prefix)) prefix += sep;
    return { label: name, path: prefix };
  });
}
