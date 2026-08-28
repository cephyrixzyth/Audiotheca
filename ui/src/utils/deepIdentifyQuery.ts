import type { DeepIdentifyItem } from "../types";

export function matchesDeepIdentifyQuery(row: DeepIdentifyItem, q: string): boolean {
  if (!q) return true;
  return (
    row.item_name.toLowerCase().includes(q) ||
    row.path.toLowerCase().includes(q) ||
    row.vendor.toLowerCase().includes(q) ||
    row.method.toLowerCase().includes(q) ||
    row.evidence.toLowerCase().includes(q) ||
    row.previous_vendor.toLowerCase().includes(q)
  );
}
