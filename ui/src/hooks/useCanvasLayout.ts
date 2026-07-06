import type { CSSProperties } from "react";
import { useCallback, useState } from "react";

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
    window.dispatchEvent(new Event("audiotheca-canvas-layout"));
  } catch {
    /* quota */
  }
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export function useCanvasLayout(layoutId: string) {
  const [revision, setRevision] = useState(0);

  const getSlot = useCallback(
    (sectionId: string, fallbackSpan: number): CanvasSlot => {
      void revision;
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
    [layoutId, revision],
  );

  const setSlot = useCallback(
    (sectionId: string, slot: CanvasSlot) => {
      const store = readStore();
      if (!store[layoutId]) store[layoutId] = {};
      store[layoutId][sectionId] = slot;
      writeStore(store);
      setRevision((v) => v + 1);
    },
    [layoutId],
  );

  const resizeSlot = useCallback(
    (sectionId: string, fallbackSpan: number, delta: { colSpan?: number; rowSpan?: number }) => {
      const current = getSlot(sectionId, fallbackSpan);
      setSlot(sectionId, {
        ...current,
        colSpan: clamp(current.colSpan + (delta.colSpan ?? 0), 1, 12),
        rowSpan: clamp(current.rowSpan + (delta.rowSpan ?? 0), 1, 6),
      });
    },
    [getSlot, setSlot],
  );

  return { getSlot, setSlot, resizeSlot };
}

export function canvasStyle(slot: CanvasSlot): CSSProperties {
  return {
    gridColumn: `${slot.col} / span ${slot.colSpan}`,
    gridRow: `${slot.row} / span ${slot.rowSpan}`,
  };
}
