import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const realWebSocket = globalThis.WebSocket

describe('ws-auth helpers', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.unstubAllEnvs()
  })

  afterEach(() => {
    if (realWebSocket === undefined) {
      // @ts-expect-error restoring deleted global
      delete globalThis.WebSocket
    } else {
      Object.defineProperty(globalThis, 'WebSocket', {
        configurable: true,
        value: realWebSocket,
      })
    }
  })

  it('uses the configured websocket base and wires handlers', async () => {
    vi.stubEnv('NEXT_PUBLIC_WS_URL', 'wss://ygb.example')
    const messageHandler = vi.fn()
    const errorHandler = vi.fn()
    const closeHandler = vi.fn()
    const ctor = vi.fn(function (this: Record<string, unknown>, url: string) {
      this.url = url
    }) as unknown as typeof WebSocket

    Object.defineProperty(globalThis, 'WebSocket', {
      configurable: true,
      value: ctor,
    })

    const mod = await import('../lib/ws-auth')
    const ws = mod.createAuthWebSocket('/training', messageHandler, errorHandler, closeHandler)

    expect(mod.WS_BASE).toBe('wss://ygb.example')
    expect(ctor).toHaveBeenCalledWith('wss://ygb.example/training')
    expect((ws as unknown as Record<string, unknown>).onmessage).toBe(messageHandler)
    expect((ws as unknown as Record<string, unknown>).onerror).toBe(errorHandler)
    expect((ws as unknown as Record<string, unknown>).onclose).toBe(closeHandler)
  })

  it('falls back to localhost and leaves handlers unset when omitted', async () => {
    vi.stubEnv('NEXT_PUBLIC_WS_URL', '')
    const ctor = vi.fn(function (this: Record<string, unknown>, url: string) {
      this.url = url
    }) as unknown as typeof WebSocket

    Object.defineProperty(globalThis, 'WebSocket', {
      configurable: true,
      value: ctor,
    })

    const mod = await import('../lib/ws-auth')
    const ws = mod.createAuthWebSocket('/dashboard')

    expect(mod.WS_BASE).toBe('ws://localhost:8000')
    expect(ctor).toHaveBeenCalledWith('ws://localhost:8000/dashboard')
    expect((ws as unknown as Record<string, unknown>).onmessage).toBeUndefined()
    expect((ws as unknown as Record<string, unknown>).onerror).toBeUndefined()
    expect((ws as unknown as Record<string, unknown>).onclose).toBeUndefined()
  })
})
