"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import { authFetch, getApiBase } from "@/lib/ygb-api"

interface UseDashboardConnectionArgs {
  authStatus: string
  authUserId: string
  authUserName: string
  isAbortError: (error: unknown) => boolean
}

export function useDashboardConnection({
  authStatus,
  authUserId,
  authUserName,
  isAbortError,
}: UseDashboardConnectionArgs) {
  const [dashboardId, setDashboardId] = useState<string | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const healthFailureCount = useRef(0)
  const healthCheckInFlight = useRef(false)

  const checkServerHealth = useCallback(async () => {
    if (healthCheckInFlight.current) {
      return
    }
    healthCheckInFlight.current = true
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort("health_timeout"), 5000)

    try {
      const response = await fetch(`${getApiBase()}/health`, {
        method: "GET",
        signal: controller.signal,
      })
      if (response.ok) {
        healthFailureCount.current = 0
        setIsConnected(true)
      } else {
        healthFailureCount.current += 1
        if (healthFailureCount.current >= 3) {
          setIsConnected(false)
        }
      }
    } catch (error) {
      if (!isAbortError(error)) {
        console.warn("Health check failed:", error)
      }
      healthFailureCount.current += 1
      if (healthFailureCount.current >= 3) {
        setIsConnected(false)
      }
    } finally {
      clearTimeout(timeout)
      healthCheckInFlight.current = false
    }
  }, [isAbortError])

  const initDashboard = useCallback(async () => {
    if (authStatus !== "authenticated" || !authUserId) {
      return
    }

    setIsLoading(true)
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort("dashboard_init_timeout"), 5000)

    try {
      const response = await authFetch(`${getApiBase()}/api/dashboard/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: authUserId, user_name: authUserName }),
        signal: controller.signal,
      })

      if (response.ok) {
        const data = await response.json()
        setDashboardId(data.dashboard_id)
      } else {
        const statusTag = response.status === 401 || response.status === 403 ? "AUTH_REQUIRED" : "UNAVAILABLE"
        console.warn(`Dashboard init unavailable (${response.status})`)
        setDashboardId(statusTag)
      }
    } catch (error) {
      if (!isAbortError(error)) {
        console.error("Dashboard init failed:", error)
      }
      setDashboardId("UNAVAILABLE")
    } finally {
      clearTimeout(timeout)
      setIsLoading(false)
    }
  }, [authStatus, authUserId, authUserName, isAbortError])

  useEffect(() => {
    if (authStatus === "authenticated" && authUserId) {
      void initDashboard()
    }
  }, [authStatus, authUserId, initDashboard])

  useEffect(() => {
    if (authStatus !== "authenticated" || !authUserId) return
    if (!isConnected) return
    if (dashboardId === "AUTH_REQUIRED") return
    if (!dashboardId || dashboardId === "UNAVAILABLE") {
      void initDashboard()
    }
  }, [authStatus, authUserId, isConnected, dashboardId, initDashboard])

  useEffect(() => {
    void checkServerHealth()
    const interval = setInterval(checkServerHealth, 10000)
    return () => clearInterval(interval)
  }, [checkServerHealth])

  return {
    dashboardId,
    isConnected,
    isLoading,
    initDashboard,
  }
}
