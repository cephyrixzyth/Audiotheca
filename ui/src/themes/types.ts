/** CSS design tokens applied to :root via JavaScript. */
export interface ThemeTokens {
  bg: string;
  bgElevated: string;
  bgHover: string;
  bgPanel: string;
  border: string;
  borderBright: string;
  text: string;
  textMuted: string;
  textDim: string;
  accent: string;
  accentDim: string;
  accentSoft: string;
  accentGlow: string;
  accentContrast: string;
  success: string;
  warning: string;
  danger: string;
  ready: string;
  review: string;
  scrollbarTrack: string;
  scrollbarThumb: string;
  scrollbarThumbHover: string;
  /** Radial gradient tint at top of viewport */
  bodyGlow: string;
  mono: string;
  sans: string;
}

export interface ThemePreset {
  id: string;
  name: string;
  description: string;
  tokens: ThemeTokens;
  builtIn?: boolean;
  artwork?: string;
}

export interface ThemeExportBundle {
  format: "audiotheca-theme";
  version: 1;
  theme: ThemePreset;
}

export const THEME_TOKEN_KEYS: (keyof ThemeTokens)[] = [
  "bg",
  "bgElevated",
  "bgHover",
  "bgPanel",
  "border",
  "borderBright",
  "text",
  "textMuted",
  "textDim",
  "accent",
  "accentDim",
  "accentSoft",
  "accentGlow",
  "accentContrast",
  "success",
  "warning",
  "danger",
  "ready",
  "review",
  "scrollbarTrack",
  "scrollbarThumb",
  "scrollbarThumbHover",
  "bodyGlow",
  "mono",
  "sans",
];
