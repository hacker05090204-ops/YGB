/**
 * WebSocket Auth Factory
 *
 * Browser auth relies on HttpOnly cookies sent during the WebSocket handshake.
 * Query-string tokens are never used.
 */

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000"

export function createAuthWebSocket(
  path: string,
  onMessage?: (event: MessageEvent) => void,
  onError?: (event: Event) => void,
  onClose?: (event: CloseEvent) => void
): WebSocket {
  const url = `${WS_BASE}${path}`
  const ws = new WebSocket(url)

  if (onMessage) ws.onmessage = onMessage
  if (onError) ws.onerror = onError
  if (onClose) ws.onclose = onClose

  return ws
}

export { WS_BASE }
