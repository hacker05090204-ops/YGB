"use client"

import { useCallback, useEffect, useState } from "react"

import {
  AUTH_STATE_EVENT,
  credentialedFetch,
  purgeLegacyAuthStorage,
} from "@/lib/auth-token"

export interface AuthUser {
  userId: string | null
  sessionId: string | null
  name: string | null
  email: string | null
  avatar: string | null
  githubLogin: string | null
  role: string | null
  authProvider: string | null
  status: "loading" | "authenticated" | "unavailable"
  unavailableReason: string | null
}

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

const EMPTY_AUTH_USER: AuthUser = {
  userId: null,
  sessionId: null,
  name: null,
  email: null,
  avatar: null,
  githubLogin: null,
  role: null,
  authProvider: null,
  status: "loading",
  unavailableReason: null,
}

export function useAuthUser(): AuthUser {
  const [user, setUser] = useState<AuthUser>(EMPTY_AUTH_USER)

  const fetchUser = useCallback(async () => {
    try {
      const res = await credentialedFetch(`${API_BASE}/auth/me`)

      if (res.status === 401 || res.status === 403 || res.status === 404) {
        setUser({
          ...EMPTY_AUTH_USER,
          status: "unavailable",
          unavailableReason: "Authentication required",
        })
        return
      }

      if (!res.ok) {
        throw new Error(`Auth endpoint returned ${res.status}`)
      }

      const data = await res.json()
      setUser({
        userId: data.user_id || null,
        sessionId: data.session_id || null,
        name: data.github_login || data.name || null,
        email: data.email || null,
        avatar: data.avatar_url || null,
        githubLogin: data.github_login || null,
        role: data.role || null,
        authProvider: data.auth_provider || null,
        status: "authenticated",
        unavailableReason: null,
      })
    } catch (err) {
      setUser({
        ...EMPTY_AUTH_USER,
        status: "unavailable",
        unavailableReason:
          err instanceof Error ? err.message : "Backend unreachable",
      })
    }
  }, [])

  useEffect(() => {
    purgeLegacyAuthStorage()
    void fetchUser()

    const onAuthChange = () => {
      void fetchUser()
    }

    window.addEventListener(AUTH_STATE_EVENT, onAuthChange)
    window.addEventListener("focus", onAuthChange)

    return () => {
      window.removeEventListener(AUTH_STATE_EVENT, onAuthChange)
      window.removeEventListener("focus", onAuthChange)
    }
  }, [fetchUser])

  return user
}
