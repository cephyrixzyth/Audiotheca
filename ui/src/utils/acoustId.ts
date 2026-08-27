export type AcoustIdLookupPayload = {
  ok?: boolean;
  skipped?: boolean;
  error?: unknown;
  results?: unknown;
};

type AcoustIdRecording = { title?: string; artists?: string[] };
type AcoustIdHit = { score?: number; recordings?: AcoustIdRecording[] };

export function formatAcoustIdResult(res: AcoustIdLookupPayload): string {
  if (res.skipped) {
    return typeof res.error === "string" ? res.error : "AcoustID lookup skipped";
  }
  if (res.ok === false) {
    return typeof res.error === "string" ? res.error : "AcoustID lookup failed";
  }
  const results = Array.isArray(res.results) ? res.results : [];
  const first = results[0] as AcoustIdHit | undefined;
  const recording = first?.recordings?.[0];
  if (!recording?.title) {
    return "No AcoustID match";
  }
  const artists = (recording.artists ?? []).filter(Boolean).join(", ");
  const score = typeof first?.score === "number" ? ` (${Math.round(first.score * 100)}%)` : "";
  return `${artists ? `${artists} — ` : ""}${recording.title}${score}`;
}
