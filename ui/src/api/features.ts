/**
 * API calls for the Nov 28 review features: Plugin Ledger, license vault, DAW projects,
 * schedules, notifications, import pipeline, naming templates, release monitor,
 * recovery, space map, clone support, UCS write-back, extensions, the sample similarity
 * finder and the shared catalog.
 *
 * Kept out of client.ts so that file stops growing (review P3-9).
 */
import { deleteJson, downloadAuthenticated, getJson, postJson, putJson } from "./client";

/** Turn a thrown API error (often a JSON `{"detail": ...}` body) into readable text. */
export function errorText(err: unknown): string {
  const raw = err instanceof Error ? err.message : String(err);
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) return parsed.detail.map((d) => (d as { msg?: string }).msg ?? "").join("; ");
  } catch {
    /* not JSON */
  }
  return raw;
}

// ── Plugin Ledger ────────────────────────────────────────────────────────────

export type LedgerStatus =
  | "installer_older"
  | "no_installer"
  | "covered"
  | "covered_unknown_version"
  | "never_installed"
  | "ignored";

export interface LedgerInstaller {
  item_name: string;
  path: string;
  vendor?: string;
  version: string;
  size_mb: number;
  score?: number;
}

export interface LicenseSummary {
  license_type?: string;
  has_secret?: boolean;
  account?: string;
  updated_at?: string;
}

export interface LedgerRow {
  key: string;
  vendor: string;
  product: string;
  installed_version?: string;
  formats?: string[];
  architectures?: string[];
  paths?: string[];
  status: LedgerStatus;
  note: string;
  newest_installer_version?: string;
  installers: LedgerInstaller[];
  license: LicenseSummary | null;
  project_count?: number;
}

export interface LedgerResponse {
  stamp: string | null;
  host: string;
  scanned_at: string | null;
  installed_count: number;
  counts: Record<string, number>;
  plugins: LedgerRow[];
  never_installed: LedgerRow[];
}

export interface PluginSettings {
  extra_dirs: Array<{ format: string; path: string }>;
  default_dirs: Array<{ format: string; path: string; exists: boolean }>;
  scanned_at: string | null;
  host: string;
  count: number;
}

export const fetchLedger = (stamp?: string) =>
  getJson<LedgerResponse>(`/plugins/ledger${stamp ? `?stamp=${encodeURIComponent(stamp)}` : ""}`);
export const fetchPluginSettings = () => getJson<PluginSettings>("/plugins/settings");
export const savePluginDirs = (extra_dirs: Array<{ format: string; path: string }>) =>
  putJson<PluginSettings>("/plugins/settings", { extra_dirs });
export const scanPlugins = () =>
  postJson<{ count: number; folders: Array<{ format: string; path: string; plugins: number }> }>("/plugins/scan", {});
export const exportPluginInventory = () => getJson<Record<string, unknown>>("/plugins/inventory/export");
export const importPluginInventory = (payload: unknown) =>
  postJson<{ count: number; host: string }>("/plugins/inventory/import", payload);
export const ignoreLedgerKeys = (keys: string[], ignored: boolean) =>
  postJson<{ ignored: string[] }>("/plugins/ignore", { keys, ignored });
export const downloadReinstallChecklist = (format: "markdown" | "csv") =>
  downloadAuthenticated("/plugins/checklist", `reinstall_checklist.${format === "csv" ? "csv" : "md"}`, { format });

// ── License vault ────────────────────────────────────────────────────────────

export interface LicenseRow extends LicenseSummary {
  product_key: string;
  vendor: string;
  product: string;
  seats: string;
  purchase_date: string;
  notes: string;
}

export const fetchLicenses = () =>
  getJson<{ encryption: string; count: number; with_secret: number; license_types: string[]; licenses: LicenseRow[] }>(
    "/licenses",
  );
export const saveLicense = (key: string, body: Partial<LicenseRow> & { secret?: string }) =>
  putJson<LicenseRow>(`/licenses/${encodeURIComponent(key)}`, body);
export const deleteLicense = (key: string) => deleteJson<{ ok: boolean }>(`/licenses/${encodeURIComponent(key)}`);
export const revealLicense = (key: string) =>
  postJson<{ product_key: string; secret: string }>(`/licenses/${encodeURIComponent(key)}/reveal`, {});

// ── DAW projects ─────────────────────────────────────────────────────────────

export interface DawSummary {
  roots: string[];
  indexed_at: string | null;
  project_count: number;
  errors: Array<{ path: string; error: string }>;
  top_plugins: Array<{ name: string; vendor: string; projects: number }>;
  by_daw?: Record<string, number>;
  formats?: string[];
  heuristic?: string[];
}

