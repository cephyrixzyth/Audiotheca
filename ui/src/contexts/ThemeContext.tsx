import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  applyTheme,
  duplicateTheme,
  downloadThemeJson,
  getAllThemes,
  loadActiveThemeId,
  loadCustomThemes,
  parseThemeImport,
  resolveTheme,
  saveActiveThemeId,
  saveCustomThemes,
} from "../themes/themeEngine";
import { BUILTIN_THEMES } from "../themes/presets";
import type { ThemePreset, ThemeTokens } from "../themes/types";
import { THEME_TOKEN_KEYS } from "../themes/types";

interface ThemeContextValue {
  activeId: string;
  activeTheme: ThemePreset;
  themes: ThemePreset[];
  customThemes: ThemePreset[];
  setActiveTheme: (id: string) => void;
  saveTheme: (theme: ThemePreset) => void;
  deleteTheme: (id: string) => void;
  duplicateAsCustom: (sourceId: string, name: string) => ThemePreset;
  updateToken: (themeId: string, key: keyof ThemeTokens, value: string) => void;
  exportTheme: (id: string) => void;
  importTheme: (json: string) => ThemePreset;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [activeId, setActiveId] = useState(loadActiveThemeId);
  const [customThemes, setCustomThemes] = useState<ThemePreset[]>(loadCustomThemes);

  const themes = useMemo(() => {
    const customIds = new Set(customThemes.map((t) => t.id));
    const builtins = BUILTIN_THEMES.filter((t) => !customIds.has(t.id));
    return [...builtins, ...customThemes];
  }, [customThemes]);

  const activeTheme = useMemo(
    () => resolveTheme(activeId) ?? themes[0],
    [activeId, themes],
  );

  const setActiveTheme = useCallback((id: string) => {
    const theme = resolveTheme(id) ?? getAllThemes().find((t) => t.id === id);
    if (!theme) return;
    setActiveId(id);
    saveActiveThemeId(id);
    applyTheme(theme);
  }, []);

  const saveTheme = useCallback(
    (theme: ThemePreset) => {
      const next = customThemes.filter((t) => t.id !== theme.id);
      next.push({ ...theme, builtIn: false });
      setCustomThemes(next);
      saveCustomThemes(next);
      setActiveId(theme.id);
      saveActiveThemeId(theme.id);
      applyTheme(theme);
    },
    [customThemes],
  );

  const deleteTheme = useCallback(
    (id: string) => {
      const target = customThemes.find((t) => t.id === id);
      if (!target || target.builtIn) return;
      const next = customThemes.filter((t) => t.id !== id);
      setCustomThemes(next);
      saveCustomThemes(next);
      if (activeId === id) {
        const fallback = themes.find((t) => t.builtIn) ?? themes[0];
        if (fallback) setActiveTheme(fallback.id);
      }
    },
    [activeId, customThemes, setActiveTheme, themes],
  );

  const duplicateAsCustom = useCallback(
    (sourceId: string, name: string) => {
      const source = themes.find((t) => t.id === sourceId);
      if (!source) throw new Error("Source theme not found");
      return duplicateTheme(source, name);
    },
    [themes],
  );

  const updateToken = useCallback(
    (themeId: string, key: keyof ThemeTokens, value: string) => {
      const existing = customThemes.find((t) => t.id === themeId);
      if (!existing) return;
      const updated: ThemePreset = {
        ...existing,
        tokens: { ...existing.tokens, [key]: value },
      };
      const next = customThemes.map((t) => (t.id === themeId ? updated : t));
      setCustomThemes(next);
      saveCustomThemes(next);
      if (activeId === themeId) applyTheme(updated);
    },
    [activeId, customThemes],
  );

  const exportTheme = useCallback(
    (id: string) => {
      const theme = themes.find((t) => t.id === id);
      if (theme) downloadThemeJson(theme);
    },
    [themes],
  );

  const importTheme = useCallback(
    (json: string) => {
      const theme = parseThemeImport(json);
      const next = customThemes.filter((t) => t.id !== theme.id);
      next.push(theme);
      setCustomThemes(next);
      saveCustomThemes(next);
      setActiveId(theme.id);
      saveActiveThemeId(theme.id);
      applyTheme(theme);
      return theme;
    },
    [customThemes],
  );

  const value = useMemo(
    () => ({
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
    }),
    [
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
    ],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used within ThemeProvider");
  return ctx;
}

/** Editable token fields shown in the theme editor */
export const EDITABLE_TOKEN_GROUPS: { label: string; keys: (keyof ThemeTokens)[] }[] = [
  { label: "Surfaces", keys: ["bg", "bgElevated", "bgHover", "bgPanel", "bodyGlow"] },
  { label: "Borders & text", keys: ["border", "borderBright", "text", "textMuted", "textDim"] },
  { label: "Accent", keys: ["accent", "accentDim", "accentSoft", "accentGlow", "accentContrast"] },
  { label: "Status", keys: ["success", "warning", "danger", "ready", "review"] },
  { label: "Scrollbars", keys: ["scrollbarTrack", "scrollbarThumb", "scrollbarThumbHover"] },
];

export { THEME_TOKEN_KEYS };
