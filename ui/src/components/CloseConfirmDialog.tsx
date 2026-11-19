import { Dialog } from "../ui/Dialog";
import { useEffect, useState } from "react";
import type { DesktopCloseAction } from "../hooks/useDesktopCloseBehavior";
import { Button } from "../ui";

interface Props {
  open: boolean;
  initialAction: DesktopCloseAction;
  onConfirm: (action: DesktopCloseAction, rememberChoice: boolean) => void;
  onCancel: () => void;
}

export function CloseConfirmDialog({ open, initialAction, onConfirm, onCancel }: Props) {
  const [action, setAction] = useState<DesktopCloseAction>(initialAction);
  const [rememberChoice, setRememberChoice] = useState(false);

  useEffect(() => {
    if (open) {
      setAction(initialAction);
      setRememberChoice(false);
    }
  }, [open, initialAction]);

  if (!open) return null;

  return (
    <Dialog open={open} onOpenChange={value => { if (!value) onCancel(); }}
      title="Close Audiotheca?" description="Choose whether to hide the window or quit the app.">
        <fieldset className="desktop-close-fieldset">
          <legend className="context-label">When I click the close button</legend>
          <label className="desktop-close-option">
            <input
              type="radio"
              name="desktop-close-action"
              checked={action === "tray"}
              onChange={() => setAction("tray")}
            />
            <span>Minimize to system tray</span>
          </label>
          <label className="desktop-close-option">
            <input
              type="radio"
              name="desktop-close-action"
              checked={action === "quit"}
              onChange={() => setAction("quit")}
            />
            <span>Quit completely</span>
          </label>
        </fieldset>

        <label className="desktop-close-option remember">
          <input
            type="checkbox"
            checked={rememberChoice}
            onChange={(e) => setRememberChoice(e.target.checked)}
          />
          <span>Remember this choice (don&apos;t ask again)</span>
        </label>

        <div className="env-actions" style={{ marginTop: "1rem" }}>
          <Button variant="primary" onClick={() => onConfirm(action, rememberChoice)}>
            {action === "tray" ? "Hide to tray" : "Quit"}
          </Button>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </div>
    </Dialog>
  );
}
