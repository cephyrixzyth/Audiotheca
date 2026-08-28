import { useState } from "react";
import { useTheme } from "../contexts/ThemeContext";
import { DropdownMenu } from "../ui";

export function ThemeSwitcher() {
  const { activeId, activeTheme, themes, setActiveTheme } = useTheme();
  const [contrastPreview, setContrastPreview] = useState(100);

  return (
    <div className="theme-switcher">
      <DropdownMenu
        align="end"
        ariaLabel="Theme presets"
        trigger={
          <button
            type="button"
            className="theme-switcher-trigger"
            title="UI color theme"
            aria-label="Select UI theme"
          >
            <span className="theme-switcher-icon" aria-hidden>
              ◐
            </span>
            <span className="theme-switcher-label">{activeTheme.name}</span>
            <span className="theme-switcher-chevron" aria-hidden>
              ▾
            </span>
          </button>
        }
        items={themes.map((theme) => ({
          id: theme.id,
          active: theme.id === activeId,
          label: (
            <span className="theme-switcher-option-name">
              {theme.name}
              {!theme.builtIn ? <span className="theme-switcher-custom"> ★</span> : null}
            </span>
          ),
          onSelect: () => setActiveTheme(theme.id),
        }))}
        footer={
          <div className="theme-contrast-preview" aria-label="Contrast preview">
            <div
              className="theme-contrast-swatch"
              style={{
                background: activeTheme.tokens.bg,
                color: activeTheme.tokens.text,
                borderColor: activeTheme.tokens.border,
                filter: `contrast(${contrastPreview / 100})`,
              }}
            >
              <span style={{ color: activeTheme.tokens.accent }}>Accent</span>
              <span style={{ color: activeTheme.tokens.textMuted }}>Muted</span>
            </div>
            <label className="theme-contrast-slider">
              <span className="context-label">Contrast</span>
              <input
                type="range"
                min={70}
                max={140}
                value={contrastPreview}
                aria-label="Contrast"
                onChange={(e) => setContrastPreview(Number(e.target.value))}
              />
              <span className="count-muted">{contrastPreview}%</span>
            </label>
          </div>
        }
      />
    </div>
  );
}
