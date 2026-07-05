import { getApiBase, getWsBase, isTauri } from "../platform";
import type {
  ArchiveDiffResponse,
  ArchivePeekResponse,
  DuplicateGroup,
  InvestigationItem,
  CustomBucketResult,
  FeedbackApplyEstimate,
  JobHistoryEntry,
  JobProgress,
  JobSnapshot,
  ProgressEvent,
  ReferenceExtrasSummary,
  RestructureItem,
  RunListItem,
  RunSummary,
  SceneRenameItem,
  ScanAuditItem,
} from "../types";

async function apiUrl(path: string): Promise<string> {
  const base = await getApiBase();
  return `${base}${path}`;
}

let cachedToken: string | null = null;

async function ensureApiToken(): Promise<string> {
  if (cachedToken) return cachedToken;
  const res = await fetch(await apiUrl("/auth/token"));
  if (!res.ok) {
    throw new Error("Failed to obtain API token — is the API running on 127.0.0.1:8787?");
  }
  const data = (await res.json()) as { token: string };
  cachedToken = data.token;
  return cachedToken;
}

async function authHeaders(extra?: HeadersInit): Promise<HeadersInit> {
  const token = await ensureApiToken();
  return {
    ...extra,
    Authorization: `Bearer ${token}`,
  };
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(await apiUrl(path), { headers: await authHeaders() });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

async function putJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(await apiUrl(path), {
    method: "PUT",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(await apiUrl(path), {
    method: "POST",
    headers: await authHeaders({ "Content-Type": "application/json" }),
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

export interface VendorGap {
  prefix: string;
  suggested_company: string;
  count: number;
  keywords: string[];
  id_methods: Record<string, number>;
  sample_items: string[];
}

export interface InvestigationGroup {
  group_key: string;
  count: number;
  bucket: string;
  id_method: string;
  sample_items: string[];
  paths: string[];
  sections: Record<string, number>;
}

export function fetchVendorGaps(stamp: string, minCount = 1): Promise<{ gaps: VendorGap[]; total: number }> {
  return getJson(`/runs/${stamp}/vendor-gaps?min_count=${minCount}`);
}

export function bulkAddVendorGaps(
  stamp: string,
  prefixes: string[],
): Promise<{ ok: boolean; added: string[]; count: number }> {
  return postJson(`/runs/${stamp}/vendor-gaps/bulk-add`, { prefixes });
}

export function fetchInvestigationGroups(
  stamp: string,
  opts?: { bucket?: string; group_by?: string; q?: string; limit?: number },
): Promise<{ groups: InvestigationGroup[]; total: number; group_by: string }> {
  const qs = new URLSearchParams();
  if (opts?.bucket) qs.set("bucket", opts.bucket);
  if (opts?.group_by) qs.set("group_by", opts.group_by);
  if (opts?.q) qs.set("q", opts.q);
  if (opts?.limit) qs.set("limit", String(opts.limit));
  return getJson(`/runs/${stamp}/investigation/groups?${qs}`);
}

export function bulkCorrectInvestigation(
  stamp: string,
  payload: {
    paths: string[];
    action: string;
    value?: string;
    reason?: string;
    keywords?: string[];
  },
): Promise<{ ok: boolean; count: number; state: InvestigationFeedbackState }> {
  return postJson(`/runs/${stamp}/investigation/bulk-correct`, payload);
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

export function fetchRestructureFeedback(stamp: string): Promise<{
  stamp: string;
  path_dest_overrides: Record<string, string>;
  section_approvals: string[];
  active_approval_stamp: string;
  corrections: Array<Record<string, string>>;
}> {
  return getJson(`/runs/${stamp}/restructure/feedback`);
}

export function overrideRestructureDest(
  stamp: string,
  payload: {
    path: string;
    destination: string;
    item_name?: string;
    old_destination?: string;
  },
): Promise<{ ok: boolean; state: { path_dest_overrides: Record<string, string>; section_approvals: string[] } }> {
  return postJson(`/runs/${stamp}/restructure/override`, payload);
}

export function approveRestructureSection(
  stamp: string,
  section: string,
): Promise<{ ok: boolean; state: { path_dest_overrides: Record<string, string>; section_approvals: string[] } }> {
  return postJson(`/runs/${stamp}/restructure/approve-section`, { section });
}

export function executeRestructure(
  stamp: string,
  payload: { dry_run?: boolean; root?: string; confirm_live?: boolean },
): Promise<{
  ok: boolean;
  dry_run: boolean;
  moved: number;
  failed: number;
  approved_sections: string[];
  results: Array<Record<string, unknown>>;
  error?: string;
}> {
  return postJson(`/runs/${stamp}/restructure/execute`, payload);
}

export function fetchSceneRenames(stamp: string): Promise<SceneRenameItem[]> {
  return getJson(`/runs/${stamp}/scene-renames`);
}

export function fetchSceneFeedback(stamp: string): Promise<{
  approved_renames: string[];
  rejected_paths: Record<string, string>;
  name_overrides: Record<string, string>;
  missing_part01: Record<string, string>;
  reject_reasons: string[];
}> {
  return getJson(`/runs/${stamp}/scene-renames/feedback`);
}

export function approveSceneRename(
  stamp: string,
  payload: { source_path: string; scene_id?: string },
): Promise<{ ok: boolean; state: { approved_renames: string[] } }> {
  return postJson(`/runs/${stamp}/scene-renames/approve`, payload);
}

export function rejectSceneRename(
  stamp: string,
  payload: { source_path: string; scene_id?: string; reason?: string; note?: string },
): Promise<{ ok: boolean }> {
  return postJson(`/runs/${stamp}/scene-renames/reject`, payload);
}

export function overrideSceneName(
  stamp: string,
  payload: { source_path: string; proposed_name: string; scene_id?: string; old_name?: string },
): Promise<{ ok: boolean; state: { name_overrides: Record<string, string> } }> {
  return postJson(`/runs/${stamp}/scene-renames/override`, payload);
}

export function flagSceneMissingPart01(
  stamp: string,
  payload: { source_path: string; scene_id?: string },
): Promise<{ ok: boolean }> {
  return postJson(`/runs/${stamp}/scene-renames/missing-part01`, payload);
}

export function executeSceneRenames(
  stamp: string,
  payload: { dry_run?: boolean; confirm_live?: boolean },
): Promise<{
  ok: boolean;
  dry_run: boolean;
  renamed: number;
  failed: number;
  results: Array<Record<string, unknown>>;
  error?: string;
}> {
  return postJson(`/runs/${stamp}/scene-renames/execute`, payload);
}

export function fetchArchiveFeedback(stamp: string): Promise<{
  rejected_archives: Record<string, string>;
  confirmed_deletes: Record<string, string>;
  keeper_choice: Record<string, string>;
  reject_reasons: string[];
}> {
  return getJson(`/runs/${stamp}/archive-peek/feedback`);
}

export function rejectArchiveVerdict(
  stamp: string,
  payload: {
    archive_path: string;
    archive_name?: string;
    item_name?: string;
    reason?: string;
    note?: string;
  },
): Promise<{ ok: boolean }> {
  return postJson(`/runs/${stamp}/archive-peek/reject`, payload);
}

export function confirmArchiveDelete(
  stamp: string,
  payload: { archive_path: string; archive_name?: string; item_name?: string; note?: string },
): Promise<{ ok: boolean }> {
  return postJson(`/runs/${stamp}/archive-peek/confirm`, payload);
}

export function setArchiveKeeper(
  stamp: string,
  payload: { archive_path: string; keeper: "archive" | "folder"; archive_name?: string; item_name?: string },
): Promise<{ ok: boolean }> {
  return postJson(`/runs/${stamp}/archive-peek/keeper`, payload);
}

export function executeArchiveStaging(
  stamp: string,
  payload: { dry_run?: boolean; root?: string; confirm_live?: boolean },
): Promise<{
  ok: boolean;
  dry_run: boolean;
  staged: number;
  failed: number;
  results: Array<Record<string, unknown>>;
  error?: string;
}> {
  return postJson(`/runs/${stamp}/archive-peek/execute`, payload);
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

export function fetchArchiveDiff(
  stamp: string,
  params: { archive_path: string; folder_path: string; limit?: number },
): Promise<ArchiveDiffResponse> {
  const qs = new URLSearchParams({
    archive_path: params.archive_path,
    folder_path: params.folder_path,
  });
  if (params.limit) qs.set("limit", String(params.limit));
  return getJson(`/runs/${stamp}/archive-diff?${qs}`);
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
  payload: { dry_run?: boolean; root?: string; confirm_live?: boolean },
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
  module: "duplicates" | "investigation" | "all" = "duplicates",
): Promise<string> {
  const qs = new URLSearchParams();
  if (stamp) qs.set("stamp", stamp);
  qs.set("format", format);
  qs.set("module", module);
  return `${await apiUrl(`/feedback/export?${qs}`)}`;
}

export async function unifiedFeedbackExportUrl(stamp?: string): Promise<string> {
  return feedbackExportUrl(stamp, "csv", "all");
}

export function fetchFeedbackSummary(stamp?: string): Promise<Record<string, number>> {
  const qs = stamp ? `?stamp=${encodeURIComponent(stamp)}` : "";
  return getJson(`/feedback/summary${qs}`);
}

export function fetchVendors(): Promise<{
  known: string[];
  user_added: Array<{ company: string; keywords: string[]; category?: string }>;
}> {
  return getJson("/vendors");
}

export function addVendor(payload: {
  company: string;
  keywords: string[];
  category?: string;
}): Promise<{ ok: boolean; vendor: { company: string; keywords: string[] } }> {
  return postJson("/vendors", payload);
}

export function testVendorKeyword(
  keyword: string,
  sample: string,
): Promise<{ keyword: string; matches: boolean; match_span?: string; reason: string }> {
  return postJson("/vendors/test", { keyword, sample });
}

export interface HarvestCandidate {
  harvest_id: string;
  company: string;
  keywords: string[];
  category: string;
  source_url: string;
  source_label: string;
  confidence: string;
  notes: string;
  status: string;
  already_known: boolean;
}

export interface HarvestSourcePreset {
  id: string;
  label: string;
  urls: string[];
  default_category: string;
  notes?: string;
}

export function fetchHarvestSources(): Promise<{
  presets: HarvestSourcePreset[];
  categories: string[];
  default_urls: string[];
}> {
  return getJson("/vendors/harvest/sources");
}

export function fetchHarvestCandidates(includeKnown = true): Promise<{
  pending: HarvestCandidate[];
  total_pending: number;
  last_run: Record<string, unknown> | null;
  updated: string;
}> {
  return getJson(`/vendors/harvest/candidates?include_known=${includeKnown ? "true" : "false"}`);
}

export function runVendorHarvest(params: {
  urls?: string[];
  preset_id?: string;
  category?: string;
  include_known?: boolean;
}): Promise<{ ok: boolean; added: number; total_pending: number; results: Array<Record<string, unknown>> }> {
  return postJson("/vendors/harvest", params);
}

export function approveHarvestCandidates(
  harvestIds: string[],
): Promise<{ ok: boolean; count: number }> {
  return postJson("/vendors/harvest/approve", { harvest_ids: harvestIds });
}

export function rejectHarvestCandidates(
  harvestIds: string[],
): Promise<{ ok: boolean; rejected: number }> {
  return postJson("/vendors/harvest/reject", { harvest_ids: harvestIds });
}

export function vendorResearchExportUrl(includeKnown = false): string {
  return `/api/vendors/harvest/export?include_known=${includeKnown ? "true" : "false"}&status=pending`;
}

export function fetchJobs(): Promise<JobSnapshot[]> {
  return getJson("/jobs");
}

export function fetchJob(jobId: string): Promise<JobSnapshot> {
  return getJson(`/jobs/${jobId}`);
}

export function fetchJobEvents(
  jobId: string,
  after = 0,
): Promise<{ events: ProgressEvent[]; total: number; after: number }> {
  return getJson(`/jobs/${jobId}/events?after=${after}`);
}

export function fetchJobProgress(jobId: string): Promise<JobProgress> {
  return getJson(`/jobs/${jobId}/progress`);
}

export function fetchJobHistory(limit = 50): Promise<{ jobs: JobHistoryEntry[] }> {
  return getJson(`/jobs/history?limit=${limit}`);
}

export function fetchFeedbackEstimate(stamp?: string): Promise<FeedbackApplyEstimate> {
  const q = stamp ? `?stamp=${encodeURIComponent(stamp)}` : "";
  return getJson(`/feedback/estimate${q}`);
}

export function fetchReferenceExtras(
  stamp: string,
  roots: string[],
): Promise<ReferenceExtrasSummary> {
  const rootsParam = roots.map(encodeURIComponent).join(",");
  return getJson(`/runs/${stamp}/duplicates/reference-extras?roots=${rootsParam}`);
}

export function defineCustomBucket(params: {
  name: string;
  description?: string;
}): Promise<CustomBucketResult> {
  return postJson("/feedback/custom-buckets", params);
}

export function startScan(params: {
  dry_run?: boolean;
  root?: string;
  scan_options?: {
    pause_between_phases?: boolean;
    skip_phases?: string[];
    staging_root?: string;
    extra_scan_roots?: string[];
    target_paths?: string[];
    invalidate_cache_paths?: string[];
    verbose_log?: boolean;
  };
}): Promise<JobSnapshot> {
  return postJson("/jobs", params);
}

export function controlScanJob(
  jobId: string,
  action: "pause" | "stop" | "continue",
): Promise<JobSnapshot> {
  return postJson(`/jobs/${jobId}/control`, { action });
}

export function fetchScanOptions(): Promise<{
  skippable_phases: string[];
  phase_descriptions: Record<string, string>;
}> {
  return getJson("/scan/options");
}

export function fetchSystemMetrics(root?: string): Promise<{
  cpu_percent?: number;
  ram_total_gb?: number;
  ram_used_gb?: number;
  ram_used_pct?: number;
  disk_free_gb?: number;
  disk_used_pct?: number;
  disk_free_pct?: number;
  network_latency_ms?: number;
  psutil?: boolean;
}> {
  const qs = root ? `?root=${encodeURIComponent(root)}` : "";
  return getJson(`/system/metrics${qs}`);
}

export function fetchDualSystemMetrics(root?: string): Promise<{
  host?: Record<string, unknown>;
  remote?: Record<string, unknown> | null;
  dual?: boolean;
}> {
  const qs = root ? `?root=${encodeURIComponent(root)}` : "";
  return getJson(`/system/metrics/dual${qs}`);
}

export function fetchSystemProcesses(): Promise<Record<string, unknown>> {
  return getJson("/system/processes");
}

export function hardResetSystem(body: {
  kill_orphan_engines?: boolean;
  kill_api_ports?: boolean;
  keep_current_api?: boolean;
  clear_lock?: boolean;
  clear_artifacts?: boolean;
}): Promise<Record<string, unknown>> {
  return postJson("/system/hard-reset", body);
}

export function fetchSessionLogs(): Promise<
  { id: string; kind: string; size_bytes: number; modified_at?: number }[]
> {
  return getJson("/system/session-logs");
}

export function fetchSessionLog(
  logId: string,
  tail = 2000,
): Promise<{
  id: string;
  kind: string;
  lines: string[];
  events: ProgressEvent[];
  truncated?: boolean;
  total_lines?: number;
}> {
  return getJson(`/system/session-logs/${encodeURIComponent(logId)}?tail=${tail}`);
}

export function fetchScanAudit(
  stamp: string,
  params: { status?: string; flags?: string; q?: string; limit?: number },
): Promise<{ items: ScanAuditItem[]; total: number }> {
  const qs = new URLSearchParams();
  if (params.status) qs.set("status", params.status);
  if (params.flags) qs.set("flags", params.flags);
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  return getJson(`/runs/${stamp}/audit?${qs}`);
}

export function fetchSkippedItems(
  stamp: string,
  params: { reason?: string; q?: string; limit?: number; offset?: number },
): Promise<{ items: import("../types").SkippedItem[]; total: number; counts: Record<string, number> }> {
  const qs = new URLSearchParams();
  if (params.reason) qs.set("reason", params.reason);
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));
  return getJson(`/runs/${stamp}/skipped?${qs}`);
}

export function fetchScanFailures(
  stamp: string,
  params: { q?: string; limit?: number } = {},
): Promise<{ items: import("../types").ScanFailureItem[]; total: number }> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  return getJson(`/runs/${stamp}/scan-failures?${qs}`);
}

export function fetchNestedIssues(
  stamp: string,
  params: { issue_type?: string; q?: string; limit?: number } = {},
): Promise<{ items: import("../types").NestedIssueItem[]; total: number }> {
  const qs = new URLSearchParams();
  if (params.issue_type) qs.set("issue_type", params.issue_type);
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  return getJson(`/runs/${stamp}/nested-issues?${qs}`);
}

export function fetchCoexistence(
  stamp: string,
  params: { issue_type?: string; q?: string; limit?: number } = {},
): Promise<{ items: import("../types").CoexistenceItem[]; total: number }> {
  const qs = new URLSearchParams();
  if (params.issue_type) qs.set("issue_type", params.issue_type);
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  return getJson(`/runs/${stamp}/coexistence?${qs}`);
}

export function fetchInventory(
  stamp: string,
  params: { vendor?: string; q?: string; limit?: number } = {},
): Promise<{ items: import("../types").InventoryItem[]; total: number }> {
  const qs = new URLSearchParams();
  if (params.vendor) qs.set("vendor", params.vendor);
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  return getJson(`/runs/${stamp}/inventory?${qs}`);
}

export function fetchCacheHits(
  stamp: string,
  params: { q?: string; limit?: number } = {},
): Promise<{ items: import("../types").CacheHitItem[]; total: number }> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  return getJson(`/runs/${stamp}/cache-hits?${qs}`);
}

export function fetchCoverageGaps(
  stamp: string,
  params: { reason?: string; q?: string; limit?: number } = {},
): Promise<{ items: import("../types").CoverageGapItem[]; total: number }> {
  const qs = new URLSearchParams();
  if (params.reason) qs.set("reason", params.reason);
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  return getJson(`/runs/${stamp}/coverage-gaps?${qs}`);
}

export function fetchProbeTruncations(
  stamp: string,
  params: { kind?: string; q?: string; limit?: number } = {},
): Promise<{ items: import("../types").ProbeTruncationItem[]; total: number }> {
  const qs = new URLSearchParams();
  if (params.kind) qs.set("kind", params.kind);
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  return getJson(`/runs/${stamp}/probe-truncations?${qs}`);
}

export function fetchSkipImpact(
  stamp: string,
): Promise<{ phases: import("../types").SkipPhaseImpact[]; feedback_skipped: unknown[] }> {
  return getJson(`/runs/${stamp}/skip-impact`);
}

export function fetchDeepIdentify(
  stamp: string,
  params: { method?: string; q?: string; limit?: number } = {},
): Promise<{ items: import("../types").DeepIdentifyItem[]; total: number }> {
  const qs = new URLSearchParams();
  if (params.method) qs.set("method", params.method);
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  return getJson(`/runs/${stamp}/deep-identify?${qs}`);
}

export function fetchVerification(
  stamp: string,
  params: { check?: string; severity?: string; q?: string; limit?: number } = {},
): Promise<{
  items: import("../types").VerificationFinding[];
  total: number;
  scorecard: import("../types").QualityScorecard;
}> {
  const qs = new URLSearchParams();
  if (params.check) qs.set("check", params.check);
  if (params.severity) qs.set("severity", params.severity);
  if (params.q) qs.set("q", params.q);
  if (params.limit) qs.set("limit", String(params.limit));
  return getJson(`/runs/${stamp}/verification?${qs}`);
}

export function compareRuns(
  stampA: string,
  stampB: string,
): Promise<import("../types").RunComparison> {
  return getJson(`/runs/compare?stamp_a=${encodeURIComponent(stampA)}&stamp_b=${encodeURIComponent(stampB)}`);
}

export function invalidateCache(paths: string[]): Promise<{ ok: boolean; removed: string[] }> {
  return postJson("/cache/invalidate", { paths });
}

export function rescanPaths(
  stamp: string,
  payload: { paths: string[]; invalidate_cache?: boolean; dry_run?: boolean },
): Promise<{ ok: boolean; job: JobSnapshot }> {
  return postJson(`/runs/${stamp}/skipped/rescan`, payload);
}

export function queueSkippedInvestigation(
  stamp: string,
  payload: { paths: string[]; bucket?: string },
): Promise<{ ok: boolean; applied: number }> {
  return postJson(`/runs/${stamp}/skipped/queue-investigation`, payload);
}

export interface UnderscoreVendorRow {
  name: string;
  path: string;
  section: string;
  source: string;
  whitelisted: boolean;
}

export function fetchUnderscoreVendors(
  stamp?: string,
): Promise<{ items: UnderscoreVendorRow[]; total: number; whitelisted_count: number }> {
  const qs = stamp ? `?stamp=${encodeURIComponent(stamp)}` : "";
  return getJson(`/underscore-vendors${qs}`);
}

export function addUnderscoreVendors(payload: {
  folders?: string[];
  paths?: string[];
}): Promise<{ ok: boolean; added_folders: string[]; added_paths: string[] }> {
  return postJson("/underscore-vendors", payload);
}

export function removeUnderscoreVendors(payload: {
  folders?: string[];
  paths?: string[];
}): Promise<{ ok: boolean; removed_folders: string[]; removed_paths: string[] }> {
  return postJson("/underscore-vendors/remove", payload);
}

export function rescanUnderscorePaths(
  stamp: string,
  payload: { paths: string[]; invalidate_cache?: boolean; dry_run?: boolean; full_library?: boolean },
): Promise<{ ok: boolean; job: JobSnapshot }> {
  return postJson(`/runs/${stamp}/underscore/rescan`, payload);
}

export function seedKnownUnderscoreVendors(
  folders?: string[],
): Promise<{ ok: boolean; added_folders: string[]; total_folders?: number }> {
  return postJson("/underscore-vendors/seed-known", { folders: folders || [] });
}

export function bulkWhitelistAllUnderscore(
  stamp: string,
  payload?: { dry_run?: boolean; invalidate_cache?: boolean },
): Promise<{ ok: boolean; job: JobSnapshot; count: number; paths: string[] }> {
  return postJson(`/runs/${stamp}/underscore/bulk-whitelist-all`, payload || {});
}

export function fetchSpaceRecoverySummary(stamp: string): Promise<Record<string, unknown>> {
  return getJson(`/runs/${stamp}/space-recovery/summary`);
}

export async function spaceRecoveryReportUrl(filename: string): Promise<string> {
  const token = await ensureApiToken();
  return `${await apiUrl(`/space-recovery/reports/${encodeURIComponent(filename)}`)}?token=${encodeURIComponent(token)}`;
}

export async function jobEventsUrl(jobId: string): Promise<string> {
  const token = await ensureApiToken();
  return `${await getWsBase()}/api/jobs/${jobId}/events?token=${encodeURIComponent(token)}`;
}

export async function openInExplorer(path: string): Promise<void> {
  if (isTauri()) {
    const { revealItemInDir } = await import("@tauri-apps/plugin-opener");
    await revealItemInDir(path);
    return;
  }
  await postJson("/explorer", { path });
}

export interface BrowseEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number | null;
  vendor?: string;
  status?: string;
  id_method?: string;
  investigation_bucket?: string;
}

export async function browseDirectory(path: string = ""): Promise<{
  path: string;
  parent: string | null;
  entries: BrowseEntry[];
}> {
  const qs = path ? `?path=${encodeURIComponent(path)}` : "";
  return getJson(`/browse${qs}`);
}

export async function browseDirectoryEnriched(
  path: string = "",
  stamp: string = "",
): Promise<{
  path: string;
  parent: string | null;
  entries: BrowseEntry[];
}> {
  const qs = new URLSearchParams();
  if (path) qs.set("path", path);
  if (stamp) qs.set("stamp", stamp);
  const query = qs.toString();
  return getJson(`/browse/enriched${query ? `?${query}` : ""}`);
}

export async function browseTreeChildren(path: string = ""): Promise<{
  path: string;
  parent: string | null;
  children: BrowseEntry[];
}> {
  const qs = path ? `?path=${encodeURIComponent(path)}` : "";
  return getJson(`/browse/tree${qs}`);
}

export async function listArchiveContents(path: string, limit = 200): Promise<{
  path: string;
  archive_tool_available: boolean;
  error: string | null;
  entries: string[];
  count: number;
}> {
  const qs = new URLSearchParams({ path, limit: String(limit) });
  return getJson(`/archive/list?${qs}`);
}

export function startSecurityScan(params: {
  root: string;
  use_clamav?: boolean;
  max_files?: number;
}): Promise<{ ok: boolean; findings: import("../types").MalwareFinding[]; total: number; report: string }> {
  return postJson("/security/scan", params);
}

export function fetchLatestSecurityScan(): Promise<{
  report: string | null;
  root?: string;
  scanned_at?: string;
  findings: import("../types").MalwareFinding[];
  total: number;
}> {
  return getJson("/security/latest");
}

export function lookupSecurityHash(hash: string): Promise<{ hash: string; urls: Record<string, string> }> {
  return getJson(`/security/lookup?hash=${encodeURIComponent(hash)}`);
}

export function quarantineSecurityThreats(params: {
  root: string;
  paths: string[];
  confirm_live: boolean;
}): Promise<{ ok: boolean; results: { path: string; status: string; destination?: string; detail?: string }[] }> {
  return postJson("/security/quarantine", params);
}

export function deleteSecurityThreats(params: {
  paths: string[];
  confirm_live: boolean;
}): Promise<{ ok: boolean; results: { path: string; status: string; detail?: string }[] }> {
  return postJson("/security/delete", params);
}

export function fetchEnvironment(): Promise<import("../types").EnvironmentPayload> {
  return getJson("/environment");
}

export function fetchHealth(): Promise<{
  status: string;
  api_version?: string;
  ui_version?: string;
  engine_version: string;
  archive_tool: string | null;
  environment?: import("../types").EnvironmentSummary;
  warnings: string[];
}> {
  return getJson("/health");
}

export function repairEnvironment(params: {
  action: string;
  dry_run?: boolean;
  confirm_live?: boolean;
}): Promise<Record<string, unknown>> {
  return postJson("/environment/repair", params);
}

export function repairAllEnvironment(params: {
  dry_run?: boolean;
  confirm_live?: boolean;
}): Promise<Record<string, unknown>> {
  return postJson("/environment/repair-all", params);
}

export function installEnvironmentDependencies(params: {
  dry_run?: boolean;
  confirm_live?: boolean;
}): Promise<{
  ok: boolean;
  dry_run?: boolean;
  attempted?: number;
  succeeded?: number;
  log?: string[];
  manual_hints?: string[];
  results?: Record<string, unknown>[];
}> {
  return postJson("/environment/install", params);
}

export function fetchLibraryRoots(): Promise<{ roots: string[]; configured?: boolean }> {
  return getJson("/security/library-roots");
}

export function saveLibraryRoots(roots: string[]): Promise<{ ok: boolean; roots: string[]; configured: boolean }> {
  return putJson("/security/library-roots", { roots });
}

export function exportEnvironmentManifest(): Promise<Record<string, unknown>> {
  return postJson("/environment/manifest/export", {});
}

export function importEnvironmentManifest(params: {
  manifest: Record<string, unknown>;
  dry_run?: boolean;
  confirm_live?: boolean;
}): Promise<Record<string, unknown>> {
  return postJson("/environment/manifest/import", params);
}

export function fetchAiLookupCache(limit = 100): Promise<{ items: import("../types").AiLookupResult[] }> {
  return getJson(`/ai/lookup/cache?limit=${limit}`);
}

export function fetchAiLookupStatus(): Promise<import("../types").AiLookupStatus> {
  return getJson("/ai/lookup/status");
}

export function queryAiLookup(body: {
  path: string;
  root?: string;
  section?: string;
}): Promise<{ result: import("../types").AiLookupResult }> {
  return postJson("/ai/lookup/query", body);
}

export function confirmAiLookup(body: {
  lookup_id: string;
  accepted: boolean;
  reasoning?: string;
}): Promise<{ result: import("../types").AiLookupResult }> {
  return postJson("/ai/lookup/confirm", body);
}

export interface InstallationRecord {
  install_id: string;
  product_key: string;
  display_name: string;
  install_path: string;
  tags: string[];
  notes_html: string;
  dependencies: Array<{ name: string; kind?: string; required?: boolean; notes?: string }>;
  local_version: string;
  manifest_version: string;
  update_status: string;
  product_url?: string;
  docs_url?: string;
}

export function fetchInstallations(): Promise<{ installs: InstallationRecord[]; default_tags: string[] }> {
  return getJson("/installations");
}

export function upsertInstallation(installId: string, body: Partial<InstallationRecord>): Promise<InstallationRecord> {
  return putJson(`/installations/${encodeURIComponent(installId)}`, body);
}

export function checkInstallationVersion(installId: string): Promise<{
  check: {
    product_key: string;
    install_path: string;
    exe_path: string | null;
    local_version: string;
    manifest_version: string;
    update_status: string;
  };
  install: InstallationRecord;
}> {
  return getJson(`/installations/${encodeURIComponent(installId)}/version-check`);
}

export function refreshVersionManifest(body: {
  product_key: string;
  display_name?: string;
  expected_version?: string;
  install_path?: string;
}): Promise<{ ok: boolean; entry: { expected_version?: string; display_name?: string } }> {
  return postJson("/installations/manifest/refresh", body);
}

export function syncVersionManifestCatalog(url: string): Promise<{ ok: boolean; merged: number; url: string }> {
  return postJson("/installations/manifest/sync", { url });
}

export function fetchInstallationPresets(): Promise<{ presets: Array<{ name: string; snapshot: Record<string, unknown> }> }> {
  return getJson("/installations/presets/list");
}

export function saveInstallationPreset(name: string, snapshot: Record<string, unknown>): Promise<{ name: string; snapshot: Record<string, unknown> }> {
  return postJson("/installations/presets", { name, snapshot });
}

export function runReferenceDedupeEngine(body: {
  reference_roots: string[];
  scan_roots: string[];
}): Promise<{
  reference_keys: number;
  extra_count: number;
  extra_groups: number;
  extras: Array<{ dedup_key: string; full_path: string; reference_matches: string[] }>;
}> {
  return postJson("/reference-dedupe/engine-scan", body);
}
