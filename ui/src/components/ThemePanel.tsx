import { useEffect, useRef, useState } from "react";
import { EDITABLE_TOKEN_GROUPS, useTheme } from "../contexts/ThemeContext";
import type { ThemePreset } from "../themes/types";

function ThemeSwatch({ theme }: { theme: ThemePreset }) {
  const { accent, bg, text, warning, danger } = theme.tokens;
  return (
    <div className="theme-swatch" aria-hidden>
      <span style={{ background: bg }} />
      <span style={{ background: accent }} />
      <span style={{ background: text }} />
      <span style={{ background: warning }} />
      <span style={{ background: danger }} />
    </div>
  );
}

function ThemeCard({
  theme,
  active,
  onSelect,
}: {
  theme: ThemePreset;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`theme-card${active ? " active" : ""}`}
      onClick={onSelect}
      title={theme.description}
    >
      <ThemeSwatch theme={theme} />
      <span className="theme-card-name">{theme.name}</span>
      {theme.builtIn && <span className="theme-card-badge">Built-in</span>}
    </button>
  );
}

export function ThemePanel() {
  const {
    activeId,
    activeTheme,
    themes,
    customThemes,
    setActiveTheme,
    saveTheme,
    deleteTheme,
    duplicateAsCustom,
    updateToken,
    exportTheme,
    importTheme,
  } = useTheme();

  const [editorId, setEditorId] = useState<string | null>(null);
  const [customName, setCustomName] = useState("");
  const [importText, setImportText] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const bootstrapped = useRef(false);

  useEffect(() => {
    if (bootstrapped.current) return;
    bootstrapped.current = true;
    setEditorId(activeId);
  }, [activeId]);

  const editorTheme = editorId ? themes.find((t) => t.id === editorId) ?? null : null;
  const isCustomEditor = editorTheme && !editorTheme.builtIn;

  function flash(next: string) {
    setMsg(next);
    window.setTimeout(() => setMsg(null), 2500);
  }

  function handleDuplicate() {
    const name = customName.trim() || `${activeTheme.name} Custom`;
    try {
      const dup = duplicateAsCustom(activeId, name);
      saveTheme(dup);
      setEditorId(dup.id);
      setCustomName("");
      flash(`Saved custom theme “${dup.name}”`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not duplicate theme");
    }
  }

  function handleImport() {
    setErr(null);
    try {
      const theme = importTheme(importText.trim());
      setEditorId(theme.id);
      setImportText("");
      flash(`Imported “${theme.name}”`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Import failed");
    }
  }

  function handleFileImport(file: File) {
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result ?? "");
      setImportText(text);
      try {
        const theme = importTheme(text);
        setEditorId(theme.id);
        flash(`Imported “${theme.name}”`);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Import failed");
      }
    };
    reader.readAsText(file);
  }

  return (
    <div className="theme-panel">
      {msg && <div className="banner dry">{msg}</div>}
      {err && <div className="error">{err}</div>}

      <div className="theme-panel-toolbar">
        <label className="context-field theme-name-field">
          <span className="context-label">Save copy as</span>
          <input
            type="text"
            className="field-input"
            placeholder={`${activeTheme.name} Custom`}
            value={customName}
            onChange={(e) => setCustomName(e.target.value)}
          />
        </label>
        <button type="button" className="text-btn" onClick={handleDuplicate}>
          Duplicate &amp; save
        </button>
        <button type="button" className="text-btn" onClick={() => exportTheme(activeId)}>
          Export active
        </button>
        <button type="button" className="text-btn" onClick={() => fileRef.current?.click()}>
          Import file
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          className="theme-file-input"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleFileImport(file);
            e.target.value = "";
          }}
        />
      </div>

      <div className="theme-grid-scroll">
        <div className="theme-grid" role="list" aria-label="Theme presets">
          {themes.map((theme) => (
            <ThemeCard
              key={theme.id}
              theme={theme}
              active={theme.id === activeId}
              onSelect={() => {
                setActiveTheme(theme.id);
                setEditorId(theme.id);
              }}
            />
          ))}
        </div>
      </div>

      {editorTheme && (
        <div className="theme-editor">
          <header className="theme-editor-header">
            <div>
              <h4>{editorTheme.name}</h4>
              <p className="count-muted">{editorTheme.description}</p>
            </div>
            <div className="theme-editor-actions">
              <button type="button" className="text-btn" onClick={() => exportTheme(editorTheme.id)}>
                Export
              </button>
              {isCustomEditor && (
                <button
                  type="button"
                  className="danger-btn"
                  onClick={() => {
                    if (window.confirm(`Delete custom theme “${editorTheme.name}”?`)) {
                      deleteTheme(editorTheme.id);
                      setEditorId(null);
                    }
                  }}
                >
                  Delete
                </button>
              )}
            </div>
          </header>

          {!isCustomEditor && (
            <p className="count-muted theme-editor-hint">
              Built-in presets are read-only. Use <strong>Duplicate &amp; save</strong> to create an editable copy.
            </p>
          )}

          <div className="theme-token-groups">
            {EDITABLE_TOKEN_GROUPS.map((group) => (
              <fieldset key={group.label} className="theme-token-group">
                <legend>{group.label}</legend>
                <div className="theme-token-grid">
                  {group.keys.map((key) => (
                    <label key={key} className="theme-token-field">
                      <span className="theme-token-label">{key}</span>
                      <input
                        type="text"
                        className="field-input theme-token-input"
                        value={editorTheme.tokens[key]}
                        disabled={!isCustomEditor}
                        onChange={(e) => updateToken(editorTheme.id, key, e.target.value)}
                      />
                      <input
                        type="color"
                        className="theme-color-picker"
                        value={toHexColor(editorTheme.tokens[key])}
                        disabled={!isCustomEditor || !isHexable(editorTheme.tokens[key])}
                        onChange={(e) => updateToken(editorTheme.id, key, e.target.value)}
                        title={`Pick color for ${key}`}
                      />
                    </label>
                  ))}
                </div>
              </fieldset>
            ))}
          </div>
        </div>
      )}

      <details className="theme-import-paste">
        <summary>Paste theme JSON</summary>
        <textarea
          className="field-input field-textarea"
          rows={5}
          placeholder='{"format":"audiotheca-theme","version":1,"theme":{...}}'
          value={importText}
          onChange={(e) => setImportText(e.target.value)}
        />
        <button type="button" className="text-btn" disabled={!importText.trim()} onClick={handleImport}>
          Import pasted JSON
        </button>
      </details>

      {customThemes.length > 0 && (
        <p className="count-muted theme-custom-count">
          {customThemes.length} custom theme{customThemes.length === 1 ? "" : "s"} saved locally.
        </p>
      )}
    </div>
  );
}

function isHexable(value: string): boolean {
  return /^#[0-9a-fA-F]{6}$/.test(value);
}

function toHexColor(value: string): string {
  if (isHexable(value)) return value;
  return "#000000";
}
