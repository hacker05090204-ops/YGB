/**
 * YGB API Client
 * TypeScript client for communicating with the YGB FastAPI backend
 */

import { credentialedFetch } from "./auth-token";

const _ENV_API_BASE = (process.env.NEXT_PUBLIC_YGB_API_URL || "").trim().replace(/\/+$/, "");
const _DEFAULT_API_BASE = "http://localhost:8000";
const _API_PORT = "8000";
const _API_BASE_OVERRIDE_KEY = "ygb_api_base_override";

function isLoopbackHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1";
}

function normalizeApiBase(raw: string | null | undefined): string {
  if (!raw) return "";
  try {
    const url = new URL(raw);
    return url.origin.replace(/\/+$/, "");
  } catch {
    return "";
  }
}

function isPrivateOrigin(origin: string): boolean {
  try {
    const url = new URL(origin);
    const host = url.hostname;
    if (host === "localhost" || host === "127.0.0.1") return true;
    if (host.endsWith(".ts.net")) return true;
    if (host.startsWith("192.168.") || host.startsWith("10.")) return true;
    if (host.startsWith("100.")) return true; // Tailscale CGNAT
    if (host.startsWith("172.")) {
      const second = parseInt(host.split(".")[1], 10);
      if (second >= 16 && second <= 31) return true;
    }
    return false;
  } catch {
    return false;
  }
}

function readBrowserApiBaseOverride(): string {
  if (typeof window === "undefined") {
    return "";
  }

  const fromQuery = normalizeApiBase(
    new URLSearchParams(window.location.search).get("api_base")
  );
  // GOVERNANCE: Only accept private/LAN IPs — never allow external redirects
  if (fromQuery && isPrivateOrigin(fromQuery)) {
    try {
      window.localStorage.setItem(_API_BASE_OVERRIDE_KEY, fromQuery);
    } catch {
      // Ignore storage failures and still use the query value.
    }
    return fromQuery;
  }

  return "";
}

function readStoredBrowserApiBaseOverride(): string {
  if (typeof window === "undefined") {
    return "";
  }

  try {
    const stored = normalizeApiBase(window.localStorage.getItem(_API_BASE_OVERRIDE_KEY));
    if (stored && isPrivateOrigin(stored)) return stored;
    // Clear any stored non-private override (stale or malicious)
    if (stored) window.localStorage.removeItem(_API_BASE_OVERRIDE_KEY);
    return "";
  } catch {
    return "";
  }
}

/**
 * Derive API base URL at runtime from the browser's current hostname.
 * This ensures cookies set by the backend at IP:8000 are sent back to the
 * same IP:8000 — not to "localhost:8000" which is a different cookie domain.
 * If the frontend runs on localhost from another device, allow an explicit
 * backend override via query string, localStorage, or env.
 */
export function getApiBase(): string {
  if (typeof window === "undefined") return _ENV_API_BASE || _DEFAULT_API_BASE;

  const queryOverride = readBrowserApiBaseOverride();
  if (queryOverride) {
    return queryOverride;
  }

  if (_ENV_API_BASE) {
    return _ENV_API_BASE;
  }

  const storedOverride = readStoredBrowserApiBaseOverride();
  if (storedOverride) {
    return storedOverride;
  }

  const { protocol, hostname } = window.location;
  const derived = `${protocol}//${hostname}:${_API_PORT}`;
  if (!isLoopbackHost(hostname)) {
    return derived;
  }

  return derived;
}

/**
 * Centralized fetch wrapper that includes auth credentials (HttpOnly cookies).
 */
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  return credentialedFetch(url, {
    ...options,
    cache: "no-store",
  });
}

export interface PhaseInfo {
  name: string;
  path: string;
  has_tests: boolean;
  description?: string;
}

export interface HunterModuleInfo {
  name: string;
  path: string;
  files: string[];
}

export type ExecutionStatus = "pending" | "running" | "success" | "failed";

export interface ExecutionResult {
  status: ExecutionStatus;
  stdout: string;
  stderr: string;
  return_code: number;
  phase?: string;
  module?: string;
}

export interface HealthCheck {
  status: string;
  ygb_root: string;
  python_phases: number;
  hunter_modules: number;
}

// ============== API FUNCTIONS ==============

export async function getPhases(): Promise<PhaseInfo[]> {
  const res = await authFetch(`${getApiBase()}/api/phases`);
  if (!res.ok) throw new Error("Failed to fetch phases");
  return res.json();
}

export async function getHunterModules(): Promise<HunterModuleInfo[]> {
  const res = await authFetch(`${getApiBase()}/api/hunter-modules`);
  if (!res.ok) throw new Error("Failed to fetch hunter modules");
  return res.json();
}

export async function runPhase(phase: string): Promise<ExecutionResult> {
  const res = await authFetch(`${getApiBase()}/api/run-phase`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phase }),
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to run phase");
  }
  return res.json();
}

export async function runHunterModule(module: string): Promise<ExecutionResult> {
  const res = await authFetch(`${getApiBase()}/api/run-hunter`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ module }),
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || "Failed to run module");
  }
  return res.json();
}

export async function checkHealth(): Promise<HealthCheck> {
  const res = await authFetch(`${getApiBase()}/api/health`);
  if (!res.ok) throw new Error("API server not available");
  return res.json();
}

// ============== HDD STORAGE API ==============

