"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"

/**
 * AuthGuard — wraps protected pages.
 * Redirects to /login if no valid token is found in sessionStorage.
 * Shows nothing (blank) during the check to prevent flash of protected content.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
    const router = useRouter()
    const [authorized, setAuthorized] = useState(false)

    useEffect(() => {
        const token = sessionStorage.getItem("ygb_token")
        if (!token) {
            router.replace("/login")
            return
        }
        setAuthorized(true)
    }, [router])

    if (!authorized) {
        return (
            <div className="min-h-screen bg-[#000000] flex items-center justify-center">
                <div className="text-gray-600 text-sm animate-pulse">Checking authentication...</div>
            </div>
        )
    }

    return <>{children}</>
}
