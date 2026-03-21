import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  AUTH_STATE_EVENT,
  credentialedFetch,
  getCookieValue,
  getCsrfToken,
  notifyAuthStateChanged,
  purgeLegacyAuthStorage,
  withCredentialedAuth,
} from '../lib/auth-token'

const realWindow = globalThis.window
const realDocument = globalThis.document
const realFetch = globalThis.fetch

function installBrowserEnv(cookie = '') {
  const listeners: Record<string, Array<(event: Event) => void>> = {}
  const removedSession: string[] = []
  const removedLocal: string[] = []

  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    value: { cookie },
  })

  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      sessionStorage: {
        removeItem: (key: string) => removedSession.push(key),
      },
      localStorage: {
        removeItem: (key: string) => removedLocal.push(key),
      },
      dispatchEvent: (event: Event) => {
        for (const listener of listeners[event.type] ?? []) {
          listener(event)
        }
        return true
      },
      addEventListener: (type: string, listener: (event: Event) => void) => {
        listeners[type] ??= []
        listeners[type].push(listener)
      },
    },
  })

  return { removedSession, removedLocal, listeners }
}

describe('auth-token helpers', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    if (realWindow === undefined) {
      // @ts-expect-error restoring deleted global
      delete globalThis.window
    } else {
      Object.defineProperty(globalThis, 'window', {
        configurable: true,
        value: realWindow,
      })
    }

    if (realDocument === undefined) {
      // @ts-expect-error restoring deleted global
      delete globalThis.document
    } else {
      Object.defineProperty(globalThis, 'document', {
        configurable: true,
        value: realDocument,
      })
    }

    globalThis.fetch = realFetch
  })

  it('returns null when document is unavailable', () => {
    // @ts-expect-error testing non-browser environment
    delete globalThis.document

    expect(getCookieValue('ygb_csrf')).toBeNull()
    expect(getCsrfToken()).toBeNull()
  })

  it('reads and decodes cookie values, including escaped names', () => {
    installBrowserEnv('ygb_csrf=csrf%20token; weird.name=value%2B1')

    expect(getCookieValue('ygb_csrf')).toBe('csrf token')
    expect(getCookieValue('weird.name')).toBe('value+1')
  })

  it('purges legacy auth keys from both storage buckets', () => {
    const { removedSession, removedLocal } = installBrowserEnv()

    purgeLegacyAuthStorage()

    expect(removedSession).toEqual([
      'ygb_token',
      'ygb_jwt',
      'ygb_session',
      'ygb_session_id',
      'ygb_auth_method',
      'ygb_profile',
      'ygb_network',
    ])
    expect(removedLocal).toEqual(removedSession)
  })

  it('dispatches the auth state event in browser contexts', () => {
    installBrowserEnv()
    const handler = vi.fn()
    window.addEventListener(AUTH_STATE_EVENT, handler)

    notifyAuthStateChanged()

    expect(handler).toHaveBeenCalledTimes(1)
    expect(handler.mock.calls[0][0]).toBeInstanceOf(Event)
  })

  it('injects csrf and credentials for unsafe methods', () => {
    installBrowserEnv('ygb_csrf=csrf-123')

    const result = withCredentialedAuth({
      method: 'post',
      headers: { 'Content-Type': 'application/json' },
      cache: 'reload',
    })

    expect(result.method).toBe('POST')
    expect(result.credentials).toBe('include')
    expect(result.cache).toBe('reload')
    expect(new Headers(result.headers).get('X-CSRF-Token')).toBe('csrf-123')
  })

  it('preserves explicit csrf headers and defaults cache for safe methods', () => {
    installBrowserEnv('ygb_csrf=csrf-123')

    const result = withCredentialedAuth({
      headers: { 'X-CSRF-Token': 'preset' },
    })

    expect(result.method).toBe('GET')
    expect(result.cache).toBe('no-store')
    expect(new Headers(result.headers).get('X-CSRF-Token')).toBe('preset')
  })

  it('wraps fetch with credentialed auth options', async () => {
    installBrowserEnv('ygb_csrf=csrf-999')
    const response = new Response(JSON.stringify({ ok: true }), { status: 200 })
    const fetchMock = vi.fn().mockResolvedValue(response)
    globalThis.fetch = fetchMock

    const result = await credentialedFetch('/api/report', { method: 'PATCH' })

    expect(result).toBe(response)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/report')
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: 'PATCH',
      credentials: 'include',
      cache: 'no-store',
    })
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get('X-CSRF-Token')).toBe('csrf-999')
  })
})
