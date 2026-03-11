"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { getApiBase } from "@/lib/ygb-api"

export type BackendStatus = "checking" | "online" | "offline"

interface BackendStatusState {
  /** Current connection status */
  status: BackendStatus
  /** Last measured round-trip latency in ms (null if never measured) */
  latencyMs: number | null
  /** ISO timestamp of last successful health check */
  lastChecked: string | null
  /** Whether the hook is actively trying to reconnect after failure */
  isReconnecting: boolean
  /** Number of consecutive failed health checks */
  consecutiveFailures: number
  /** Force an immediate health check */
  recheckNow: () => void
}

/**
 * Centralized backend health polling hook with exponential backoff.
 *
 * Replaces per-page duplicated checkHealth/setApiStatus logic with a single
 * reusable hook. On consecutive failures, the polling interval increases
 * (15s → 30s → 60s, capped at 60s) to reduce load. On recovery, the
 * interval resets to the base.
 *
 * @param baseIntervalMs  Normal polling interval (default 15000ms)
 * @param maxIntervalMs   Maximum backoff interval (default 60000ms)
 */
export function useBackendStatus(
  baseIntervalMs = 15_000,
  maxIntervalMs = 60_000,
): BackendStatusState {
  const [status, setStatus] = useState<BackendStatus>("checking")
  const [latencyMs, setLatencyMs] = useState<number | null>(null)
  const [lastChecked, setLastChecked] = useState<string | null>(null)
  const [consecutiveFailures, setConsecutiveFailures] = useState(0)

  const failuresRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  const doCheck = useCallback(async () => {
    const start = performance.now()
    try {
      const res = await fetch(`${getApiBase()}/api/health`, {
        cache: "no-store",
        signal: AbortSignal.timeout(10_000),
      })
      if (!mountedRef.current) return

      const elapsed = Math.round(performance.now() - start)

      if (res.ok) {
        setStatus("online")
        setLatencyMs(elapsed)
        setLastChecked(new Date().toISOString())
        failuresRef.current = 0
        setConsecutiveFailures(0)
      } else {
        failuresRef.current += 1
        setConsecutiveFailures(failuresRef.current)
        setStatus("offline")
      }
    } catch {
      if (!mountedRef.current) return
      failuresRef.current += 1
      setConsecutiveFailures(failuresRef.current)
      setStatus("offline")
    }
  }, [])

  // Schedule next check with backoff
  const scheduleNext = useCallback(() => {
    if (!mountedRef.current) return
    const backoffMultiplier = Math.min(
      Math.pow(2, failuresRef.current),
      maxIntervalMs / baseIntervalMs,
    )
    const interval = Math.min(
      baseIntervalMs * backoffMultiplier,
      maxIntervalMs,
    )
    timerRef.current = setTimeout(async () => {
      await doCheck()
      scheduleNext()
    }, interval)
  }, [baseIntervalMs, maxIntervalMs, doCheck])

  useEffect(() => {
    mountedRef.current = true

    // Initial check
    doCheck().then(() => scheduleNext())

    return () => {
      mountedRef.current = false
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [doCheck, scheduleNext])

  const recheckNow = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    doCheck().then(() => scheduleNext())
  }, [doCheck, scheduleNext])

  return {
    status,
    latencyMs,
    lastChecked,
    isReconnecting: consecutiveFailures > 0 && status === "offline",
    consecutiveFailures,
    recheckNow,
  }
}
