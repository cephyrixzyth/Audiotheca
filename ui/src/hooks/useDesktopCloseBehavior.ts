import { useCallback, useState } from "react";
import { isTauri } from "../platform";

const STORAGE_KEY = "audiotheca.desktopClose.v1";

export type DesktopCloseAction = "tray" | "quit";

export interface DesktopCloseBehavior {
  action: DesktopCloseAction;
  confirmOnClose: boolean;
}

function isWindowsDesktop(): boolean {
  return typeof navigator !== "undefined" && /Windows/i.test(navigator.userAgent);
}

export function defaultDesktopCloseAction(): DesktopCloseAction {
  if (isTauri() && isWindowsDesktop()) {
    return "tray";
  }
  return "quit";
}

function readDesktopCloseBehavior(): DesktopCloseBehavior {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return { action: defaultDesktopCloseAction(), confirmOnClose: true };
    }
    const parsed = JSON.parse(raw) as Partial<DesktopCloseBehavior>;
    return {
      action: parsed.action === "quit" ? "quit" : "tray",
      confirmOnClose: parsed.confirmOnClose !== false,
    };
  } catch {
    return { action: defaultDesktopCloseAction(), confirmOnClose: true };
  }
}

export function getDesktopCloseBehavior(): DesktopCloseBehavior {
  return readDesktopCloseBehavior();
}

export function saveDesktopCloseBehavior(settings: DesktopCloseBehavior): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    /* private mode / quota */
  }
}

export function useDesktopCloseBehavior() {
  const [settings, setSettings] = useState<DesktopCloseBehavior>(readDesktopCloseBehavior);

  const update = useCallback((patch: Partial<DesktopCloseBehavior>) => {
    setSettings((prev) => {
      const next: DesktopCloseBehavior = { ...prev, ...patch };
      saveDesktopCloseBehavior(next);
      return next;
    });
  }, []);

  const setAction = useCallback(
    (action: DesktopCloseAction) => {
      update({ action });
    },
    [update],
  );

  const setConfirmOnClose = useCallback(
    (confirmOnClose: boolean) => {
      update({ confirmOnClose });
    },
    [update],
  );

  return { settings, setAction, setConfirmOnClose, update };
}
