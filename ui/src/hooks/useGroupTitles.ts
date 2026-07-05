import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "audiotheca.groupTitles.v1";

type TitleMap = Record<string, Record<string, string>>;

function readStore(): TitleMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as TitleMap;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeStore(map: TitleMap) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    /* quota / private mode */
  }
}

export function useGroupTitles(layoutId: string) {
  const [titles, setTitles] = useState<Record<string, string>>(() => readStore()[layoutId] ?? {});

  useEffect(() => {
    setTitles(readStore()[layoutId] ?? {});
  }, [layoutId]);

  const getTitle = useCallback(
    (groupId: string, defaultTitle: string) => titles[groupId]?.trim() || defaultTitle,
    [titles],
  );

  const setTitle = useCallback(
    (groupId: string, title: string) => {
      const store = readStore();
      const layoutTitles = { ...(store[layoutId] ?? {}) };
      const trimmed = title.trim();
      if (trimmed) {
        layoutTitles[groupId] = trimmed;
      } else {
        delete layoutTitles[groupId];
      }
      store[layoutId] = layoutTitles;
      writeStore(store);
      setTitles(layoutTitles);
    },
    [layoutId],
  );

  return { getTitle, setTitle };
}
