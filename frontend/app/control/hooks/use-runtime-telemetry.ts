"use client"

import { useEffect, useRef, useState } from "react"

import { authFetch, getApiBase } from "@/lib/ygb-api"

export interface AccuracySnapshot {
  precision: number
  recall: number
  ece_score: number
  dup_suppression_rate: number
  scope_compliance: number
}

export interface RuntimeStatus {
  status: string
  runtime?: {
    total_epochs: number
    completed_epochs: number
    current_loss: number
    precision: number
    ece: number
    drift_kl: number
    duplicate_rate: number
    gpu_util: number
    cpu_util: number
    temperature: number
    determinism_status: boolean
    freeze_status: boolean
    mode: string
    progress_pct: number
    loss_trend: number
    wall_clock_unix: number
    monotonic_start_time: number
    training_duration_seconds: number
  }
  determinism_ok?: boolean
  stale?: boolean
  last_update_ms?: number
  signature?: string
  source?: string
  auto_repaired?: boolean
  repair_issues?: string[]
}

export function useRuntimeTelemetry() {
  const [runtimeMode, setRuntimeMode] = useState<"IDLE" | "TRAIN" | "HUNT">("IDLE")
  const [accuracySnapshot, setAccuracySnapshot] = useState<AccuracySnapshot | null>(null)
  const [runtimeStatus, setRuntimeStatus] = useState<RuntimeStatus | null>(null)
  const [liveTime, setLiveTime] = useState<number>(Date.now())
  const [isStalled, setIsStalled] = useState(false)
  const lastTelemetryTs = useRef<number>(0)

  useEffect(() => {
    let inFlight = false

    const fetchAccuracy = async () => {
      if (inFlight) return
      inFlight = true
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort("accuracy_timeout"), 2500)

      try {
        const res = await authFetch(`${getApiBase()}/api/accuracy/snapshot`, {
          signal: controller.signal,
        })
        if (res.ok) {
          const data = await res.json()
          setAccuracySnapshot(data)
        } else {
          setAccuracySnapshot(null)
        }
      } catch {
        setAccuracySnapshot(null)
      } finally {
        clearTimeout(timeout)
        inFlight = false
      }
    }

    void fetchAccuracy()
    const interval = setInterval(fetchAccuracy, 3000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    let inFlight = false

    const fetchRuntimeStatus = async () => {
      if (inFlight) return
      inFlight = true
      const controller = new AbortController()
      const timeout = setTimeout(() => controller.abort("runtime_status_timeout"), 2500)

      try {
        const res = await authFetch(`${getApiBase()}/runtime/status`, {
          signal: controller.signal,
        })
        if (res.ok) {
          const data = await res.json()
          setRuntimeStatus(data)
          if (data.runtime?.training_state === "TRAINING" || data.status === "active") {
            setRuntimeMode("TRAIN")
          } else if (data.status === "idle" || data.runtime?.training_state === "IDLE") {
            setRuntimeMode((prev) => (prev === "TRAIN" ? "IDLE" : prev))
          }
          if (data.runtime?.wall_clock_unix) {
            const newTs = data.runtime.wall_clock_unix
            if (lastTelemetryTs.current > 0 && newTs === lastTelemetryTs.current) {
              const elapsed = Date.now() / 1000 - newTs
              setIsStalled(elapsed > 30)
            } else {
              setIsStalled(false)
            }
            lastTelemetryTs.current = newTs
          }
        } else {
          setRuntimeStatus({ status: "error", stale: true })
          setIsStalled(false)
          lastTelemetryTs.current = 0
        }
      } catch {
        setRuntimeStatus({ status: "error", stale: true })
        setIsStalled(false)
        lastTelemetryTs.current = 0
      } finally {
        clearTimeout(timeout)
        inFlight = false
      }
    }

    void fetchRuntimeStatus()
    const interval = setInterval(fetchRuntimeStatus, 3000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const tick = setInterval(() => setLiveTime(Date.now()), 1000)
    return () => clearInterval(tick)
  }, [])

  return {
    runtimeMode,
    setRuntimeMode,
    accuracySnapshot,
    runtimeStatus,
    liveTime,
    isStalled,
  }
}
