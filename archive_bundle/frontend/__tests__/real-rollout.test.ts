import { beforeEach, describe, expect, it, vi } from 'vitest'

const { authFetch, getApiBase } = vi.hoisted(() => ({
  authFetch: vi.fn(),
  getApiBase: vi.fn(() => 'https://ygb.example'),
}))

vi.mock('@/lib/ygb-api', () => ({
  authFetch,
  getApiBase,
}))

import {
  ROLLOUT_PERCENTAGES,
  THRESHOLDS,
  deserializeStatus,
  fetchRiskMetrics,
  fetchRolloutStatus,
  getBlockingReasons,
  isBlocked,
  isMetricPassing,
  serializeStatus,
  type RiskMetrics,
  type RolloutStatus,
} from '../lib/real-rollout'

const baseStatus: RolloutStatus = {
  stage: 1,
  stage_label: 'STAGE_1',
  real_data_pct: 40,
  consecutive_stable: 2,
  frozen: true,
  freeze_reasons: ['LABEL_QUALITY_LOW', 'DRIFT_GUARD_FAIL'],
  total_cycles: 7,
  last_cycle_id: 'cycle-7',
  last_updated: '2026-03-21T00:00:00Z',
  promotion_history: [],
}

describe('real-rollout utilities', () => {
  beforeEach(() => {
    authFetch.mockReset()
    getApiBase.mockClear()
  })

  it('exports the expected rollout percentages', () => {
    expect(ROLLOUT_PERCENTAGES).toEqual({
      STAGE_0: 20,
      STAGE_1: 40,
      STAGE_2: 70,
      STAGE_3: 100,
    })
  })

  it('detects blocked and unblocked rollout states', () => {
    expect(isBlocked(baseStatus)).toBe(true)
    expect(isBlocked({ ...baseStatus, frozen: false })).toBe(false)
    expect(isBlocked({ ...baseStatus, freeze_reasons: [] })).toBe(false)
  })

  it('maps blocking reasons to human-readable labels', () => {
    expect(getBlockingReasons(baseStatus)).toEqual([
      `Label quality below ${THRESHOLDS.LABEL_QUALITY_FLOOR}`,
      'Drift guard check failed',
    ])
    expect(getBlockingReasons({
      ...baseStatus,
      freeze_reasons: ['BACKTEST_GATE_FAIL', 'FEATURE_MISMATCH'],
    })).toEqual([
      'Backtest gate check failed',
      `Feature mismatch exceeds ${THRESHOLDS.UNKNOWN_TOKEN_MAX}`,
    ])
  })

  it('checks floor and max metrics correctly', () => {
    expect(isMetricPassing('LABEL_QUALITY_FLOOR', 0.91)).toBe(true)
    expect(isMetricPassing('LABEL_QUALITY_FLOOR', 0.89)).toBe(false)
    expect(isMetricPassing('CLASS_IMBALANCE_MAX', 9.5)).toBe(true)
    expect(isMetricPassing('CLASS_IMBALANCE_MAX', 10.5)).toBe(false)
    expect(isMetricPassing('DISTRIBUTION_SHIFT_MAX', 0.15)).toBe(true)
  })

  it('serializes and deserializes rollout status payloads', () => {
    const json = serializeStatus(baseStatus)

    expect(json).toContain('"stage_label":"STAGE_1"')
    expect(deserializeStatus(json)).toEqual(baseStatus)
  })
})

describe('real-rollout API helpers', () => {
  it('fetches rollout status successfully', async () => {
    authFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => baseStatus,
    })

    await expect(fetchRolloutStatus()).resolves.toEqual(baseStatus)
    expect(getApiBase).toHaveBeenCalled()
    expect(authFetch).toHaveBeenCalledWith('https://ygb.example/api/rollout/status')
  })

  it('throws when rollout status cannot be fetched', async () => {
    authFetch.mockResolvedValueOnce({ ok: false })

    await expect(fetchRolloutStatus()).rejects.toThrow('Failed to fetch rollout status')
  })

  it('fetches risk metrics successfully', async () => {
    const metrics: RiskMetrics = {
      label_quality: 0.95,
      class_imbalance_ratio: 1.5,
      js_divergence: 0.02,
      unknown_token_ratio: 0.01,
      feature_mismatch_ratio: 0.01,
      fpr_current: 0.03,
      fpr_baseline: 0.02,
      drift_guard_pass: true,
      regression_gate_pass: true,
      determinism_gate_pass: true,
      backtest_gate_pass: true,
    }
    authFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => metrics,
    })

    await expect(fetchRiskMetrics()).resolves.toEqual(metrics)
    expect(authFetch).toHaveBeenCalledWith('https://ygb.example/api/rollout/metrics')
  })

  it('throws when risk metrics cannot be fetched', async () => {
    authFetch.mockResolvedValueOnce({ ok: false })

    await expect(fetchRiskMetrics()).rejects.toThrow('Failed to fetch risk metrics')
  })
})
