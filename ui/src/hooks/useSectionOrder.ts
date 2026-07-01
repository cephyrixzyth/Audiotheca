import { useCallback, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "audiotheca.sectionOrder.v1";

type OrderMap = Record<string, string[]>;

function readStore(): OrderMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as OrderMap;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeStore(map: OrderMap) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    /* quota / private mode */
  }
}

export function mergeSectionOrder(saved: string[], defaults: string[]): string[] {
  const result = saved.filter((id) => defaults.includes(id));
  for (const id of defaults) {
    if (!result.includes(id)) result.push(id);
  }
  return result;
}

function moveBefore(order: string[], fromId: string, toId: string): string[] {
  if (fromId === toId) return order;
  const next = order.filter((id) => id !== fromId);
  const targetIdx = next.indexOf(toId);
  if (targetIdx < 0) return order;
  next.splice(targetIdx, 0, fromId);
  return next;
}

export function useSectionOrder(layoutId: string, defaultOrder: string[]) {
  const defaultsKey = defaultOrder.join("\0");

  const [order, setOrder] = useState<string[]>(() => {
    const saved = readStore()[layoutId] ?? [];
    return mergeSectionOrder(saved, defaultOrder);
  });

  useEffect(() => {
    setOrder((prev) => mergeSectionOrder(prev, defaultOrder));
  }, [layoutId, defaultsKey]);

  const persist = useCallback(
    (next: string[]) => {
      const merged = mergeSectionOrder(next, defaultOrder);
      setOrder(merged);
      const store = readStore();
      store[layoutId] = merged;
      writeStore(store);
    },
    [layoutId, defaultsKey],
  );

  const reorder = useCallback(
    (fromId: string, toId: string) => {
      setOrder((prev) => {
        const next = moveBefore(prev, fromId, toId);
        persist(next);
        return next;
      });
    },
    [persist],
  );

  const moveUp = useCallback(
    (sectionId: string) => {
      setOrder((prev) => {
        const idx = prev.indexOf(sectionId);
        if (idx <= 0) return prev;
        const next = [...prev];
        [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
        persist(next);
        return next;
      });
    },
    [persist],
  );

  const moveDown = useCallback(
    (sectionId: string) => {
      setOrder((prev) => {
        const idx = prev.indexOf(sectionId);
        if (idx < 0 || idx >= prev.length - 1) return prev;
        const next = [...prev];
        [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
        persist(next);
        return next;
      });
    },
    [persist],
  );

  const resetOrder = useCallback(() => {
    persist([...defaultOrder]);
  }, [defaultOrder, persist]);

  const orderedIds = useMemo(
    () => mergeSectionOrder(order, defaultOrder),
    [order, defaultsKey],
  );

  return { orderedIds, reorder, moveUp, moveDown, resetOrder };
}
