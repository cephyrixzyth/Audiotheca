import { getApiBase, getWsBase, isTauri } from "../platform";
import type {
  ArchivePeekResponse,
  DuplicateGroup,
  InvestigationItem,
  JobSnapshot,
  RestructureItem,
  RunListItem,
  RunSummary,
  SceneRenameItem,
} from "../types";

async function apiUrl(path: string): Promise<string> {
  const base = await getApiBase();
  return `${base}${path}`;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(await apiUrl(path));
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(await apiUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export function fetchRuns(): Promise<RunListItem[]> {
  return getJson("/runs");
}

export function fetchRun(stamp: string): Promise<RunSummary> {
  return getJson(`/runs/${stamp}`);
}

export function fetchBuckets(stamp: string): Promise<Record<string, number>> {
  return getJson(`/runs/${stamp}/buckets`);
}

export interface InvestigationFeedbackState {
  corrections: Array<Record<string, unknown>>;
  path_vendor_overrides: Record<string, string>;
  path_bucket_overrides: Record<string, string>;
  resolved_paths: string[];
  parent_links: Record<string, string>;
  custom_buckets: Record<string, string>;
  bucket_options: string[];
  correction_actions: string[];
  correction_reasons: string[];
}

export function fetchInvestigationFeedback(stamp: string): Promise<InvestigationFeedbackState> {
  return getJson(`/runs/${stamp}/investigation/feedback`);
}

export function correctInvestigation(
  stamp: string,
  payload: {
    path: string;
    action: string;
    value?: string;
    reason?: string;
    note?: string;
    item_name?: string;
    old_bucket?: string;
    keywords?: string[];
  },
): Promise<{ ok: boolean; state: InvestigationFeedbackState }> {
  return postJson(`/runs/${stamp}/investigation/correct`, payload);
}

export async function investigationFeedbackExportUrl(stamp: string): Promise<string> {
  return `${await apiUrl(`/runs/${stamp}/investigation/export`)}`;
}

export function fetchInvestigation(
  stamp: string,
  params: { bucket?: string; section?: string; q?: string; limit?: number; offset?: number },
): Promise<{ items: InvestigationItem[]; total: number }> {
  const qs = new URLSearchParams();
  if (params.bucket) qs.set("bucket", params.bucket);
  if (params.section) qs.set("section", params.section);
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));
  return getJson(`/runs/${stamp}/investigation?${qs}`);
}

export function fetchDuplicates(
  stamp: string,
  params: { confidence?: string; q?: string; limit?: number },
): Promise<{ groups: DuplicateGroup[]; total: number }> {
  const qs = new URLSearchParams();
  if (params.confidence) qs.set("confidence", params.confidence);
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  return getJson(`/runs/${stamp}/duplicates?${qs}`);
}

export function fetchRestructure(
  stamp: string,
  params: { status?: string; section?: string; q?: string; limit?: number },
): Promise<{ items: RestructureItem[]; total: number }> {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.section) qs.set("section", params.section);
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  return getJson(`/runs/${stamp}/restructure?${qs}`);
}

export function fetchSceneRenames(stamp: string): Promise<SceneRenameItem[]> {
  return getJson(`/runs/${stamp}/scene-renames`);
}

export function fetchArchivePeek(
  stamp: string,
  params: { verdict?: string; q?: string; limit?: number },
): Promise<ArchivePeekResponse> {
  const qs = new URLSearchParams();
  if (params.verdict) qs.set("verdict", params.verdict);
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  return getJson(`/runs/${stamp}/archive-peek?${qs}`);
}

export interface DuplicateRejection {
  dedup_key: string;
  paths: string[];
  reason: string;
  note?: string;
  created?: string;
}

export interface ManualDuplicateFinding {
  path_a: string;
  path_b: string;
  relationship?: string;
  note?: string;
  created?: string;
}

export function fetchDecisions(stamp: string): Promise<{
  decisions: Record<string, string>;
  keepers: Record<string, string>;
  rejections: DuplicateRejection[];
  manual_findings: ManualDuplicateFinding[];
  reject_reasons: string[];
  saved: boolean;
}> {
  return getJson(`/runs/${stamp}/decisions`);
}

export function saveDecisions(
  stamp: string,
  decisions: Record<string, string>,
): Promise<{ ok: boolean; count: number; path: string }> {
  return postJson(`/runs/${stamp}/decisions`, { decisions });
}

export function rejectDuplicateGroup(
  stamp: string,
  payload: {
    dedup_key: string;
    paths: string[];
    reason?: string;
    note?: string;
  },
): Promise<{ ok: boolean; dedup_key: string }> {
  return postJson(`/runs/${stamp}/duplicates/reject`, payload);
}

export function addManualDuplicate(
  stamp: string,
  payload: {
    path_a: string;
    path_b: string;
    relationship?: string;
    note?: string;
  },
): Promise<{ ok: boolean }> {
  return postJson(`/runs/${stamp}/duplicates/manual`, payload);
}

export function executeDuplicateStaging(
  stamp: string,
  payload: { dry_run?: boolean; root?: string },
): Promise<{
  ok: boolean;
  dry_run: boolean;
  staged: number;
  failed: number;
  results: Array<{
    dedup_key: string;
    path: string;
    ok: boolean;
    dry_run?: boolean;
    staged_to?: string;
    error?: string;
  }>;
  error?: string;
}> {
  return postJson(`/runs/${stamp}/duplicates/execute`, payload);
}

export async function downloadDecisionsUrl(stamp: string): Promise<string> {
  return `${await apiUrl(`/runs/${stamp}/decisions/download`)}`;
}

export async function feedbackExportUrl(
  stamp?: string,
  format: "csv" | "json" = "csv",
): Promise<string> {
  const qs = new URLSearchParams();
  if (stamp) qs.set("stamp", stamp);
  qs.set("format", format);
  return `${await apiUrl(`/feedback/export?${qs}`)}`;
}

export function startScan(params: {
  dry_run?: boolean;
  root?: string;
}): Promise<JobSnapshot> {
  return postJson("/jobs", params);
}

export function jobEventsUrl(jobId: string): string {
  return `${getWsBase()}/api/jobs/${jobId}/events`;
}

export async function openInExplorer(path: string): Promise<void> {
  if (isTauri()) {
    const { revealItemInDir } = await import("@tauri-apps/plugin-opener");
    await revealItemInDir(path);
    return;
  }
  await postJson("/explorer", { path });
}
