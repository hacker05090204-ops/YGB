/**
 * YGB API Client
 * TypeScript client for communicating with the YGB FastAPI backend
 */

import { buildAuthHeaders } from "./auth-token";

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000";

/**
 * Centralized fetch wrapper that includes Authorization header.
 * Uses unified token lookup from auth-token.ts.
 */
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = buildAuthHeaders(
    options.headers as Record<string, string> || {}
  );

  return fetch(url, { ...options, headers });
}

// ============== TYPES ==============

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
  const res = await authFetch(`${API_BASE}/api/phases`);
  if (!res.ok) throw new Error("Failed to fetch phases");
  return res.json();
}

export async function getHunterModules(): Promise<HunterModuleInfo[]> {
  const res = await authFetch(`${API_BASE}/api/hunter-modules`);
  if (!res.ok) throw new Error("Failed to fetch hunter modules");
  return res.json();
}

export async function runPhase(phase: string): Promise<ExecutionResult> {
  const res = await authFetch(`${API_BASE}/api/run-phase`, {
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
  const res = await authFetch(`${API_BASE}/api/run-hunter`, {
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
  const res = await authFetch(`${API_BASE}/api/health`);
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
  const res = await authFetch(`${API_BASE}/api/storage/stats`);
  if (!res.ok) throw new Error("Failed to fetch storage stats");
  return res.json();
}

export async function getDiskStatus(): Promise<DiskStatus> {
  const res = await authFetch(`${API_BASE}/api/storage/disk`);
  if (!res.ok) throw new Error("Failed to fetch disk status");
  return res.json();
}

export async function getLifecycleStatus(): Promise<LifecycleStatus> {
  const res = await authFetch(`${API_BASE}/api/storage/lifecycle`);
  if (!res.ok) throw new Error("Failed to fetch lifecycle status");
  return res.json();
}

export async function getDeletePreview(entityType?: string) {
  const url = entityType
    ? `${API_BASE}/api/storage/delete-preview?entity_type=${entityType}`
    : `${API_BASE}/api/storage/delete-preview`;
  const res = await authFetch(url);
  if (!res.ok) throw new Error("Failed to fetch delete preview");
  return res.json();
}

export async function getVideoList(userId?: string) {
  const url = userId
    ? `${API_BASE}/api/video/list?user_id=${userId}`
    : `${API_BASE}/api/video/list`;
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
  const res = await authFetch(`${API_BASE}/api/readiness`);
  if (!res.ok) throw new Error("Failed to fetch dataset readiness");
  return res.json();
}

export async function getIntegrationStatus(): Promise<IntegrationStatusResponse> {
  const res = await authFetch(`${API_BASE}/api/integration/status`);
  if (!res.ok) throw new Error("Failed to fetch integration status");
  return res.json();
}

export async function getCVEPipelineStatus(): Promise<CVEPipelineStatus> {
  const res = await authFetch(`${API_BASE}/api/cve/status`);
  if (!res.ok) throw new Error("Failed to fetch CVE pipeline status");
  return res.json();
}

export async function getBackupStatus(): Promise<BackupStatus> {
  const res = await authFetch(`${API_BASE}/api/backup/status`);
  if (!res.ok) throw new Error("Failed to fetch backup status");
  return res.json();
}

export async function getRolloutMetrics(): Promise<RolloutMetrics> {
  const res = await authFetch(`${API_BASE}/api/rollout/metrics`);
  if (!res.ok) throw new Error("Failed to fetch rollout metrics");
  return res.json();
}
