import type { CSSProperties } from "react";

const paths = {
  dashboard: "M3 4h11v8H3z M17 4h4v8h-4z M3 15h5v5H3z M11 15h10v5H11z",
  library: "M3 6v13 M7 4v15 M11 5v14 M16 6l4 12 M2 21h19",
  scan: "M4 9V4h5 M15 4h5v5 M20 15v5h-5 M9 20H4v-5 M6 12h12 M9 9v6 M15 10v4",
  review: "M4 4h12v14H4z M8 21h12V8 M7 9l2 2 4-4 M7 14h5",
  studio: "M3 7h4m5 0h9 M3 17h11m5 0h2 M7 4h4v6H7z M14 14h4v6h-4z",
  system: "M3 4h18v6H3z M3 14h18v6H3z M6 7h1 M6 17h1 M13 7h5 M13 17h5",
  help: "M3 5c3-1 6-1 9 1 3-2 6-2 9-1v14c-3-1-6-1-9 1-3-2-6-2-9-1z M12 6v14",
  search: "M16.4 16.4l4.3 4.3 M18 10.5a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0",
  arrow: "M5 12h14 M13 6l6 6-6 6",
  upRight: "M6 18 18 6 M7 6h11v11",
  route: "M4 5h16 M4 12h16 M4 19h16",
  close: "m5 5 14 14 M19 5 5 19",
  drive: "m3 14 3-9h12l3 9v5H3z M3 14h18 M16 17h2",
  chevron: "m9 6 6 6-6 6",
  folder: "M3 6h6l2 3h10v11H3z",
  history: "M3 11a9 9 0 1 1 2 7 M3 4v7h7 M12 7v6l4 2",
  waveform: "M2 11v2 M6 7v10 M10 3v18 M14 8v8 M18 5v14 M22 10v4",
  filter: "M3 6h18 M6 12h12 M9 18h6",
  compare: "M3 4h8v16H3z M14 4h7v16h-7z",
  palette: "M3 13a9 9 0 1 1 18-1c0 3-2 4-5 3-2-1-4 0-3 2 1 2-1 4-3 3-4-1-7-3-7-7 M7 10h.1 M11 7h.1 M16 8h.1",
} as const;

export type WorkspaceIconName = keyof typeof paths;
export function WorkspaceIcon({ name, size = 19, style }: { name: WorkspaceIconName; size?: number; style?: CSSProperties }) {
  return <svg aria-hidden="true" focusable="false" width={size} height={size} viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" style={style}>
    <path d={paths[name]} />
  </svg>;
}