export interface StorageStats {
  initialized: boolean;
  hdd_root: string;
  entity_counts: Record<string, number>;
  disk_usage: {
    total_bytes: number;
    free_bytes: number;
    used_bytes: number;
    percent_used: number;
  };
  total_writes: number;
  total_reads: number;
  total_entities: number;
  total_bytes_written: number;
}

export interface DiskStatus {
  status: {
    total_bytes: number;
    free_bytes: number;
    used_bytes: number;
    percent_used: number;
    percent_free: number;
    alert_level: string;
    hdd_root: string;
  };
  breakdown: Record<string, {
    entity_count: number;
    total_bytes: number;
    total_mb: number;
    file_count: number;
  }>;
  index_health: Record<string, {
    meta_count: number;
    log_count: number;
    orphaned_logs: number;
    healthy: boolean;
  }>;
  alerts: string[];
}

export interface LifecycleStatus {
  deletion_preview: Array<{
    entity_type: string;
    entity_id: string;
    age_days: number;
    would_delete: boolean;
    reason?: string;
  }>;
  eligible_count: number;
}

export async function getStorageStats(): Promise<StorageStats> {
  const res = await authFetch(`${getApiBase()}/api/storage/stats`);
  if (!res.ok) throw new Error("Failed to fetch storage stats");
  return res.json();
}

export async function getDiskStatus(): Promise<DiskStatus> {
  const res = await authFetch(`${getApiBase()}/api/storage/disk`);
  if (!res.ok) throw new Error("Failed to fetch disk status");
  return res.json();
}

export async function getLifecycleStatus(): Promise<LifecycleStatus> {
  const res = await authFetch(`${getApiBase()}/api/storage/lifecycle`);
  if (!res.ok) throw new Error("Failed to fetch lifecycle status");
  return res.json();
}

export async function getDeletePreview(entityType?: string) {
  const url = entityType
    ? `${getApiBase()}/api/storage/delete-preview?entity_type=${entityType}`
    : `${getApiBase()}/api/storage/delete-preview`;
  const res = await authFetch(url);
  if (!res.ok) throw new Error("Failed to fetch delete preview");
  return res.json();
}

export async function getVideoList(userId?: string) {
  const url = userId
    ? `${getApiBase()}/api/video/list?user_id=${userId}`
    : `${getApiBase()}/api/video/list`;
  const res = await authFetch(url);
  if (!res.ok) throw new Error("Failed to fetch video list");
  return res.json();
}

// ============== READINESS & INTEGRATION API ==============

export interface DatasetReadiness {
  status: "READY" | "BLOCKED_REAL_DATA" | "UNKNOWN";
  min_samples_required: number | null;
  reason: string | null;
}

export interface IntegrationItem {
  state: "ENABLED" | "DISABLED" | "BLOCKED";
  reason: string;
}

export interface IntegrationStatusResponse {
  profile?: string;
  startup_ok?: boolean;
  integrations?: Record<string, IntegrationItem>;
  status?: string;
  reason?: string;
}

export interface CVEPipelineStatus {
  status: string;
  sources_total: number;
  sources_connected: number;
  sources_configured: number;
  total_records: number;
  sources: Record<string, {
    name: string;
    status: string;
    is_stale: boolean;
    records_fetched: number;
    last_error: string | null;
  }>;
  checked_at: string;
}

export interface BackupStatus {
  status: string;
  targets_active: number;
  targets_configured: number;
  targets_total: number;
  compression_default: string;
  targets: Record<string, {
    status: string;
    reason: string;
    last_backup_at: string | null;
    total_backups: number;
  }>;
  checked_at: string;
}

export interface RolloutMetrics {
  status: string;
  metrics_available: boolean;
  reason?: string;
  stage?: string | null;
  real_data_pct?: number | null;
  frozen?: boolean | null;
  timestamp: string;
}

export async function getDatasetReadiness(): Promise<DatasetReadiness> {
  const res = await authFetch(`${getApiBase()}/api/readiness`);
  if (!res.ok) throw new Error("Failed to fetch dataset readiness");
  return res.json();
}

export async function getIntegrationStatus(): Promise<IntegrationStatusResponse> {
  const res = await authFetch(`${getApiBase()}/api/integration/status`);
  if (!res.ok) throw new Error("Failed to fetch integration status");
  return res.json();
}

export async function getCVEPipelineStatus(): Promise<CVEPipelineStatus> {
  const res = await authFetch(`${getApiBase()}/api/cve/status`);
  if (!res.ok) throw new Error("Failed to fetch CVE pipeline status");
  return res.json();
}

export async function getBackupStatus(): Promise<BackupStatus> {
  const res = await authFetch(`${getApiBase()}/api/backup/status`);
  if (!res.ok) throw new Error("Failed to fetch backup status");
  return res.json();
}

export async function getRolloutMetrics(): Promise<RolloutMetrics> {
  const res = await authFetch(`${getApiBase()}/api/rollout/metrics`);
  if (!res.ok) throw new Error("Failed to fetch rollout metrics");
  return res.json();
}

// ============== USER PROFILE ==============

export interface UserProfile {
  id: string;
  name: string;
  email: string;
  role: string;
  github_login?: string;
  avatar_url?: string;
  auth_provider?: string;
}

export async function getUserProfile(): Promise<UserProfile> {
  const res = await authFetch(`${getApiBase()}/api/user/profile`);
  if (!res.ok) throw new Error("Failed to fetch user profile");
  return res.json();
}
