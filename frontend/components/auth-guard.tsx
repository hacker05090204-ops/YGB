"use client"

import { useEffect } from "react"
import { usePathname, useRouter, useSearchParams } from "next/navigation"

import { buildLoginRedirectTarget } from "@/lib/post-login-redirect"
import { useAuthUser } from "@/hooks/use-auth-user"

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const authUser = useAuthUser()
  const search = searchParams?.toString() ?? ""

  useEffect(() => {
    if (
      authUser.status === "unavailable" &&
      authUser.unavailableReason === "Authentication required"
    ) {
      router.replace(
        buildLoginRedirectTarget(pathname || "/", search ? `?${search}` : "")
      )
    }
  }, [authUser.status, authUser.unavailableReason, pathname, router, search])

  if (authUser.status === "loading") {
    return (
      <div className="min-h-screen bg-[#000000] flex items-center justify-center">
        <div className="text-gray-600 text-sm animate-pulse">
          Checking authentication...
        </div>
      </div>
    )
  }

  if (authUser.status !== "authenticated") {
    if (authUser.unavailableReason === "Authentication required") {
      return null
    }

    return (
      <div className="min-h-screen bg-[#000000] flex items-center justify-center px-6">
        <div className="text-center">
          <p className="text-sm text-gray-300">Session verification unavailable</p>
          <p className="mt-2 text-xs text-gray-500">
            {authUser.unavailableReason || "Backend unreachable"}
          </p>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
