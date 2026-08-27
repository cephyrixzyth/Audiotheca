export interface RunListItem {
  stamp: string;
  engine_version: string | null;
  dry_run: boolean | null;
  scanned: number | null;
  investigation: number | null;
}

export interface RunSummary {
  stamp: string;
  engine_version: string;
  dry_run: boolean;
  scanned: number;
  cache_hits: number;
  routes_planned: number;
  investigation: number;
  investigation_buckets: Record<string, number>;
  nested_issues: number;
  coexistence_findings: number;
  scene_renames_planned: number;
  duplicate_groups: number;
  duplicate_high: number;
  duplicate_medium: number;
  ready_count: number | null;
  needs_review_count: number | null;
  merge_count: number | null;
  coverage_gaps?: number;
  cache_hit_paths?: number;
  probe_truncations?: number;
  feedback_skipped?: number;
    scan_failures?: number;
  route_ready_pct?: number | null;
  identification_pct?: number | null;
  one_action_pct?: number | null;
}

export interface InvestigationItem {
  section: string;
  item_name: string;
  current_path: string;
  investigation_bucket: string;
  reason: string;
  id_method: string;
  id_confidence: string;
  fingerprint?: string;
  size_mb: number | null;
  planned_destination: string;
}

export interface DuplicateMember {
  index: number;
  item_name: string;
  section: string;
  full_path: string;
  vendor: string;
  size_mb: number | null;
  recommendation: string;
}

export interface DuplicateGroup {
  dedup_key: string;
  confidence: string;
  group_kind: string;
  name_similarity_pct: number | null;
  size_ratio: number | null;
  content_check: string;
  members: DuplicateMember[];
}

export interface RestructureItem {
  section: string;
  item_name: string;
  current_path: string;
  planned_destination: string;
  vendor: string;
  id_method: string;
  id_confidence: string;
  size_mb: number | null;
  status: string;
}

export interface SceneRenameItem {
  scene_id: string;
  source_path: string;
  proposed_name: string;
  destination_path: string;
  multipart_diagnosis: string;
  multipart_diagnosis_label?: string;
}

export interface ArchivePeekItem {
  section: string;
  item_name: string;
  item_path: string;
  archive_name: string;
  archive_path: string;
  extracted_folder: string;
  name_similarity: number | null;
  archive_size_mb: number | null;
  verdict: string;
  inferred_product: string;
}

export interface ArchiveDeleteItem {
  section: string;
  item_name: string;
  archive_path: string;
  archive_size_mb: number | null;
  multipart_group: string;
}

export interface ArchivePeekResponse {
  items: ArchivePeekItem[];
  total: number;
  verdict_counts: Record<string, number>;
  delete_candidates: ArchiveDeleteItem[];
  delete_candidate_files: number;
  delete_candidate_mb: number;
}

export interface ArchiveDiffMatch {
  name: string;
  size_archive: number | null;
  size_disk: number | null;
}

export interface ArchiveDiffEntry {
  name: string;
  relative_path?: string;
  path?: string;
  is_dir: boolean;
  size: number | null;
}

export interface ArchiveDiffResponse {
  stamp: string;
  archive_path: string;
  folder_path: string;
  archive_tool_available?: boolean;
  archive_list_count?: number;
  archive_error?: string | null;
  archive_entries: ArchiveDiffEntry[];
  folder_entries: ArchiveDiffEntry[];
  only_in_archive: string[];
  only_on_disk: string[];
  matched: ArchiveDiffMatch[];
  verdict_hint: string;
}

export interface ScanAuditItem {
  section: string;
  item_name: string;
  current_path: string;
  vendor: string;
  id_method: string;
  id_confidence: string;
  fingerprint: string;
  version_key: string;
  size_mb: number | null;
  status: string;
  investigation_bucket: string;
  planned_destination: string;
  flags: string;
}

