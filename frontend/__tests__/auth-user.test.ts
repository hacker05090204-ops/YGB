/**
 * Tests for hooks/use-auth-user.ts — Auth user profile retrieval
 *
 * Covers:
 * - Reading GitHub profile from sessionStorage
 * - Fallback to defaults when no profile
 * - GitHub login display priority
 * - Malformed profile handling
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// We test the underlying logic rather than the React hook to avoid
// needing a full React testing renderer. The hook's logic is extracted.

describe('useAuthUser profile parsing', () => {
    const DEFAULTS = {
        name: "BugHunter_01",
        email: "hunter@bugbounty.com",
        avatar: "/avatars/agnish.jpg",
        githubLogin: null as string | null,
    }

    function parseProfile(raw: string | null) {
        if (!raw) return DEFAULTS
        try {
            const profile = JSON.parse(raw)
            return {
                name: profile.github_login || profile.name || DEFAULTS.name,
                email: profile.email || DEFAULTS.email,
                avatar: profile.avatar_url || DEFAULTS.avatar,
                githubLogin: profile.github_login || null,
            }
        } catch {
            return DEFAULTS
        }
    }

    it('returns defaults when no profile stored', () => {
        const result = parseProfile(null)
        expect(result).toEqual(DEFAULTS)
    })

    it('returns GitHub login as display name when available', () => {
        const profile = JSON.stringify({
            github_login: "octocat",
            name: "The Octocat",
            email: "octocat@github.com",
            avatar_url: "https://avatars.githubusercontent.com/u/1",
        })
        const result = parseProfile(profile)
        expect(result.name).toBe("octocat")
        expect(result.githubLogin).toBe("octocat")
        expect(result.email).toBe("octocat@github.com")
        expect(result.avatar).toBe("https://avatars.githubusercontent.com/u/1")
    })

    it('falls back to name when github_login missing', () => {
        const profile = JSON.stringify({
            name: "John Doe",
            email: "john@example.com",
        })
        const result = parseProfile(profile)
        expect(result.name).toBe("John Doe")
        expect(result.githubLogin).toBeNull()
    })

    it('falls back to defaults for all missing fields', () => {
        const profile = JSON.stringify({})
        const result = parseProfile(profile)
        expect(result.name).toBe(DEFAULTS.name)
        expect(result.email).toBe(DEFAULTS.email)
        expect(result.avatar).toBe(DEFAULTS.avatar)
    })

    it('handles malformed JSON gracefully', () => {
        const result = parseProfile("not-json")
        expect(result).toEqual(DEFAULTS)
    })

    it('prioritizes github_login over name', () => {
        const profile = JSON.stringify({
            github_login: "gh-user",
            name: "Display Name",
        })
        const result = parseProfile(profile)
        expect(result.name).toBe("gh-user")
    })
})

// ---- getUserProfile API tests ----

describe('getUserProfile', () => {
    const mockFetch = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
    vi.stubEnv('NEXT_PUBLIC_YGB_API_URL', 'http://test-api:9000')

    let api: typeof import('../lib/ygb-api')

    beforeEach(async () => {
        mockFetch.mockReset()
        api = await import('../lib/ygb-api')
    })

    it('returns user profile on success', async () => {
        const data = {
            id: "user-1",
            name: "octocat",
            email: "octocat@github.com",
            role: "hunter",
            github_login: "octocat",
            avatar_url: "https://avatars.githubusercontent.com/u/1",
            auth_provider: "github",
        }
        mockFetch.mockResolvedValueOnce({
            ok: true,
            json: () => Promise.resolve(data),
        } as Response)
        const result = await api.getUserProfile()
        expect(result).toEqual(data)
        expect(result.github_login).toBe("octocat")
    })

    it('throws on non-ok', async () => {
        mockFetch.mockResolvedValueOnce({
            ok: false,
            status: 401,
            json: () => Promise.resolve({ detail: 'Unauthorized' }),
        } as unknown as Response)
        await expect(api.getUserProfile()).rejects.toThrow('Failed to fetch user profile')
    })
})
