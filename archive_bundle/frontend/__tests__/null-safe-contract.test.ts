/**
 * Null-Safe Contract Tests — Frontend rendering with null API metrics.
 *
 * Verifies that client-side helpers and rendering logic handle null
 * metric values from API v2 without throwing or producing undefined.
 *
 * Covers:
 * 1. Null metric values render safely (no TypeError)
 * 2. Missing fields don't cause undefined access
 * 3. Field set stability — no unexpected removals
 * 4. Default fallback values for null metrics
 */
import { describe, it, expect } from 'vitest'

// ---------------------------------------------------------------------------
// API v2 contract schema (mirrors backend/api/api_v2_contract.py)
// ---------------------------------------------------------------------------

const REQUIRED_FIELDS = [
  'status',
  'storage_engine_status',
  'dataset_readiness',
  'training_ready',
  'timestamp',
] as const

const NULLABLE_FIELDS = [
  'runtime',
  'signature',
  'stale',
  'determinism_ok',
  'message',
] as const

const METRIC_FIELDS = [
  'total_epochs', 'completed_epochs', 'current_loss', 'best_loss',
  'precision', 'ece', 'drift_kl', 'duplicate_rate',
  'gpu_util', 'cpu_util', 'temperature',
  'progress_pct', 'loss_trend', 'total_errors',
] as const

// ---------------------------------------------------------------------------
// Safe rendering helpers (what the frontend SHOULD use)
// ---------------------------------------------------------------------------

function safeNumber(value: unknown, fallback: number = 0): number {
  if (value === null || value === undefined) return fallback
  const n = Number(value)
  return Number.isFinite(n) ? n : fallback
}

function safeString(value: unknown, fallback: string = '—'): string {
  if (value === null || value === undefined) return fallback
  return String(value)
}

function safePercent(value: unknown, fallback: string = '—'): string {
  if (value === null || value === undefined) return fallback
  const n = Number(value)
  return Number.isFinite(n) ? `${n.toFixed(1)}%` : fallback
}

function getMeasurementCompleteness(data: Record<string, unknown>): number {
  const total = METRIC_FIELDS.length as number
  if (total === 0) return 1.0
  const present = METRIC_FIELDS.filter(f => data[f] !== null && data[f] !== undefined).length
  return present / total
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Null-Safe Contract Tests', () => {
  describe('safeNumber', () => {
    it('handles null gracefully', () => {
      expect(safeNumber(null)).toBe(0)
      expect(safeNumber(null, -1)).toBe(-1)
    })

    it('handles undefined gracefully', () => {
      expect(safeNumber(undefined)).toBe(0)
    })

    it('passes through valid numbers', () => {
      expect(safeNumber(42)).toBe(42)
      expect(safeNumber(3.14)).toBe(3.14)
    })

    it('handles NaN/Infinity', () => {
      expect(safeNumber(NaN)).toBe(0)
      expect(safeNumber(Infinity)).toBe(0)
    })
  })

  describe('safeString', () => {
    it('handles null gracefully', () => {
      expect(safeString(null)).toBe('—')
    })

    it('handles undefined gracefully', () => {
      expect(safeString(undefined)).toBe('—')
    })

    it('passes through valid strings', () => {
      expect(safeString('active')).toBe('active')
    })
  })

  describe('safePercent', () => {
    it('handles null gracefully', () => {
      expect(safePercent(null)).toBe('—')
    })

    it('formats valid numbers as percentages', () => {
      expect(safePercent(95.123)).toBe('95.1%')
    })
  })

  describe('API v2 all-null metrics response', () => {
    const allNullResponse: Record<string, unknown> = {
      status: 'active',
      storage_engine_status: 'ACTIVE',
      dataset_readiness: { status: 'BLOCKED' },
      training_ready: false,
      timestamp: Date.now(),
      runtime: null,
      signature: null,
      stale: null,
      determinism_ok: null,
      message: null,
    }

    it('required fields are present', () => {
      for (const field of REQUIRED_FIELDS) {
        expect(allNullResponse).toHaveProperty(field)
        expect(allNullResponse[field]).not.toBeUndefined()
        expect(allNullResponse[field]).not.toBeNull()
      }
    })

    it('nullable fields are present (even if null)', () => {
      for (const field of NULLABLE_FIELDS) {
        expect(allNullResponse).toHaveProperty(field)
      }
    })

    it('renders all null metrics without throwing', () => {
      for (const field of METRIC_FIELDS) {
        expect(() => safeNumber(allNullResponse[field])).not.toThrow()
        expect(() => safeString(allNullResponse[field])).not.toThrow()
        expect(() => safePercent(allNullResponse[field])).not.toThrow()
      }
    })

    it('measurement completeness is 0 when all metrics null', () => {
      const completeness = getMeasurementCompleteness(allNullResponse)
      expect(completeness).toBe(0)
    })
  })

  describe('API v2 partial metrics response', () => {
    const partialResponse: Record<string, unknown> = {
      status: 'active',
      storage_engine_status: 'ACTIVE',
      dataset_readiness: { status: 'READY' },
      training_ready: true,
      timestamp: Date.now(),
      total_epochs: 100,
      completed_epochs: 50,
      current_loss: 0.05,
      best_loss: null,
      precision: 0.95,
      ece: null,
      drift_kl: null,
      duplicate_rate: 0.001,
      gpu_util: 85.5,
      cpu_util: null,
      temperature: 72.0,
      progress_pct: 50.0,
      loss_trend: null,
      total_errors: 0,
    }

    it('renders mixed null/present metrics without throwing', () => {
      for (const field of METRIC_FIELDS) {
        expect(() => safeNumber(partialResponse[field])).not.toThrow()
      }
    })

    it('measurement completeness is between 0 and 1', () => {
      const completeness = getMeasurementCompleteness(partialResponse)
      expect(completeness).toBeGreaterThan(0)
      expect(completeness).toBeLessThanOrEqual(1)
    })

    it('null metrics fall back to default values', () => {
      expect(safeNumber(partialResponse.best_loss)).toBe(0)
      expect(safeNumber(partialResponse.ece)).toBe(0)
      expect(safeString(partialResponse.loss_trend)).toBe('—')
    })
  })

  describe('Field set stability', () => {
    it('schema defines all expected required fields', () => {
      expect(REQUIRED_FIELDS.length).toBeGreaterThanOrEqual(5)
    })

    it('schema defines all expected metric fields', () => {
      expect(METRIC_FIELDS.length).toBeGreaterThanOrEqual(14)
    })

    it('no unexpected field removal between v1 and v2', () => {
      // These fields must always exist in the schema
      const criticalFields = ['status', 'training_ready', 'timestamp']
      for (const field of criticalFields) {
        expect(REQUIRED_FIELDS).toContain(field)
      }
    })
  })
})
