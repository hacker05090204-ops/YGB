/**
 * Browser auth helpers for HttpOnly-cookie sessions.
 *
 * Live auth tokens are never read from browser storage.
 */

export const AUTH_STATE_EVENT = "ygb-auth-changed"

const CSRF_COOKIE_NAME = "ygb_csrf"
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS", "TRACE"])

const LEGACY_STORAGE_KEYS = [
  "ygb_token",
  "ygb_jwt",
  "ygb_session",
  "ygb_session_id",
  "ygb_auth_method",
  "ygb_profile",
  "ygb_network",
] as const

function hasWindow(): boolean {
  return typeof window !== "undefined"
}

export function getCookieValue(name: string): string | null {
  if (typeof document === "undefined") {
    return null
  }

  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

export function getCsrfToken(): string | null {
  return getCookieValue(CSRF_COOKIE_NAME)
}

export function purgeLegacyAuthStorage(): void {
  if (!hasWindow()) {
    return
  }

  for (const key of LEGACY_STORAGE_KEYS) {
    window.sessionStorage.removeItem(key)
    window.localStorage.removeItem(key)
  }
}

export function notifyAuthStateChanged(): void {
  if (!hasWindow()) {
    return
  }

  window.dispatchEvent(new Event(AUTH_STATE_EVENT))
}

export function withCredentialedAuth(options: RequestInit = {}): RequestInit {
  const headers = new Headers(options.headers)
  const method = (options.method ?? "GET").toUpperCase()

  if (!SAFE_METHODS.has(method)) {
    const csrfToken = getCsrfToken()
    if (csrfToken && !headers.has("X-CSRF-Token")) {
      headers.set("X-CSRF-Token", csrfToken)
    }
  }

  return {
    ...options,
    method,
    headers,
    credentials: "include",
    cache: options.cache ?? "no-store",
  }
}

export async function credentialedFetch(
  input: RequestInfo | URL,
  options: RequestInit = {}
): Promise<Response> {
  return fetch(input, withCredentialedAuth(options))
}
