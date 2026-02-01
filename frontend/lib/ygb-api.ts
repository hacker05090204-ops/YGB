/**
 * YGB API Client
 * TypeScript client for communicating with the YGB FastAPI backend
 */

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000";

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
  const res = await fetch(`${API_BASE}/api/phases`);
  if (!res.ok) throw new Error("Failed to fetch phases");
  return res.json();
}

export async function getHunterModules(): Promise<HunterModuleInfo[]> {
  const res = await fetch(`${API_BASE}/api/hunter-modules`);
  if (!res.ok) throw new Error("Failed to fetch hunter modules");
  return res.json();
}

export async function runPhase(phase: string): Promise<ExecutionResult> {
  const res = await fetch(`${API_BASE}/api/run-phase`, {
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
  const res = await fetch(`${API_BASE}/api/run-hunter`, {
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
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error("API server not available");
  return res.json();
}
