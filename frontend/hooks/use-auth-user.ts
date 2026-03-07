"use client"

import { useState, useEffect, useCallback } from "react"

export interface AuthUser {
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

/**
 * Retrieve the authenticated user profile from the backend.
 *
 * Source of truth: /auth/me endpoint (always fresh, no cache).
 * Falls back to sessionStorage profile for offline resilience.
 * NEVER returns hardcoded default values.
 * Shows explicit UNAVAILABLE status when backend is unreachable.
 */
export function useAuthUser(): AuthUser {
    const [user, setUser] = useState<AuthUser>({
        name: null,
        email: null,
        avatar: null,
        githubLogin: null,
        role: null,
        authProvider: null,
        status: "loading",
        unavailableReason: null,
    })

    const fetchUser = useCallback(async () => {
        // Try backend /auth/me first (source of truth)
        try {
            const token =
                sessionStorage.getItem("ygb_token") ||
                sessionStorage.getItem("ygb_jwt") ||
                localStorage.getItem("ygb_token") ||
                localStorage.getItem("ygb_jwt")

            if (!token) {
                // No token — try sessionStorage profile as fallback
                const raw = sessionStorage.getItem("ygb_profile")
                if (raw) {
                    // Cached profile is NOT proof of auth — mark unavailable
                    // but preserve profile data for display if UI chooses.
                    const profile = JSON.parse(raw)
                    setUser({
                        name: profile.github_login || profile.name || null,
                        email: profile.email || null,
                        avatar: profile.avatar_url || null,
                        githubLogin: profile.github_login || null,
                        role: profile.role || null,
                        authProvider: profile.auth_provider || null,
                        status: "unavailable",
                        unavailableReason: "Cached profile only — no auth token",
                    })
                    return
                }
                setUser(prev => ({
                    ...prev,
                    status: "unavailable",
                    unavailableReason: "No auth token found",
                }))
                return
            }

            const res = await fetch(`${API_BASE}/auth/me`, {
                headers: { Authorization: `Bearer ${token}` },
                cache: "no-store",
            })

            if (!res.ok) {
                throw new Error(`Auth endpoint returned ${res.status}`)
            }

            const data = await res.json()
            setUser({
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
            // Backend unreachable — try sessionStorage as fallback
            try {
                const raw = sessionStorage.getItem("ygb_profile")
                if (raw) {
                    // Backend unreachable + cached profile ≠ authenticated
                    const profile = JSON.parse(raw)
                    setUser({
                        name: profile.github_login || profile.name || null,
                        email: profile.email || null,
                        avatar: profile.avatar_url || null,
                        githubLogin: profile.github_login || null,
                        role: profile.role || null,
                        authProvider: profile.auth_provider || null,
                        status: "unavailable",
                        unavailableReason: "Backend unreachable — using cached profile",
                    })
                    return
                }
            } catch {
                // sessionStorage also failed
            }
            setUser(prev => ({
                ...prev,
                status: "unavailable",
                unavailableReason: err instanceof Error ? err.message : "Backend unreachable",
            }))
        }
    }, [])

    useEffect(() => {
        fetchUser()

        // Listen for storage changes (login/logout in another tab)
        const onStorage = (e: StorageEvent) => {
            if (e.key === "ygb_token" || e.key === "ygb_jwt" || e.key === "ygb_profile") {
                fetchUser()
            }
        }
        window.addEventListener("storage", onStorage)
        return () => window.removeEventListener("storage", onStorage)
    }, [fetchUser])

    return user
}
