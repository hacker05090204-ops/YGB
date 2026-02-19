/**
 * Tests for lib/ygb-api.ts — YGB API Client
 *
 * Tests all exported API functions with mocked fetch.
 * Covers: success paths, error paths, query param handling.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mock fetch globally before importing the module
const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

// Mock process.env
vi.stubEnv('NEXT_PUBLIC_YGB_API_URL', 'http://test-api:9000')

import {
    getPhases,
    getHunterModules,
    runPhase,
    runHunterModule,
    checkHealth,
    getStorageStats,
    getDiskStatus,
    getLifecycleStatus,
    getDeletePreview,
    getVideoList,
} from '../lib/ygb-api'

function mockOk(data: unknown) {
    return { ok: true, json: () => Promise.resolve(data) } as Response
}

function mockError(status: number, detail?: string) {
    return {
        ok: false,
        status,
        json: () => Promise.resolve({ detail: detail || 'Error' }),
    } as unknown as Response
}

beforeEach(() => {
    mockFetch.mockReset()
})

// ---- GET endpoints ----

describe('getPhases', () => {
    it('returns phases on success', async () => {
        const data = [{ name: 'phase01', path: '/p01', has_tests: true }]
        mockFetch.mockResolvedValueOnce(mockOk(data))
        const result = await getPhases()
        expect(result).toEqual(data)
        expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/api/phases'))
    })

    it('throws on non-ok', async () => {
        mockFetch.mockResolvedValueOnce(mockError(500))
        await expect(getPhases()).rejects.toThrow('Failed to fetch phases')
    })
})

describe('getHunterModules', () => {
    it('returns modules on success', async () => {
        const data = [{ name: 'mod1', path: '/m1', files: ['a.py'] }]
        mockFetch.mockResolvedValueOnce(mockOk(data))
        const result = await getHunterModules()
        expect(result).toEqual(data)
    })

    it('throws on non-ok', async () => {
        mockFetch.mockResolvedValueOnce(mockError(500))
        await expect(getHunterModules()).rejects.toThrow('Failed to fetch hunter modules')
    })
})

describe('checkHealth', () => {
    it('returns health on success', async () => {
        const data = { status: 'ok', ygb_root: '/ygb', python_phases: 5, hunter_modules: 3 }
        mockFetch.mockResolvedValueOnce(mockOk(data))
        const result = await checkHealth()
        expect(result).toEqual(data)
    })

    it('throws on non-ok', async () => {
        mockFetch.mockResolvedValueOnce(mockError(503))
        await expect(checkHealth()).rejects.toThrow('API server not available')
    })
})

// ---- POST endpoints ----

describe('runPhase', () => {
    it('runs phase and returns result', async () => {
        const data = { status: 'success', stdout: 'ok', stderr: '', return_code: 0, phase: 'p01' }
        mockFetch.mockResolvedValueOnce(mockOk(data))
        const result = await runPhase('phase01')
        expect(result).toEqual(data)
        expect(mockFetch).toHaveBeenCalledWith(
            expect.stringContaining('/api/run-phase'),
            expect.objectContaining({
                method: 'POST',
                body: JSON.stringify({ phase: 'phase01' }),
            })
        )
    })

    it('throws with detail on error', async () => {
        mockFetch.mockResolvedValueOnce(mockError(400, 'Phase not found'))
        await expect(runPhase('bad')).rejects.toThrow('Phase not found')
    })
})

describe('runHunterModule', () => {
    it('runs module and returns result', async () => {
        const data = { status: 'success', stdout: 'ok', stderr: '', return_code: 0, module: 'm1' }
        mockFetch.mockResolvedValueOnce(mockOk(data))
        const result = await runHunterModule('mod1')
        expect(result).toEqual(data)
        expect(mockFetch).toHaveBeenCalledWith(
            expect.stringContaining('/api/run-hunter'),
            expect.objectContaining({
                method: 'POST',
                body: JSON.stringify({ module: 'mod1' }),
            })
        )
    })

    it('throws with detail on error', async () => {
        mockFetch.mockResolvedValueOnce(mockError(400, 'Module not found'))
        await expect(runHunterModule('bad')).rejects.toThrow('Module not found')
    })
})

// ---- Storage endpoints ----

describe('getStorageStats', () => {
    it('returns stats on success', async () => {
        const data = { initialized: true, hdd_root: '/hdd', entity_counts: {}, disk_usage: {} }
        mockFetch.mockResolvedValueOnce(mockOk(data))
        const result = await getStorageStats()
        expect(result).toEqual(data)
    })

    it('throws on non-ok', async () => {
        mockFetch.mockResolvedValueOnce(mockError(500))
        await expect(getStorageStats()).rejects.toThrow('Failed to fetch storage stats')
    })
})

describe('getDiskStatus', () => {
    it('returns disk status on success', async () => {
        const data = { status: {}, breakdown: {}, index_health: {}, alerts: [] }
        mockFetch.mockResolvedValueOnce(mockOk(data))
        const result = await getDiskStatus()
        expect(result).toEqual(data)
    })

    it('throws on non-ok', async () => {
        mockFetch.mockResolvedValueOnce(mockError(500))
        await expect(getDiskStatus()).rejects.toThrow('Failed to fetch disk status')
    })
})

describe('getLifecycleStatus', () => {
    it('returns lifecycle on success', async () => {
        const data = { deletion_preview: [], eligible_count: 0 }
        mockFetch.mockResolvedValueOnce(mockOk(data))
        const result = await getLifecycleStatus()
        expect(result).toEqual(data)
    })

    it('throws on non-ok', async () => {
        mockFetch.mockResolvedValueOnce(mockError(500))
        await expect(getLifecycleStatus()).rejects.toThrow('Failed to fetch lifecycle status')
    })
})

describe('getDeletePreview', () => {
    it('fetches without entity type', async () => {
        mockFetch.mockResolvedValueOnce(mockOk({ previews: [] }))
        await getDeletePreview()
        expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/api/storage/delete-preview'))
        expect(mockFetch).toHaveBeenCalledWith(expect.not.stringContaining('entity_type='))
    })

    it('fetches with entity type query param', async () => {
        mockFetch.mockResolvedValueOnce(mockOk({ previews: [] }))
        await getDeletePreview('logs')
        expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('entity_type=logs'))
    })

    it('throws on non-ok', async () => {
        mockFetch.mockResolvedValueOnce(mockError(500))
        await expect(getDeletePreview()).rejects.toThrow('Failed to fetch delete preview')
    })
})

describe('getVideoList', () => {
    it('fetches without user id', async () => {
        mockFetch.mockResolvedValueOnce(mockOk({ videos: [] }))
        await getVideoList()
        expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/api/video/list'))
        expect(mockFetch).toHaveBeenCalledWith(expect.not.stringContaining('user_id='))
    })

    it('fetches with user id query param', async () => {
        mockFetch.mockResolvedValueOnce(mockOk({ videos: [] }))
        await getVideoList('u1')
        expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('user_id=u1'))
    })

    it('throws on non-ok', async () => {
        mockFetch.mockResolvedValueOnce(mockError(500))
        await expect(getVideoList()).rejects.toThrow('Failed to fetch video list')
    })
})
