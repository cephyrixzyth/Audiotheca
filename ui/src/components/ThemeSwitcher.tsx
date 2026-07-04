import { useTheme } from "../contexts/ThemeContext";

export function ThemeSwitcher() {
  const { activeId, themes, setActiveTheme } = useTheme();

  return (
    <label className="theme-switcher" title="UI color theme">
      <span className="theme-switcher-icon" aria-hidden>
        ◐
      </span>
      <select
        className="field-input theme-switcher-select"
        value={activeId}
        onChange={(e) => setActiveTheme(e.target.value)}
        aria-label="Select UI theme"
      >
        {themes.map((theme) => (
          <option key={theme.id} value={theme.id}>
            {theme.name}
            {theme.builtIn ? "" : " ★"}
          </option>
        ))}
      </select>
    </label>
  );
}