export const fetchDawProjects = () => getJson<DawSummary>("/daw-projects");
export const saveDawRoots = (roots: string[]) => putJson<{ roots: string[] }>("/daw-projects/roots", { roots });
export const indexDawProjects = () => postJson<DawSummary>("/daw-projects/index", {});
export const dawUsage = (query: { plugin?: string; path?: string }) => {
  const qs = new URLSearchParams(query as Record<string, string>);
  return getJson<{ count: number; projects: Array<{ name: string; path: string; daw: string }> }>(
    `/daw-projects/usage?${qs}`,
  );
};

// ── Schedules ────────────────────────────────────────────────────────────────

export interface Schedule {
  id: string;
  name: string;
  cron: string;
  root: string;
  enabled: boolean;
  notify: boolean;
  skip_phases: string[];
  incremental: boolean;
  next_run: string | null;
  last_run: { at: string; outcome: string; job_id: string | null; detail: string } | null;
}

export const fetchSchedules = () =>
  getJson<{ enabled: boolean; schedules: Schedule[]; aliases: string[] }>("/schedules");
export const createSchedule = (body: Partial<Schedule>) => postJson<Schedule>("/schedules", body);
export const updateSchedule = (id: string, body: Partial<Schedule>) =>
  putJson<Schedule>(`/schedules/${encodeURIComponent(id)}`, body);
export const deleteSchedule = (id: string) => deleteJson<{ ok: boolean }>(`/schedules/${encodeURIComponent(id)}`);
export const runScheduleNow = (id: string) =>
  postJson<{ outcome: string; job_id?: string }>(`/schedules/${encodeURIComponent(id)}/run`, {});
export const previewCron = (cron: string) => postJson<{ next_runs: string[] }>("/schedules/preview", { cron });

// ── Notifications ────────────────────────────────────────────────────────────

export interface NotifyTarget {
  id: string;
  name: string;
  enabled: boolean;
  url_masked: string;
}

export interface NotificationConfig {
  notify_on: "scheduled" | "all" | "never";
  only_when_changed: boolean;
  targets: NotifyTarget[];
  apprise_available: boolean;
  air_gap: boolean;
  history: Array<{ ts: string; title: string; results: Array<{ name: string; ok: boolean; error?: string }> }>;
}

export const fetchNotifications = () => getJson<NotificationConfig>("/notifications");
export const saveNotificationSettings = (body: { notify_on?: string; only_when_changed?: boolean }) =>
  putJson<NotificationConfig>("/notifications/settings", body);
export const addNotifyTarget = (name: string, url: string) =>
  postJson<NotifyTarget>("/notifications/targets", { name, url });
export const updateNotifyTarget = (id: string, body: { enabled?: boolean; name?: string }) =>
  putJson<{ ok: boolean }>(`/notifications/targets/${encodeURIComponent(id)}`, body);
export const deleteNotifyTarget = (id: string) =>
  deleteJson<{ ok: boolean }>(`/notifications/targets/${encodeURIComponent(id)}`);
export const testNotifications = (target_ids?: string[]) =>
  postJson<{ sent: number; failed: number; skipped?: string; results: Array<{ name: string; ok: boolean; error?: string }> }>(
    "/notifications/test",
    target_ids ? { target_ids } : {},
  );

// ── Import pipeline ──────────────────────────────────────────────────────────

export interface ImportProposal {
  name: string;
  path: string;
  is_dir: boolean;
  size_mb: number;
  vendor: string;
  confidence: number;
  method: string;
  library_status: "new" | "newer_version" | "older_version" | "duplicate" | "unidentified";
  match: { item_name: string; path: string; version: string } | null;
  bin: string;
  destination: string;
  as_is_destination: string;
  recommended: "apply" | "as_is" | "skip";
}

export interface ImportSettings {
  incoming: string;
  library_root: string;
  default_bin: string;
  auto_apply_threshold: number | null;
  decided: number;
}

export const fetchImport = () =>
  getJson<{ settings: ImportSettings; configured: boolean; incoming?: string; error?: string; items: ImportProposal[]; waiting: string[] }>(
    "/import",
  );
export const saveImportSettings = (body: Partial<ImportSettings> & { confirm_live?: boolean }) =>
  putJson<ImportSettings>("/import/settings", body);
export const applyImport = (
  items: Array<{ path: string; action: string; destination?: string }>,
  live: boolean,
) =>
  postJson<{ dry_run: boolean; batch_id: string | null; results: Array<{ ok: boolean; path: string; destination?: string; error?: string }> }>(
    "/import/apply",
    { items, dry_run: !live, confirm_live: live || undefined },
  );

// ── Naming templates ─────────────────────────────────────────────────────────