export interface SystemMetrics {
  type?: string;
  disk_path?: string;
  scan_root?: string;
  cpu_percent?: number;
  cpu_count?: number;
  ram_total_gb?: number;
  ram_used_gb?: number;
  ram_available_gb?: number;
  ram_used_pct?: number;
  disk_total_gb?: number;
  disk_used_gb?: number;
  disk_free_gb?: number;
  disk_used_pct?: number;
  disk_free_pct?: number;
  disk_read_mb?: number;
  disk_write_mb?: number;
  disk_io_busy_pct?: number;
  network_path?: boolean;
  network_host?: string;
  network_latency_ms?: number;
  volumes?: Array<{
    device: string;
    mount: string;
    fstype: string;
    total_gb: number;
    free_gb: number;
    free_pct: number;
  }>;
  bottleneck_hints?: string[];
  psutil?: boolean;
}

export interface AiLookupArchetype {
  category: string;
  confidence: number;
  reasoning?: string;
}

export interface AiLookupDeveloper {
  vendor?: string | null;
  product_line?: string | null;
  aliases?: string[];
  confidence: number;
  reasoning?: string;
}

export interface AiLookupRelease {
  release_group?: string | null;
  release_date?: string | null;
  source_url?: string | null;
  confidence: number;
  reasoning?: string;
}

export interface AiLookupResult {
  lookup_id: string;
  content_hash: string;
  status: string;
  confidence: number;
  reasoning: string;
  vendor?: string | null;
  product?: string | null;
  archetype?: AiLookupArchetype | null;
  developer?: AiLookupDeveloper | null;
  release?: AiLookupRelease | null;
  source_url?: string | null;
  relative_path?: string | null;
  provider?: string;
  pending_verification?: boolean;
}

export interface AiLookupStatus {
  active: AiLookupResult[];
  token_usage: { used: number; limit: number };
}

export interface ScanOptionsInfo {
  skippable_phases: string[];
  phase_descriptions: Record<string, string>;
}

export interface JobSnapshot {
  job_id: string;
  status: string;
  dry_run: boolean;
  root: string;
  stamp: string | null;
  exit_code: number | null;
  error: string | null;
  current_phase?: string | null;
  scan_options?: Record<string, unknown>;
}

export interface JobProgress {
  job_id: string;
  status: string;
  current_phase: string | null;
  last_event_ts: string | null;
  last_progress: ProgressEvent | null;
  event_count: number;
  stalled: boolean;
}

export interface JobHistoryEntry {
  job_id: string;
  status: string;
  dry_run: number;
  root: string | null;
  stamp: string | null;
  current_phase: string | null;
  exit_code: number | null;
  error: string | null;
  event_count: number;
  started_at: number;
  finished_at: number | null;
  updated_at: string;
}

export interface FeedbackApplyEstimate {
  stamp: string | null;
  pending_feedback: Record<string, number>;
  estimated_delta: Record<string, number>;
  note: string;
}

export interface ReferenceExtraItem {
  dedup_key: string;
  full_path: string;
  group_kind: string;
  recommendation: string;
  confidence: string;
  item_name: string;
}

export interface ReferenceExtrasSummary {
  stamp: string;
  reference_roots: string[];
  reference_extra_rows: number;
  reference_extra_groups: number;
  items: ReferenceExtraItem[];
}

export interface CustomBucketResult {
  ok: boolean;
  name: string;
  description: string;
}

export interface ProgressEvent {
  type: string;
  ts?: string;
  phase?: string;
  done?: number;
  total?: number;
  unit?: string;
  pct?: number;
  detail?: string;
  note?: string;
  elapsed_s?: number;
  eta_s?: number | null;
  /** phase_progress re-emitted without advancing done (long NAS listing, etc.) */
  heartbeat?: boolean;
  stamp?: string;
  error?: string;
  action?: string;
  /** engine_log / step_log events */
  line?: string;
  level?: "info" | "warn" | "error" | "detail";
  /** step_log: function or sub-step name within a phase */
  step?: string;
}

export interface SkippedItem {
  reason: string;
  section: string;
  item_name: string;
  path: string;
  detail: string;
  source: string;
}

export interface DeepIdentifyItem {
  section: string;
  item_name: string;
  path: string;
  method: string;
  vendor: string;
  score: string;
  evidence: string;
  previous_vendor: string;
}

export interface VerificationFinding {
  check: string;
  severity: string;
  subject: string;
  path: string;
  detail: string;
  suggestion: string;
}

