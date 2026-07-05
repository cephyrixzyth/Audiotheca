import { useTheme } from "../contexts/ThemeContext";
import { ThemePanel } from "./ThemePanel";

function ThemePreview() {
  const { activeTheme } = useTheme();
  const { accent, bg, text, warning, danger, border } = activeTheme.tokens;

  return (
    <div className="theme-studio-preview" style={{ background: bg, color: text, borderColor: border }}>
      <div className="theme-studio-preview-header" style={{ borderColor: border }}>
        <strong>Live preview</strong>
        <span className="theme-studio-preview-name">{activeTheme.name}</span>
      </div>
      <div className="theme-studio-preview-body">
        <button type="button" className="primary-btn theme-studio-sample-btn" style={{ background: accent }}>
          Primary action
        </button>
        <button type="button" className="text-btn theme-studio-sample-btn">
          Secondary
        </button>
        <div className="stat-grid compact">
          <div className="stat-tile tone-accent">
            <div className="stat-label">Ready</div>
            <div className="stat-value">128</div>
          </div>
          <div className="stat-tile tone-warning">
            <div className="stat-label">Review</div>
            <div className="stat-value" style={{ color: warning }}>
              12
            </div>
          </div>
          <div className="stat-tile tone-danger">
            <div className="stat-label">Blocked</div>
            <div className="stat-value" style={{ color: danger }}>
              3
            </div>
          </div>
        </div>
        <div className="banner dry theme-studio-banner">Dry-run banner sample</div>
        <div className="log-lines theme-studio-log">
          <div className="log-line log-info log-kind-scanner">Phase 1a — listing folders…</div>
          <div className="log-line log-warn log-kind-engine">Slow NAS read on _projects</div>
          <div className="log-line log-error log-kind-job">Permission denied: sample.dll</div>
        </div>
      </div>
    </div>
  );
}

/** WYSIWYG theme studio — token editor plus live component preview. */
export function ThemeStudioPanel() {
  return (
    <div className="theme-studio">
      <p className="count-muted">
        Edit tokens on the left; preview updates instantly. Save custom themes for export or import on other machines.
      </p>
      <div className="theme-studio-layout">
        <div className="theme-studio-editor">
          <ThemePanel />
        </div>
        <ThemePreview />
      </div>
    </div>
  );
}
