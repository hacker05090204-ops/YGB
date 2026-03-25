export const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

export function getWebSocketUrl(path: string): string {
  if (typeof window !== "undefined") {
    const url = new URL(API_BASE)
    const protocol = url.protocol === "https:" ? "wss:" : "ws:"
    return `${protocol}//${url.host}${path}`
  }

  const url = new URL(API_BASE)
  const protocol = url.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${url.host}${path}`
}

export async function fetchJson<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}
