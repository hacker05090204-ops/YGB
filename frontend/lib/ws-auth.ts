/**
 * WebSocket Auth Factory
 *
 * Centralized WebSocket connection using Sec-WebSocket-Protocol bearer auth.
 * Query-string tokens are NOT used (security risk — leaks in logs/referrer).
 */

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

/**
 * Get the current auth token from sessionStorage.
 */
function getToken(): string | null {
    if (typeof window === "undefined") return null;
    return sessionStorage.getItem("ygb_token");
}

/**
 * Create an authenticated WebSocket connection.
 *
 * @param path - WS path (e.g. "/ws/hunting")
 * @param onMessage - Message handler
 * @param onError - Error handler
 * @param onClose - Close handler
 * @returns WebSocket instance or null if no token
 */
export function createAuthWebSocket(
    path: string,
    onMessage?: (event: MessageEvent) => void,
    onError?: (event: Event) => void,
    onClose?: (event: CloseEvent) => void
): WebSocket | null {
    const token = getToken();
    if (!token) {
        console.warn("[WS] No auth token — cannot open WebSocket");
        return null;
    }

    const url = `${WS_BASE}${path}`;

    // Use Sec-WebSocket-Protocol for auth (NOT query string)
    const ws = new WebSocket(url, [`bearer.${token}`]);

    if (onMessage) ws.onmessage = onMessage;
    if (onError) ws.onerror = onError;
    if (onClose) ws.onclose = onClose;

    return ws;
}

export { WS_BASE };
