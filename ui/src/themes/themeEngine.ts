import { BUILTIN_THEMES, DEFAULT_THEME_ID } from "./presets";
import type { ThemeExportBundle, ThemePreset, ThemeTokens } from "./types";
import { THEME_TOKEN_KEYS } from "./types";

export const ACTIVE_THEME_KEY = "audiotheca.theme.active.v1";
export const CUSTOM_THEMES_KEY = "audiotheca.theme.custom.v1";

const CSS_VAR_MAP: Record<keyof ThemeTokens, string> = {
  bg: "--bg",
  bgElevated: "--bg-elevated",
  bgHover: "--bg-hover",
  bgPanel: "--bg-panel",
  border: "--border",
  borderBright: "--border-bright",
  text: "--text",
  textMuted: "--text-muted",
  textDim: "--text-dim",
  accent: "--accent",
  accentDim: "--accent-dim",
  accentSoft: "--accent-soft",
  accentGlow: "--accent-glow",
  accentContrast: "--accent-contrast",
  success: "--success",
  warning: "--warning",
  danger: "--danger",
  ready: "--ready",
  review: "--review",
  scrollbarTrack: "--scrollbar-track",
  scrollbarThumb: "--scrollbar-thumb",
  scrollbarThumbHover: "--scrollbar-thumb-hover",
  bodyGlow: "--body-glow",
  mono: "--mono",
  sans: "--sans",
};

export function applyTheme(theme: ThemePreset): void {
  const root = document.documentElement;
  for (const key of THEME_TOKEN_KEYS) {
    root.style.setProperty(CSS_VAR_MAP[key], theme.tokens[key]);
  }
  root.dataset.theme = theme.id;
}

export function loadActiveThemeId(): string {
  try {
    return localStorage.getItem(ACTIVE_THEME_KEY) || DEFAULT_THEME_ID;
  } catch {
    return DEFAULT_THEME_ID;
  }
}

export function saveActiveThemeId(id: string): void {
  try {
    localStorage.setItem(ACTIVE_THEME_KEY, id);
  } catch {
    /* quota */
  }
}

export function loadCustomThemes(): ThemePreset[] {
  try {
    const raw = localStorage.getItem(CUSTOM_THEMES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Record<string, ThemePreset>;
    if (!parsed || typeof parsed !== "object") return [];
    return Object.values(parsed).filter((t) => t?.id && t?.tokens);
  } catch {
    return [];
  }
}

export function saveCustomThemes(themes: ThemePreset[]): void {
  const store: Record<string, ThemePreset> = {};
  for (const theme of themes) {
    store[theme.id] = { ...theme, builtIn: false };
  }
  try {
    localStorage.setItem(CUSTOM_THEMES_KEY, JSON.stringify(store));
  } catch {
    /* quota */
  }
}

export function getAllThemes(): ThemePreset[] {
  const custom = loadCustomThemes();
  const customIds = new Set(custom.map((t) => t.id));
  const builtins = BUILTIN_THEMES.filter((t) => !customIds.has(t.id));
  return [...builtins, ...custom];
}

export function resolveTheme(id: string): ThemePreset | null {
  return getAllThemes().find((t) => t.id === id) ?? BUILTIN_THEMES[0] ?? null;
}

export function slugifyThemeName(name: string): string {
  const base = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 40);
  return `custom-${base || "theme"}-${Date.now().toString(36)}`;
}

export function duplicateTheme(source: ThemePreset, name: string): ThemePreset {
  return {
    id: slugifyThemeName(name),
    name,
    description: source.description ? `Based on ${source.name}` : `Custom theme based on ${source.name}`,
    builtIn: false,
    tokens: { ...source.tokens },
  };
}

export function exportThemeBundle(theme: ThemePreset): ThemeExportBundle {
  return {
    format: "audiotheca-theme",
    version: 1,
    theme: { ...theme, builtIn: false },
  };
}

export function parseThemeImport(raw: string): ThemePreset {
  const parsed = JSON.parse(raw) as ThemeExportBundle | ThemePreset;
  if ("format" in parsed && parsed.format === "audiotheca-theme" && parsed.theme) {
    return normalizeImportedTheme(parsed.theme);
  }
  if ("tokens" in parsed && "name" in parsed) {
    return normalizeImportedTheme(parsed as ThemePreset);
  }
  throw new Error("Unrecognized theme file — expected audiotheca-theme JSON");
}

function normalizeImportedTheme(theme: ThemePreset): ThemePreset {
  if (!theme.name?.trim()) throw new Error("Theme name is required");
  const base = BUILTIN_THEMES[0]?.tokens;
  if (!base) throw new Error("No base theme available");
  const tokens = { ...base, ...theme.tokens } as ThemeTokens;
  for (const key of THEME_TOKEN_KEYS) {
    if (!tokens[key]) throw new Error(`Missing token: ${key}`);
  }
  const id = theme.id?.startsWith("custom-") ? theme.id : slugifyThemeName(theme.name);
  return {
    id,
    name: theme.name.trim(),
    description: theme.description?.trim() || "Imported theme",
    builtIn: false,
    tokens,
  };
}

export function downloadThemeJson(theme: ThemePreset): void {
  const blob = new Blob([JSON.stringify(exportThemeBundle(theme), null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `audiotheca-theme-${theme.id}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

/** Apply saved theme before React mounts to reduce flash. */
export function bootstrapTheme(): void {
  const theme = resolveTheme(loadActiveThemeId());
  if (theme) applyTheme(theme);
}
