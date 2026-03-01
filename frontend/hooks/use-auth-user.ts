"use client"

import { useState, useEffect } from "react"

export interface AuthUser {
    name: string
    email: string
    avatar: string
    githubLogin: string | null
}

const DEFAULTS: AuthUser = {
    name: "BugHunter_01",
    email: "hunter@bugbounty.com",
    avatar: "/avatars/agnish.jpg",
    githubLogin: null,
}

/**
 * Retrieve the authenticated user profile from sessionStorage.
 *
 * Source of truth: the `ygb_profile` key written by the login page after
 * GitHub OAuth or email/password login. Falls back to hardcoded defaults
 * when no profile is available (unauthenticated or pre-login).
 *
 * Priority for display name:
 *   1. profile.github_login  (GitHub username — primary identifier)
 *   2. profile.name          (GitHub display name)
 *   3. DEFAULTS.name         (hardcoded fallback)
 */
export function useAuthUser(): AuthUser {
    const [user, setUser] = useState<AuthUser>(DEFAULTS)

    useEffect(() => {
        try {
            const raw = sessionStorage.getItem("ygb_profile")
            if (!raw) return

            const profile = JSON.parse(raw)

            setUser({
                name: profile.github_login || profile.name || DEFAULTS.name,
                email: profile.email || DEFAULTS.email,
                avatar: profile.avatar_url || DEFAULTS.avatar,
                githubLogin: profile.github_login || null,
            })
        } catch {
            // Malformed profile — keep defaults.
        }
    }, [])

    return user
}
