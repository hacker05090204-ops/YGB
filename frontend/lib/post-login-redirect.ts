const POST_LOGIN_REDIRECT_KEY = "ygb_post_login_redirect"

export const DEFAULT_POST_LOGIN_REDIRECT = "/control"

function hasWindow(): boolean {
  return typeof window !== "undefined"
}

export function normalizePostLoginRedirect(
  value: string | null | undefined
): string | null {
  if (!value) {
    return null
  }

  const trimmed = value.trim()
  if (
    !trimmed ||
    trimmed.startsWith("//") ||
    trimmed.includes("\\") ||
    /[\r\n]/.test(trimmed)
  ) {
    return null
  }

  try {
    const base = "http://localhost"
    const parsed = new URL(trimmed, base)
    if (parsed.origin !== base || !parsed.pathname.startsWith("/")) {
      return null
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash}`
  } catch {
    return null
  }
}

export function buildLoginRedirectTarget(
  pathname: string,
  search = ""
): string {
  const currentTarget =
    normalizePostLoginRedirect(`${pathname || "/"}${search}`) ||
    DEFAULT_POST_LOGIN_REDIRECT
  return `/login?next=${encodeURIComponent(currentTarget)}`
}

export function persistPostLoginRedirect(
  value: string | null | undefined
): string | null {
  const normalized = normalizePostLoginRedirect(value)
  if (!hasWindow()) {
    return normalized
  }

  if (normalized) {
    window.sessionStorage.setItem(POST_LOGIN_REDIRECT_KEY, normalized)
  }
  return normalized
}

export function readPostLoginRedirect(): string | null {
  if (!hasWindow()) {
    return null
  }

  return normalizePostLoginRedirect(
    window.sessionStorage.getItem(POST_LOGIN_REDIRECT_KEY)
  )
}

export function clearPostLoginRedirect(): void {
  if (!hasWindow()) {
    return
  }

  window.sessionStorage.removeItem(POST_LOGIN_REDIRECT_KEY)
}

export function consumePostLoginRedirect(
  value: string | null | undefined,
  fallback = DEFAULT_POST_LOGIN_REDIRECT
): string {
  const normalized = normalizePostLoginRedirect(value)
  const target = normalized || readPostLoginRedirect() || fallback
  clearPostLoginRedirect()
  return target
}