export interface QualityScorecard {
  total_items?: number;
  identified_confirmed?: number;
  identified_tentative?: number;
  identified_unknown?: number;
  identification_rate_pct?: number;
  confirmed_rate_pct?: number;
  dedupe_eligible?: number;
  dedupe_eligible_pct?: number;
  duplicate_groups?: number;
  duplicate_groups_high?: number;
  routes_ready?: number;
  routes_needing_review?: number;
  route_ready_pct?: number;
  investigation_items?: number;
  investigation_pct?: number;
  investigation_buckets?: Record<string, number>;
  findings_total?: number;
  findings_warnings?: number;
  findings_suggestions?: number;
}

export interface ScanFailureItem {
  section: string;
  item_name: string;
  path: string;
  error: string;
}

export interface NestedIssueItem {
  section: string;
  item_name: string;
  issue_type: string;
  nested_path: string;
  repeated_name: string;
  depth: number | null;
  suggested_fix: string;
}

export interface CoexistenceItem {
  section: string;
  item_name: string;
  item_path: string;
  issue_type: string;
  parent_path: string;
  archive_or_installer: string;
  extracted_folder: string;
  depth: number | null;
  name_similarity_pct: number | null;
  suggested_action: string;
}

export interface InventoryItem {
  root_bin: string;
  item_name: string;
  fingerprint: string;
  version_key: string;
  item_type: string;
  vendor: string;
  id_method: string;
  tonex: string;
}

export interface CacheHitItem {
  section: string;
  path: string;
  name: string;
  mtime: number | null;
}

export interface CoverageGapItem {
  section: string;
  path: string;
  name: string;
  reason: string;
  detail: string;
}

export interface ProbeTruncationItem {
  section: string;
  item_path: string;
  item_name: string;
  kind: string;
  truncated_path: string;
  relative_path: string;
  depth: number | null;
  limit: number | null;
  detail: string;
}

export interface SkipPhaseImpact {
  phase: string;
  count: number;
  detail: string;
}

export interface RunComparisonDelta {
  path: string;
  change_type: string;
  old_value: string;
  new_value: string;
  section: string;
}

export interface RunComparison {
  stamp_a: string;
  stamp_b: string;
  deltas: RunComparisonDelta[];
  new_failures: string[];
  resolved_failures: string[];
  new_cache_hits: string[];
  fresh_scans: string[];
}

export type TabId =
  | "dashboard"
  | "scan"
  | "investigation"
  | "duplicates"
  | "restructure"
  | "archives"
  | "scene-renames"
  | "scan-audit"
  | "skipped"
  | "vendors"
  | "space-recovery"
  | "security"
  | "environment"
  | "help";

export type DependencyCategory = "required" | "recommended" | "optional";
export type DependencyStatusKind = "ok" | "missing" | "degraded" | "skipped";

export interface EnvironmentDependency {
  id: string;
  name: string;
  category: DependencyCategory;
  status: DependencyStatusKind;
  detail: string;
  path?: string | null;
  version?: string | null;
  install_hints: string[];
  repair_action?: string | null;
}

export interface EnvironmentSummary {
  total: number;
  ok: number;
  missing: number;
  degraded: number;
  required_missing: number;
  recommended_missing: number;
  healthy: boolean;
}

export interface EnvironmentPayload {
  platform: string;
  checked_at: string;
  workspace: string;
  manifest_path: string;
  isolation?: {
    isolated?: boolean;
    venv_active?: boolean;
    detail?: string;
  };
  dependencies: EnvironmentDependency[];
  summary: EnvironmentSummary;
  manifest: Record<string, unknown>;
  recent_operations: Array<Record<string, unknown>>;
  repair_actions: Record<string, string>;
}

export interface EnvironmentManifest {
  version: number;
  updated: string;
  library_roots: string[];
  tool_preferences: {
    seven_zip?: string;
    fpcalc_path?: string;
  };
  scheduled_checks_enabled?: boolean;
  last_scheduled_check?: string | null;
}

export interface MalwareFinding {
  path: string;
  relative_path: string;
  name: string;
  size: number;
  severity: string;
  reasons: string[];
  sha256: string;
  lookup?: Record<string, string>;
  capabilities?: Array<{ id: string; severity: string; description: string; engine?: string }>;
  capability_severity?: string;
  clamav?: { status: string; engine?: string | null; detail?: string };
  /** @deprecated Legacy scan reports may include defender instead of clamav */
  defender?: { status: string; detail?: string };
}