export interface NamingConfig {
  enabled: boolean;
  template: string;
  fields: string[];
  presets: Array<{ label: string; template: string }>;
  default: string;
}

export interface NamingPreview {
  stamp: string | null;
  template: string;
  routed_items: number;
  collisions: number;
  distinct_folders: number;
  rows: Array<{ item_name: string; planned_destination: string; template_destination: string; collision: boolean }>;
}

export const fetchNamingTemplate = () => getJson<NamingConfig>("/naming-template");
export const saveNamingTemplate = (template: string, enabled: boolean) =>
  putJson<{ enabled: boolean; template: string }>("/naming-template", { template, enabled });
export const previewNamingTemplate = (template: string, stamp?: string) =>
  postJson<NamingPreview>("/naming-template/preview", { template, stamp });

// ── Release monitor ──────────────────────────────────────────────────────────

export interface ReleaseFeed {
  id: string;
  vendor: string;
  url: string;
  last_checked: string | null;
  last_error: string | null;
}

export interface ReleaseEntry {
  id: string;
  title: string;
  link: string;
  published: string;
  vendor: string;
  kind: "update" | "not_owned" | "owned";
  product: string;
  version: string;
  owned_version: string;
  user_state: "" | "wanted" | "dismissed";
}

export const fetchReleases = (includeOwned = false) =>
  getJson<{ checked_at: string | null; feeds: ReleaseFeed[]; counts: Record<string, number>; entries: ReleaseEntry[] }>(
    `/releases?include_owned=${includeOwned}`,
  );
export const addReleaseFeed = (vendor: string, url: string) => postJson<ReleaseFeed>("/releases/feeds", { vendor, url });
export const deleteReleaseFeed = (id: string) => deleteJson<{ ok: boolean }>(`/releases/feeds/${encodeURIComponent(id)}`);
export const checkReleaseFeeds = () =>
  postJson<{ checked: number; new_entries: number; errors: Array<{ vendor: string; error: string }> }>("/releases/check", {});
export const markReleaseEntry = (id: string, state: "" | "wanted" | "dismissed") =>
  putJson<{ ok: boolean }>(`/releases/entries/${encodeURIComponent(id)}`, { state });

// ── Extensions ───────────────────────────────────────────────────────────────

export const fetchExtensions = () =>
  getJson<{
    enabled: boolean;
    folder: string;
    extensions: Array<{ file: string; name: string; vendor_rules: number; notifier: boolean; exporter: boolean; embedder?: boolean }>;
    errors: Array<{ file: string; error: string }>;
  }>("/extensions");

// ── Recovery, clone support, space map ───────────────────────────────────────

export interface RecoveryItem {
  id: string;
  batch_id: string;
  op: string;
  src: string;
  dst: string;
  is_dir: boolean;
  ts: string;
  state: "not_moved" | "moved" | "undo_interrupted" | "manual";
  detail: string;
  actions: Array<"finish" | "restore" | "dismiss" | "resume" | "resolved">;
}

export const fetchRecovery = () => getJson<{ count: number; items: RecoveryItem[]; busy?: string }>("/recovery");
export const resolveRecovery = (id: string, action: string) =>
  postJson<{ ok: boolean }>(`/recovery/${encodeURIComponent(id)}`, { action, confirm_live: true });

export const fetchCloneSupport = () =>
  getJson<{ roots: Array<{ path: string; supported: boolean; reason: string }>; any_supported: boolean }>(
    "/space-recovery/clone-support",
  );

export interface SpaceNode {
  name: string;
  size_mb: number;
  duplicate_mb: number;
  items: number;
  other?: boolean;
  children?: SpaceNode[];
}

export const fetchSpaceMap = (stamp: string, groupBy: "bin" | "status" = "bin") =>
  getJson<{ stamp: string; group_by: string; total_mb: number; duplicate_mb: number; children: SpaceNode[] }>(
    `/runs/${stamp}/space-map?group_by=${groupBy}`,
  );

// ── UCS write-back ───────────────────────────────────────────────────────────

export interface UcsFields {
  paths: string[];
  cat_id: string;
  creator_id: string;
  source_id: string;
  user_data?: string;
}

export interface UcsPlanRow {
  path: string;
  name: string;
  fx_name: string;
  new_name: string;
  already_ucs: boolean;
  error: string;
  unchanged: boolean;
}

export const planUcs = (body: UcsFields) => postJson<{ rows: UcsPlanRow[]; ok: number; errors: number }>("/ucs/plan", body);
export const applyUcs = (body: UcsFields & { rename: boolean; metadata: boolean }) =>
  postJson<{
    rename?: { batch_id: string; renamed: number; failed: number };
    metadata?: { batch: string | null; written: number; failed: number };
  }>("/ucs/apply", { ...body, confirm_live: true });
