"use client"

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react"

import { API_BASE } from "@/lib/api-base"

type ApiStatus = "checking" | "online" | "offline"

interface LiveDataState {
  apiStatus: ApiStatus
  health: any | null
  g38Status: any | null
  orchestratorStatus: any | null
  lastUpdated: string | null
  refresh: () => Promise<void>
}

const LiveDataContext = createContext<LiveDataState | null>(null)

export function LiveDataProvider({ children }: { children: React.ReactNode }) {
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking")
  const [health, setHealth] = useState<any | null>(null)
  const [g38Status, setG38Status] = useState<any | null>(null)
  const [orchestratorStatus, setOrchestratorStatus] = useState<any | null>(null)
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const inFlightRef = useRef(false)

  const refresh = useCallback(async () => {
    if (inFlightRef.current) return
    inFlightRef.current = true
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    try {
      const [healthRes, g38Res, orchestratorRes] = await Promise.all([
        fetch(`${API_BASE}/api/health`, { signal: controller.signal, cache: "no-store" }),
        fetch(`${API_BASE}/api/g38/status`, { signal: controller.signal, cache: "no-store" }),
        fetch(`${API_BASE}/api/orchestrator/status`, { signal: controller.signal, cache: "no-store" }),
      ])

      if (healthRes.ok) {
        setHealth(await healthRes.json())
        setApiStatus("online")
      } else {
        setApiStatus("offline")
      }

      if (g38Res.ok) {
        setG38Status(await g38Res.json())
      }

      if (orchestratorRes.ok) {
        setOrchestratorStatus(await orchestratorRes.json())
      }

      setLastUpdated(new Date().toISOString())
    } catch (error: any) {
      if (error?.name !== "AbortError") {
        setApiStatus("offline")
      }
    } finally {
      inFlightRef.current = false
    }
  }, [])

  useEffect(() => {
    void refresh()

    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void refresh()
      }
    }, 5000)

    const onVisible = () => {
      if (document.visibilityState === "visible") {
        void refresh()
      }
    }

    document.addEventListener("visibilitychange", onVisible)
    return () => {
      controllerRef.current?.abort()
      window.clearInterval(interval)
      document.removeEventListener("visibilitychange", onVisible)
    }
  }, [refresh])

  const value = useMemo<LiveDataState>(() => ({
    apiStatus,
    health,
    g38Status,
    orchestratorStatus,
    lastUpdated,
    refresh,
  }), [apiStatus, health, g38Status, orchestratorStatus, lastUpdated, refresh])

  return <LiveDataContext.Provider value={value}>{children}</LiveDataContext.Provider>
}

export function useLiveData(): LiveDataState {
  const context = useContext(LiveDataContext)
  if (!context) {
    throw new Error("useLiveData must be used within LiveDataProvider")
  }
  return context
}
