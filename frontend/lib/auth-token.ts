/**
 * Auth Token Utilities — Centralized token retrieval and header building.
 *
 * Checks multiple storage keys in priority order so that any auth flow
 * (session-based, JWT-based, or legacy) is covered without each caller
 * needing to know the storage layout.
 */

const TOKEN_KEYS = ["ygb_token", "ygb_jwt", "ygb_session"] as const;

/**
 * Retrieve the current auth token from browser storage.
 *
 * Priority: sessionStorage first (per-tab isolation), then localStorage.
 * Checks keys: ygb_token, ygb_jwt, ygb_session.
 *
 * @returns The token string, or null if not authenticated.
 */
export function getAuthToken(): string | null {
    if (typeof window === "undefined") return null;

    // Check sessionStorage first (per-tab, higher priority)
    for (const key of TOKEN_KEYS) {
        const val = sessionStorage.getItem(key);
        if (val) return val;
    }

    // Fallback to localStorage (persistent across tabs)
    for (const key of TOKEN_KEYS) {
        const val = localStorage.getItem(key);
        if (val) return val;
    }

    return null;
}

/**
 * Build a Headers object that includes Authorization when a token is available.
 *
 * @param existing - Optional existing headers (Record or Headers) to merge.
 * @returns A new Headers object with Authorization set if token exists.
 */
export function buildAuthHeaders(
    existing?: Record<string, string> | HeadersInit
): Record<string, string> {
    const headers: Record<string, string> = {};

    // Merge existing headers
    if (existing) {
        if (existing instanceof Headers) {
            existing.forEach((value, key) => {
                headers[key] = value;
            });
        } else if (typeof existing === "object" && !Array.isArray(existing)) {
            Object.assign(headers, existing);
        }
    }

    const token = getAuthToken();
    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }

    return headers;
}
