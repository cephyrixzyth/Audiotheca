import type { CSSProperties } from "react";
import { useCallback } from "react";

const CANVAS_KEY = "audiotheca.canvasLayout.v1";

export interface CanvasSlot {
  col: number;
  row: number;
  colSpan: number;
  rowSpan: number;
}

export type CanvasLayoutStore = Record<string, Record<string, CanvasSlot>>;

function readStore(): CanvasLayoutStore {
  try {
    const raw = localStorage.getItem(CANVAS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as CanvasLayoutStore;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeStore(store: CanvasLayoutStore) {
  try {
    localStorage.setItem(CANVAS_KEY, JSON.stringify(store));
  } catch {
    /* quota */
  }
}

export function useCanvasLayout(layoutId: string) {
  const getSlot = useCallback(
    (sectionId: string, fallbackSpan: number): CanvasSlot => {
      const store = readStore();
      return (
        store[layoutId]?.[sectionId] ?? {
          col: 1,
          row: 1,
          colSpan: Math.min(12, Math.max(1, fallbackSpan)),
          rowSpan: 1,
        }
      );
    },
    [layoutId],
  );

  const setSlot = useCallback(
    (sectionId: string, slot: CanvasSlot) => {
      const store = readStore();
      if (!store[layoutId]) store[layoutId] = {};
      store[layoutId][sectionId] = slot;
      writeStore(store);
    },
    [layoutId],
  );

  return { getSlot, setSlot };
}

export function canvasStyle(slot: CanvasSlot): CSSProperties {
  return {
    gridColumn: `${slot.col} / span ${slot.colSpan}`,
    gridRow: `${slot.row} / span ${slot.rowSpan}`,
  };
}
