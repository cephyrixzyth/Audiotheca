import { useCallback, useEffect, useState } from "react";

const SPAN_STORAGE_KEY = "audiotheca.sectionSpan.v1";

type SpanMap = Record<string, Record<string, number>>;

function readSpans(): SpanMap {
  try {
    const raw = localStorage.getItem(SPAN_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as SpanMap;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeSpans(map: SpanMap) {
  try {
    localStorage.setItem(SPAN_STORAGE_KEY, JSON.stringify(map));
  } catch {
    /* quota */
  }
}

export function useSectionSpan(layoutId: string) {
  const [spans, setSpans] = useState<Record<string, number>>(() => readSpans()[layoutId] ?? {});

  useEffect(() => {
    setSpans(readSpans()[layoutId] ?? {});
  }, [layoutId]);

  const getSpan = useCallback(
    (sectionId: string, defaultSpan = 1) => spans[sectionId] ?? defaultSpan,
    [spans],
  );

  const setSpan = useCallback(
    (sectionId: string, span: number) => {
      const clamped = Math.max(1, Math.min(4, Math.round(span)));
      setSpans((prev) => {
        const next = { ...prev, [sectionId]: clamped };
        const store = readSpans();
        store[layoutId] = next;
        writeSpans(store);
        return next;
      });
    },
    [layoutId],
  );

  const cycleSpan = useCallback(
    (sectionId: string, defaultSpan = 1, maxSpan = 2) => {
      const current = getSpan(sectionId, defaultSpan);
      const next = current >= maxSpan ? 1 : current + 1;
      setSpan(sectionId, next);
    },
    [getSpan, setSpan],
  );

  return { getSpan, setSpan, cycleSpan };
}
