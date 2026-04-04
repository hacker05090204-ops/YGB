import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  buildLoginRedirectTarget,
  clearPostLoginRedirect,
  consumePostLoginRedirect,
  normalizePostLoginRedirect,
  persistPostLoginRedirect,
  readPostLoginRedirect,
} from "../lib/post-login-redirect"

function createSessionStorage(): Storage {
  const store = new Map<string, string>()

  return {
    get length() {
      return store.size
    },
    clear() {
      store.clear()
    },
    getItem(key: string) {
      return store.has(key) ? store.get(key)! : null
    },
    key(index: number) {
      return Array.from(store.keys())[index] ?? null
    },
    removeItem(key: string) {
      store.delete(key)
    },
    setItem(key: string, value: string) {
      store.set(key, value)
    },
  }
}

describe("post-login redirect helpers", () => {
  beforeEach(() => {
    vi.stubGlobal("window", {
      sessionStorage: createSessionStorage(),
    })
    clearPostLoginRedirect()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("normalizes safe relative targets", () => {
    expect(normalizePostLoginRedirect("/dashboard?tab=alerts")).toBe(
      "/dashboard?tab=alerts"
    )
    expect(normalizePostLoginRedirect(" /runner#live ")).toBe("/runner#live")
  })

  it("rejects external redirect values", () => {
    expect(normalizePostLoginRedirect("https://evil.example/path")).toBeNull()
    expect(normalizePostLoginRedirect("//evil.example/path")).toBeNull()
    expect(normalizePostLoginRedirect("\\evil")).toBeNull()
  })

  it("builds a login redirect that preserves the current route", () => {
    expect(buildLoginRedirectTarget("/projects", "?filter=active")).toBe(
      "/login?next=%2Fprojects%3Ffilter%3Dactive"
    )
  })

  it("persists and consumes the redirect target for OAuth round trips", () => {
    persistPostLoginRedirect("/security?severity=high")

    expect(readPostLoginRedirect()).toBe("/security?severity=high")
    expect(consumePostLoginRedirect(null)).toBe("/security?severity=high")
    expect(readPostLoginRedirect()).toBeNull()
  })

  it("prefers an explicit query target over stale stored state", () => {
    persistPostLoginRedirect("/runner")

    expect(consumePostLoginRedirect("/dashboard")).toBe("/dashboard")
    expect(readPostLoginRedirect()).toBeNull()
  })
})
