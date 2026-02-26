/**
 * Real-Data Rollout — TypeScript interfaces and API helpers.
 *
 * Provides typed interfaces for the rollout stage and risk metrics,
 * plus fetch helpers and utility functions for the dashboard.
 */

import { authFetch } from "@/lib/ygb-api";
// ============== TYPES ==============

export type RolloutStageName = "STAGE_0" | "STAGE_1" | "STAGE_2" | "STAGE_3";

export const ROLLOUT_PERCENTAGES: Record<RolloutStageName, number> = {
    STAGE_0: 20,
    STAGE_1: 40,
    STAGE_2: 70,
    STAGE_3: 100,
};

export interface RiskMetrics {
    label_quality: number;
    class_imbalance_ratio: number;
    js_divergence: number;
    unknown_token_ratio: number;
    feature_mismatch_ratio: number;
    fpr_current: number;
    fpr_baseline: number;
    drift_guard_pass: boolean;
    regression_gate_pass: boolean;
    determinism_gate_pass: boolean;
    backtest_gate_pass: boolean;
}

export type BlockingReason =
    | "LABEL_QUALITY_LOW"
    | "CLASS_IMBALANCE_HIGH"
    | "DISTRIBUTION_SHIFT"
    | "FEATURE_MISMATCH"
    | "UNKNOWN_TOKEN_HIGH"
    | "FPR_REGRESSION"
    | "DRIFT_GUARD_FAIL"
    | "REGRESSION_GATE_FAIL"
    | "DETERMINISM_GATE_FAIL"
    | "BACKTEST_GATE_FAIL";

export interface PromotionRecord {
    from_stage: number;
    to_stage: number;
    cycle_id: string;
    timestamp: string;
}

export interface RolloutStatus {
    stage: number;
    stage_label: RolloutStageName;
    real_data_pct: number;
    consecutive_stable: number;
    frozen: boolean;
    freeze_reasons: BlockingReason[];
    total_cycles: number;
    last_cycle_id: string | null;
    last_updated: string | null;
    promotion_history: PromotionRecord[];
}

export interface CycleResult {
    stage: number;
    stage_label: RolloutStageName;
    real_data_pct: number;
    blocked: boolean;
    blocking_reasons: BlockingReason[];
    consecutive_stable: number;
    promoted: boolean;
    frozen: boolean;
    total_cycles: number;
    result_summary: string;
}

// ============== THRESHOLDS ==============

export const THRESHOLDS = {
    LABEL_QUALITY_FLOOR: 0.9,
    CLASS_IMBALANCE_MAX: 10.0,
    DISTRIBUTION_SHIFT_MAX: 0.15,
    UNKNOWN_TOKEN_MAX: 0.05,
    FPR_REGRESSION_DELTA_MAX: 0.02,
} as const;

// ============== UTILITIES ==============

/**
 * Check if the current rollout is blocked.
 */
export function isBlocked(status: RolloutStatus): boolean {
    return status.frozen && status.freeze_reasons.length > 0;
}

/**
 * Get human-readable blocking reasons.
 */
export function getBlockingReasons(status: RolloutStatus): string[] {
    const labels: Record<BlockingReason, string> = {
        LABEL_QUALITY_LOW: `Label quality below ${THRESHOLDS.LABEL_QUALITY_FLOOR}`,
        CLASS_IMBALANCE_HIGH: `Class imbalance exceeds ${THRESHOLDS.CLASS_IMBALANCE_MAX}`,
        DISTRIBUTION_SHIFT: `JS divergence exceeds ${THRESHOLDS.DISTRIBUTION_SHIFT_MAX}`,
        FEATURE_MISMATCH: `Feature mismatch exceeds ${THRESHOLDS.UNKNOWN_TOKEN_MAX}`,
        UNKNOWN_TOKEN_HIGH: `Unknown token ratio exceeds ${THRESHOLDS.UNKNOWN_TOKEN_MAX}`,
        FPR_REGRESSION: `FPR regression delta exceeds ${THRESHOLDS.FPR_REGRESSION_DELTA_MAX}`,
        DRIFT_GUARD_FAIL: "Drift guard check failed",
        REGRESSION_GATE_FAIL: "Regression gate check failed",
        DETERMINISM_GATE_FAIL: "Determinism gate check failed",
        BACKTEST_GATE_FAIL: "Backtest gate check failed",
    };

    return status.freeze_reasons.map((r) => labels[r] ?? r);
}

/**
 * Check individual metric against threshold.
 */
export function isMetricPassing(metricName: keyof typeof THRESHOLDS, value: number): boolean {
    const threshold = THRESHOLDS[metricName];
    // FLOOR metrics: value must be >= threshold
    if (metricName === "LABEL_QUALITY_FLOOR") {
        return value >= threshold;
    }
    // MAX metrics: value must be <= threshold
    return value <= threshold;
}

/**
 * Serialize RolloutStatus to JSON string.
 */
export function serializeStatus(status: RolloutStatus): string {
    return JSON.stringify(status);
}

/**
 * Deserialize JSON string to RolloutStatus.
 */
export function deserializeStatus(json: string): RolloutStatus {
    return JSON.parse(json) as RolloutStatus;
}

// ============== API HELPERS ==============

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000";

/**
 * Fetch current rollout status from API.
 */
export async function fetchRolloutStatus(): Promise<RolloutStatus> {
    const res = await authFetch(`${API_BASE}/api/rollout/status`);
    if (!res.ok) throw new Error("Failed to fetch rollout status");
    return res.json();
}

/**
 * Fetch latest risk metrics from API.
 */
export async function fetchRiskMetrics(): Promise<RiskMetrics> {
    const res = await authFetch(`${API_BASE}/api/rollout/metrics`);
    if (!res.ok) throw new Error("Failed to fetch risk metrics");
    return res.json();
}
