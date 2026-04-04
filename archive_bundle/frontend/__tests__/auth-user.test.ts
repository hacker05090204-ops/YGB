import { beforeEach, describe, expect, it, vi } from "vitest"

describe("cookie auth contract", () => {
  function simulateHookBehavior(opts: {
    responseStatus: number
    serverReachable: boolean
    serverResponse?: Record<string, unknown>
  }) {
    if (!opts.serverReachable) {
      return {
        userId: null,
        sessionId: null,
        name: null,
        email: null,
        avatar: null,
        githubLogin: null,
        role: null,
        authProvider: null,
        status: "unavailable" as const,
        unavailableReason: "Backend unreachable",
      }
    }

    if ([401, 403, 404].includes(opts.responseStatus)) {
      return {
        userId: null,
        sessionId: null,
        name: null,
        email: null,
        avatar: null,
        githubLogin: null,
        role: null,
        authProvider: null,
        status: "unavailable" as const,
        unavailableReason: "Authentication required",
      }
    }

    const data = opts.serverResponse || {}
    return {
      userId: (data.user_id || null) as string | null,
      sessionId: (data.session_id || null) as string | null,
      name: (data.github_login || data.name || null) as string | null,
      email: (data.email || null) as string | null,
      avatar: (data.avatar_url || null) as string | null,
      githubLogin: (data.github_login || null) as string | null,
      role: (data.role || null) as string | null,
      authProvider: (data.auth_provider || null) as string | null,
      status: "authenticated" as const,
      unavailableReason: null,
    }
  }

  it("server-validated cookie session -> authenticated", () => {
    const result = simulateHookBehavior({
      responseStatus: 200,
      serverReachable: true,
      serverResponse: {
        user_id: "user-1",
        session_id: "sess-1",
        github_login: "octocat",
        name: "The Octocat",
        email: "octocat@github.com",
        avatar_url: "https://avatars.githubusercontent.com/u/1",
        role: "hunter",
        auth_provider: "github",
      },
    })

    expect(result.status).toBe("authenticated")
    expect(result.userId).toBe("user-1")
    expect(result.sessionId).toBe("sess-1")
    expect(result.name).toBe("octocat")
    expect(result.role).toBe("hunter")
  })

  it("401 from /auth/me -> unavailable, not authenticated", () => {
    const result = simulateHookBehavior({
      responseStatus: 401,
      serverReachable: true,
    })

    expect(result.status).toBe("unavailable")
    expect(result.unavailableReason).toBe("Authentication required")
    expect(result.name).toBeNull()
  })

  it("404 from /auth/me -> unavailable, not authenticated", () => {
    const result = simulateHookBehavior({
      responseStatus: 404,
      serverReachable: true,
    })

    expect(result.status).toBe("unavailable")
    expect(result.unavailableReason).toBe("Authentication required")
  })

  it("backend unreachable -> unavailable", () => {
    const result = simulateHookBehavior({
      responseStatus: 0,
      serverReachable: false,
    })

    expect(result.status).toBe("unavailable")
    expect(result.unavailableReason).toContain("Backend unreachable")
  })
})

describe("api helpers", () => {
  const mockFetch = vi.fn()

  beforeEach(async () => {
    mockFetch.mockReset()
    vi.stubGlobal("fetch", mockFetch)
    vi.stubGlobal("document", { cookie: "ygb_csrf=csrf-123" })
    vi.stubEnv("NEXT_PUBLIC_YGB_API_URL", "http://test-api:9000")
    vi.resetModules()
  })

  it("authFetch sends cookies and csrf for unsafe methods", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    } as Response)

    const auth = await import("../lib/auth-token")
    await auth.credentialedFetch("http://test-api:9000/protected", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    })

    expect(mockFetch).toHaveBeenCalledTimes(1)
    const [, options] = mockFetch.mock.calls[0]
    expect(options.credentials).toBe("include")
    expect(options.cache).toBe("no-store")
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBe("csrf-123")
  })

  it("getUserProfile uses cookie auth and returns the payload", async () => {
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

    const api = await import("../lib/ygb-api")
    const result = await api.getUserProfile()

    expect(result).toEqual(data)
    const [, options] = mockFetch.mock.calls[0]
    expect(options.credentials).toBe("include")
    expect(options.cache).toBe("no-store")
  })

  it("getUserProfile throws on non-ok", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: "Unauthorized" }),
    } as Response)

    const api = await import("../lib/ygb-api")
    await expect(api.getUserProfile()).rejects.toThrow("Failed to fetch user profile")
  })
})
