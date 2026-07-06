/** UI-LOG spec code implementation status for Audiotheca frontend. */

export type UiSpecStatus = "done" | "partial" | "mvp";

export type UiSpecCapability = {
  code: string;
  title: string;
  status: UiSpecStatus;
  module: string;
  notes?: string;
};

export const UI_SPEC_CAPABILITIES: UiSpecCapability[] = [
  { code: "CANVAS-DRG", title: "Canvas drag layout", status: "done", module: "ui/src/components/ReorderableSections.tsx" },
  { code: "REFLOW-DYN", title: "Dynamic reflow", status: "done", module: "ui/src/components/DashboardHome.tsx" },
  { code: "AXIS-RESIZE", title: "Axis resize", status: "done", module: "ui/src/components/ReorderableSections.tsx" },
  { code: "CLR-CLUS", title: "Clear placeholders", status: "done", module: "ui/src/components/ReorderableSections.tsx" },
  { code: "LBL-STD", title: "Label standard", status: "done", module: "ui/src/utils/scanDisplay.ts" },
  { code: "ICON-BTN", title: "Icon buttons", status: "done", module: "ui/src/App.css" },
  { code: "HVR-HL", title: "Hover highlight", status: "done", module: "ui/src/App.css" },
  { code: "WYSIWYG-THM", title: "Theme studio", status: "done", module: "ui/src/components/ThemeSwitcher.tsx" },
  { code: "LOG-FIXED", title: "Fixed log height", status: "done", module: "ui/src/components/ScanPanel.tsx" },
  { code: "PHS-IND", title: "Phase indicators", status: "done", module: "ui/src/components/PhaseProgressBar.tsx" },
  { code: "LOG-FLTR", title: "Log level filter", status: "done", module: "ui/src/components/ScanPanel.tsx" },
  { code: "LOG-SRCH", title: "Log search", status: "done", module: "ui/src/components/ScanPanel.tsx" },
  { code: "ETA-HUM", title: "Human ETA", status: "done", module: "ui/src/utils/scanDisplay.ts" },
  { code: "MIX-MATX", title: "Output mixer matrix", status: "done", module: "ui/src/components/PreviewSessionPanel.tsx" },
  { code: "WAV-TRIM", title: "Waveform trimmer", status: "done", module: "ui/src/components/AudioPreviewStrip.tsx" },
  { code: "TMP-SYNC", title: "Tempo sync", status: "done", module: "ui/src/hooks/usePreviewSession.ts" },
  { code: "KEY-PITCH", title: "Key pitch shift", status: "done", module: "ui/src/hooks/usePreviewSession.ts" },
  { code: "AUTO-AUD", title: "Auto audition", status: "done", module: "ui/src/components/AudioPreviewStrip.tsx" },
  { code: "DRP-ZONE", title: "Drag-drop targets", status: "done", module: "ui/src/components/DropZoneOverlay.tsx" },
  { code: "BPRNT-SAVE", title: "Layout blueprint", status: "done", module: "ui/src/hooks/useLayoutPresets.ts" },
  { code: "LOG-DEDUP", title: "Log deduplication", status: "done", module: "ui/src/utils/scanDisplay.ts" },
  { code: "TAG-PROP", title: "Tag propagation", status: "done", module: "tag_prop.py" },
];

export function uiSpecByCode(code: string): UiSpecCapability | undefined {
  return UI_SPEC_CAPABILITIES.find((entry) => entry.code === code.toUpperCase());
}

export function uiSpecSummary(): Record<UiSpecStatus, number> {
  const counts: Record<UiSpecStatus, number> = { done: 0, partial: 0, mvp: 0 };
  for (const entry of UI_SPEC_CAPABILITIES) {
    counts[entry.status] += 1;
  }
  return counts;
}
