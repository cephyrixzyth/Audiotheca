import { useDesktopCloseBehavior } from "../hooks/useDesktopCloseBehavior";

export function DesktopCloseBehaviorPanel() {
  const { settings, setAction, setConfirmOnClose } = useDesktopCloseBehavior();

  return (
    <div className="field-stack">
      <p className="count-muted">
        Controls what happens when you click the window close button. The system tray icon can restore the
        window or quit from its menu.
      </p>
      <fieldset className="desktop-close-fieldset">
        <legend className="context-label">Desktop close behavior</legend>
        <label className="desktop-close-option">
          <input
            type="radio"
            name="desktop-close-settings-action"
            checked={settings.action === "tray"}
            onChange={() => setAction("tray")}
          />
          <span>Minimize to system tray</span>
        </label>
        <label className="desktop-close-option">
          <input
            type="radio"
            name="desktop-close-settings-action"
            checked={settings.action === "quit"}
            onChange={() => setAction("quit")}
          />
          <span>Quit completely</span>
        </label>
      </fieldset>
      <label className="desktop-close-option remember">
        <input
          type="checkbox"
          checked={settings.confirmOnClose}
          onChange={(e) => setConfirmOnClose(e.target.checked)}
        />
        <span>Ask every time before closing</span>
      </label>
    </div>
  );
}
