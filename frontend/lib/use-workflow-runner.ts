"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { API_BASE, getWebSocketUrl } from "@/lib/api-base"

type WorkflowMode = "READ_ONLY" | "REAL"

export interface PhaseUpdate {
  type: string
  phase?: number
  name?: string
  status?: string
  duration_ms?: number
  progress?: number
  output?: Record<string, any>
}

export interface BrowserAction {
  type: string
  action?: string
  target?: string
  details?: Record<string, any>
  duration_ms?: number
  timestamp?: string
}

export interface WorkflowResult {
  summary?: {
    total_phases: number
    successful_steps: number
    failed_steps: number
    findings_count: number
    verified_findings_count?: number
    total_duration_ms: number
    report_file?: string
  }
  findings?: any[]
  final_findings?: any[]
  phases?: any[]
}

export function useWorkflowRunner(initialMode: WorkflowMode = "READ_ONLY") {
  const [targetUrl, setTargetUrl] = useState("")
  const [mode, setMode] = useState<WorkflowMode>(initialMode)
  const [isRunning, setIsRunning] = useState(false)
  const [phases, setPhases] = useState<PhaseUpdate[]>([])
  const [browserActions, setBrowserActions] = useState<BrowserAction[]>([])
  const [findings, setFindings] = useState<any[]>([])
  const [currentPhase, setCurrentPhase] = useState(0)
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState<WorkflowResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const reset = useCallback(() => {
    setPhases([])
    setBrowserActions([])
    setFindings([])
    setCurrentPhase(0)
    setProgress(0)
    setResult(null)
    setError(null)
  }, [])

  const stop = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
    setIsRunning(false)
  }, [])

  const start = useCallback(async () => {
    if (!targetUrl.trim() || isRunning) return

    setIsRunning(true)
    reset()

    try {
      const response = await fetch(`${API_BASE}/api/workflow/bounty/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target: targetUrl, mode }),
      })

      if (!response.ok) {
        throw new Error("Failed to start analysis")
      }

      const data = await response.json()
      const socket = new WebSocket(getWebSocketUrl(`/ws/bounty/${data.report_id}`))
      wsRef.current = socket

      socket.onmessage = (event) => {
        const msg = JSON.parse(event.data)
        if (msg.type === "workflow_start") {
          setPhases((prev) => [...prev, { type: "start", ...msg }])
        } else if (msg.type === "phase_start") {
          setCurrentPhase(msg.phase || 0)
          setProgress(msg.progress || 0)
          setPhases((prev) => [...prev, { type: "phase_start", ...msg }])
        } else if (msg.type === "phase_complete") {
          setPhases((prev) => [...prev, { type: "phase_complete", ...msg }])
        } else if (msg.type === "browser_action") {
          setBrowserActions((prev) => [...prev, msg])
        } else if (msg.type === "finding") {
          setFindings((prev) => [...prev, msg])
        } else if (msg.type === "workflow_complete") {
          setProgress(100)
          setPhases((prev) => [...prev, { type: "complete", ...msg }])
        } else if (msg.type === "complete") {
          setResult(msg.result)
          setIsRunning(false)
          socket.close()
        } else if (msg.error) {
          setError(msg.error)
          setIsRunning(false)
          socket.close()
        }
      }

      socket.onerror = () => {
        setError("WebSocket connection failed")
        setIsRunning(false)
      }

      socket.onclose = () => {
        setIsRunning(false)
      }
    } catch (err: any) {
      setError(err.message)
      setIsRunning(false)
    }
  }, [isRunning, mode, reset, targetUrl])

  useEffect(() => {
    return () => {
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [])

  return useMemo(() => ({
    targetUrl,
    setTargetUrl,
    mode,
    setMode,
    isRunning,
    phases,
    browserActions,
    findings,
    currentPhase,
    progress,
    result,
    error,
    start,
    stop,
    reset,
  }), [
    targetUrl,
    mode,
    isRunning,
    phases,
    browserActions,
    findings,
    currentPhase,
    progress,
    result,
    error,
    start,
    stop,
    reset,
  ])
}
