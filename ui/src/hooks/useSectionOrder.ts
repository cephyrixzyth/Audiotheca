import { useCallback, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "audiotheca.sectionOrder.v1";
export const SPACER_PREFIX = "__spacer__:";

type OrderMap = Record<string, string[]>;

export function isSpacerId(id: string): boolean {
  return id.startsWith(SPACER_PREFIX);
}

export function newSpacerId(): string {
  return `${SPACER_PREFIX}${Math.random().toString(36).slice(2, 10)}`;
}

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
  const result = saved.filter((id) => defaults.includes(id) || isSpacerId(id));
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

function moveAfter(order: string[], fromId: string, afterId: string): string[] {
  if (fromId === afterId) return order;
  const next = order.filter((id) => id !== fromId);
  const targetIdx = next.indexOf(afterId);
  if (targetIdx < 0) return order;
  next.splice(targetIdx + 1, 0, fromId);
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

  const commitOrder = useCallback(
    (next: string[]) => {
      const merged = mergeSectionOrder(next, defaultOrder);
      const store = readStore();
      store[layoutId] = merged;
      writeStore(store);
      return merged;
    },
    [layoutId, defaultsKey, defaultOrder],
  );

  const reorder = useCallback(
    (fromId: string, toId: string) => {
      setOrder((prev) => commitOrder(moveBefore(prev, fromId, toId)));
    },
    [commitOrder],
  );

  const reorderAfter = useCallback(
    (fromId: string, afterId: string) => {
      setOrder((prev) => commitOrder(moveAfter(prev, fromId, afterId)));
    },
    [commitOrder],
  );

  const moveUp = useCallback(
    (sectionId: string) => {
      setOrder((prev) => {
        const idx = prev.indexOf(sectionId);
        if (idx <= 0) return prev;
        const next = [...prev];
        [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
        return commitOrder(next);
      });
    },
    [commitOrder],
  );

  const moveDown = useCallback(
    (sectionId: string) => {
      setOrder((prev) => {
        const idx = prev.indexOf(sectionId);
        if (idx < 0 || idx >= prev.length - 1) return prev;
        const next = [...prev];
        [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
        return commitOrder(next);
      });
    },
    [commitOrder],
  );

  const insertSpacerAfter = useCallback(
    (afterId: string | null) => {
      const spacerId = newSpacerId();
      setOrder((prev) => {
        if (!afterId) {
          return commitOrder([spacerId, ...prev]);
        }
        const idx = prev.indexOf(afterId);
        const next = [...prev];
        next.splice(idx < 0 ? next.length : idx + 1, 0, spacerId);
        return commitOrder(next);
      });
    },
    [commitOrder],
  );

  const removeSpacer = useCallback(
    (spacerId: string) => {
      if (!isSpacerId(spacerId)) return;
      setOrder((prev) => commitOrder(prev.filter((id) => id !== spacerId)));
    },
    [commitOrder],
  );

  const resetOrder = useCallback(() => {
    commitOrder([...defaultOrder]);
  }, [defaultOrder, commitOrder]);

  const orderedIds = useMemo(
    () => mergeSectionOrder(order, defaultOrder),
    [order, defaultsKey, defaultOrder],
  );

  return {
    orderedIds,
    reorder,
    reorderAfter,
    moveUp,
    moveDown,
    insertSpacerAfter,
    removeSpacer,
    resetOrder,
  };
}
