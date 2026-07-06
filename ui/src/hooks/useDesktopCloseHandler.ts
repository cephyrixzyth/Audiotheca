import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import {
  getDesktopCloseBehavior,
  saveDesktopCloseBehavior,
  type DesktopCloseAction,
} from "./useDesktopCloseBehavior";
import { isTauri } from "../platform";

async function applyCloseAction(action: DesktopCloseAction): Promise<void> {
  if (action === "tray") {
    await invoke("hide_main_window");
    return;
  }
  await invoke("quit_app");
}

export function useDesktopCloseHandler() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogAction, setDialogAction] = useState<DesktopCloseAction>("tray");
  const handlingRef = useRef(false);

  const handleCloseRequest = useCallback(async () => {
    if (handlingRef.current) return;
    handlingRef.current = true;
    try {
      const settings = getDesktopCloseBehavior();
      if (!settings.confirmOnClose) {
        await applyCloseAction(settings.action);
        return;
      }
      setDialogAction(settings.action);
      setDialogOpen(true);
    } finally {
      window.setTimeout(() => {
        handlingRef.current = false;
      }, 250);
    }
  }, []);

  useEffect(() => {
    if (!isTauri()) return undefined;

    let unlistenEvent: (() => void) | undefined;

    void (async () => {
      unlistenEvent = await listen("close-requested", () => {
        void handleCloseRequest();
      });
    })();

    return () => {
      unlistenEvent?.();
    };
  }, [handleCloseRequest]);

  const onDialogConfirm = useCallback((action: DesktopCloseAction, rememberChoice: boolean) => {
    const confirmOnClose = rememberChoice ? false : getDesktopCloseBehavior().confirmOnClose;
    saveDesktopCloseBehavior({ action, confirmOnClose });
    setDialogOpen(false);
    void applyCloseAction(action);
  }, []);

  const onDialogCancel = useCallback(() => {
    setDialogOpen(false);
  }, []);

  return {
    dialogOpen,
    dialogAction,
    onDialogConfirm,
    onDialogCancel,
  };
}
