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

export interface JobSnapshot {
  job_id: string;
  status: string;
  dry_run: boolean;
  root: string;
  stamp: string | null;
  exit_code: number | null;
  error: string | null;
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
  stamp?: string;
  error?: string;
}

export type TabId =
  | "dashboard"
  | "scan"
  | "investigation"
  | "duplicates"
  | "restructure"
  | "archives"
  | "scene-renames";