export const fetchUcsBatches = () =>
  getJson<{ batches: Array<{ batch: string; created: string; files: number; restored: boolean }> }>("/ucs/metadata-batches");
export const undoUcsBatch = (batch: string) =>
  postJson<{ restored: number }>(`/ucs/metadata-batches/${encodeURIComponent(batch)}/undo`, { confirm_live: true });

// ── Sample similarity ────────────────────────────────────────────────────────

export interface SimilarityStatus {
  roots: string[];
  indexed_at: string | null;
  count: number;
  skipped: number;
  skip_reasons: Record<string, number>;
  embedder: string | null;
  method: string;
  analysed?: number;
  remaining?: number;
}

export interface SimilarSample {
  path: string;
  name: string;
  folder: string;
  score: number;
  duration_s: number | null;
}

export const fetchSimilarityStatus = () => getJson<SimilarityStatus>("/samples/similarity");
export const saveSimilarityRoots = (roots: string[]) => putJson<SimilarityStatus>("/samples/similarity/roots", { roots });
export const indexSimilarity = (maxFiles = 2000) =>
  postJson<SimilarityStatus>("/samples/similarity/index", { max_files: maxFiles });
export const findSimilar = (path: string, opts: { limit?: number; excludeSameFolder?: boolean } = {}) => {
  const qs = new URLSearchParams({ path, limit: String(opts.limit ?? 25) });
  if (opts.excludeSameFolder) qs.set("exclude_same_folder", "true");
  return getJson<{ query: string; duration_s: number | null; results: SimilarSample[]; method: string }>(
    `/samples/similar?${qs}`,
  );
};
export const searchSimilarityIndex = (q: string) =>
  getJson<{ results: Array<{ path: string; name: string; duration_s: number | null }> }>(
    `/samples/similarity/search?q=${encodeURIComponent(q)}`,
  );

// ── Shared catalog ───────────────────────────────────────────────────────────

export type CatalogBundle = Record<string, unknown>;

export interface CatalogSubscription {
  id: string;
  url: string;
  name: string;
  pinned_fingerprint: string | null;
  last_checked: string | null;
  last_error: string | null;
  pending: number | null;
}

export interface CatalogPreview {
  name: string;
  publisher: string;
  description: string;
  created: string | null;
  signature: { state: "unsigned" | "invalid" | "valid" | "trusted" | "key_changed"; fingerprint: string | null };
  vendor_rules: Array<{ company: string; keywords: string[]; category: string; change: string; new_keywords: string[] }>;
  release_feeds: Array<{ vendor: string; url: string; change: string }>;
  dropped: number;
  changes: number;
}

export interface CatalogOverview {
  subscriptions: CatalogSubscription[];
  trusted: Record<string, { name: string; added_at: string }>;
  applied: Array<{ at: string; source: string; name: string; fingerprint: string | null; vendor_rules: number; release_feeds: number }>;
  publisher: { public_key: string; fingerprint: string } | null;
  local: { vendor_rules: number; release_feeds: number };
}

export interface CatalogSelection {
  companies?: string[];
  feed_urls?: string[];
}

export const fetchCatalog = () => getJson<CatalogOverview>("/catalog");
export const exportCatalog = (body: { name: string; publisher?: string; description?: string }) =>
  postJson<CatalogBundle>("/catalog/export", body);
export const previewCatalog = (bundle: CatalogBundle) => postJson<CatalogPreview>("/catalog/preview", { bundle });
export const importCatalog = (bundle: CatalogBundle, selection: CatalogSelection) =>
  postJson<{ vendor_rules: number; release_feeds: number }>("/catalog/import", { bundle, ...selection });
export const subscribeCatalog = (url: string, name = "") =>
  postJson<CatalogSubscription>("/catalog/subscriptions", { url, name });
export const unsubscribeCatalog = (id: string) => deleteJson<{ ok: boolean }>(`/catalog/subscriptions/${id}`);
export const refreshCatalog = (id: string) =>
  postJson<{ subscription: CatalogSubscription; preview: CatalogPreview }>(`/catalog/subscriptions/${id}/refresh`, {});
export const subscriptionPreview = (id: string) =>
  getJson<{ subscription: CatalogSubscription; preview: CatalogPreview }>(`/catalog/subscriptions/${id}/preview`);
export const applySubscription = (id: string, selection: CatalogSelection) =>
  postJson<{ vendor_rules: number; release_feeds: number }>(`/catalog/subscriptions/${id}/apply`, selection);
export const trustPublisher = (fingerprint: string, name: string, trusted = true) =>
  postJson<{ trusted: Record<string, unknown> }>("/catalog/trust", { fingerprint, name, trusted });
