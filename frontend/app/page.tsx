"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import Link from "next/link"
import {
  CheckCircle,
  XCircle,
  Loader2,
  ChevronDown,
  ChevronRight,
  ArrowRight,
  Play,
  Square,
  Box,
  Sparkles,
  Globe,
  Eye,
  MousePointer,
  Camera,
  Shield,
  AlertTriangle,
  Activity,
  Zap,
  Clock,
  Brain,
  Cpu,
  Power
} from "lucide-react"

import { ScrollArea } from "@/components/ui/scroll-area"
import { LiquidMetalButton } from "@/components/ui/liquid-metal"

interface PhaseUpdate {
  type: string
  phase?: number
  name?: string
  status?: string
  duration_ms?: number
  progress?: number
  output?: Record<string, any>
}

interface BrowserAction {
  type: string
  action?: string
  target?: string
  details?: Record<string, any>
  duration_ms?: number
  timestamp?: string
}

interface WorkflowResult {
  summary?: {
    total_phases: number
    successful_steps: number
    failed_steps: number
    findings_count: number
    total_duration_ms: number
    report_file?: string
  }
  findings?: any[]
  phases?: any[]
}

interface G38Status {
  available: boolean
  auto_training?: {
    state: string
    is_training: boolean
    epoch: number
    idle_seconds: number
    power_connected: boolean
    scan_active: boolean
    gpu_available: boolean
    events_count: number
    last_event: string | null
    progress?: number  // Training progress percentage (0-100)
    total_epochs?: number  // Total epochs for training
  }
  guards?: {
    main_guards: number
    all_verified: boolean
    message: string
  }
}

const API_BASE = "http://localhost:8000"

export default function Home() {
  const containerRef = useRef(null)
  const phaseLogRef = useRef<HTMLDivElement>(null)
  const browserLogRef = useRef<HTMLDivElement>(null)

  const [target, setTarget] = useState("")
  const mode = "REAL" // Always use REAL mode for full browser automation
  const [apiStatus, setApiStatus] = useState<"checking" | "online" | "offline">("checking")
  const [urlError, setUrlError] = useState<string | null>(null)
  const [showConnectionDetails, setShowConnectionDetails] = useState(false)
  const [guardsExpanded, setGuardsExpanded] = useState(false)

  const [isRunning, setIsRunning] = useState(false)
  const [phases, setPhases] = useState<PhaseUpdate[]>([])
  const [browserActions, setBrowserActions] = useState<BrowserAction[]>([])
  const [findings, setFindings] = useState<any[]>([])
  const [currentPhase, setCurrentPhase] = useState(0)
  const [progress, setProgress] = useState(0)
  const [result, setResult] = useState<WorkflowResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [g38Status, setG38Status] = useState<G38Status | null>(null)

  const wsRef = useRef<WebSocket | null>(null)

  // Check API
  useEffect(() => {
    async function checkAPI() {
      try {
        const res = await fetch(`${API_BASE}/api/health`)
        if (res.ok) {
          setApiStatus("online")
        } else {
          setApiStatus("offline")
        }
      } catch {
        setApiStatus("offline")
      }
    }
    checkAPI()
  }, [])

  // Fetch G38 status periodically
  useEffect(() => {
    async function fetchG38Status() {
      try {
        const res = await fetch(`${API_BASE}/api/g38/status`)
        if (res.ok) {
          const data = await res.json()
          setG38Status(data)
        }
      } catch {
        // G38 not available
      }
    }

    fetchG38Status()
    const interval = setInterval(fetchG38Status, 5000) // Refresh every 5 seconds
    return () => clearInterval(interval)
  }, [])

  // Auto-scroll logs
  useEffect(() => {
    phaseLogRef.current?.scrollTo({ top: phaseLogRef.current.scrollHeight, behavior: 'smooth' })
  }, [phases])

  useEffect(() => {
    browserLogRef.current?.scrollTo({ top: browserLogRef.current.scrollHeight, behavior: 'smooth' })
  }, [browserActions])

  const startAnalysis = useCallback(async () => {
    if (isRunning) return
    if (!target.trim()) {
      setUrlError("Please enter a target URL to begin security analysis")
      return
    }
    setUrlError(null)

    setIsRunning(true)
    setPhases([])
    setBrowserActions([])
    setFindings([])
    setCurrentPhase(0)
    setProgress(0)
    setResult(null)
    setError(null)

    try {
      // Start workflow via REST API - uses phase_runner.py
      const res = await fetch(`${API_BASE}/api/workflow/bounty/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target, mode })
      })

      if (!res.ok) throw new Error("Failed to start analysis")
      const data = await res.json()

      // Connect WebSocket for real-time updates
      const ws = new WebSocket(`ws://localhost:8000/ws/bounty/${data.report_id}`)
      wsRef.current = ws

      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data)

        if (msg.type === "workflow_start") {
          setPhases(prev => [...prev, { type: "start", ...msg }])
        }
        else if (msg.type === "phase_start") {
          setCurrentPhase(msg.phase || 0)
          setProgress(msg.progress || 0)
          setPhases(prev => [...prev, { type: "phase_start", ...msg }])
        }
        else if (msg.type === "phase_complete") {
          setPhases(prev => [...prev, { type: "phase_complete", ...msg }])
        }
        else if (msg.type === "browser_action") {
          setBrowserActions(prev => [...prev, msg])
        }
        else if (msg.type === "finding") {
          setFindings(prev => [...prev, msg])
        }
        else if (msg.type === "workflow_complete") {
          setProgress(100)
          setPhases(prev => [...prev, { type: "complete", ...msg }])
        }
        else if (msg.type === "complete") {
          setResult(msg.result)
          setIsRunning(false)
          ws.close()
        }
        else if (msg.error) {
          setError(msg.error)
          setIsRunning(false)
          ws.close()
        }
      }

      ws.onerror = () => {
        setError("WebSocket connection failed")
        setIsRunning(false)
      }

      ws.onclose = () => {
        setIsRunning(false)
      }

    } catch (err: any) {
      setError(err.message)
      setIsRunning(false)
    }
  }, [target, mode, isRunning])

  const stopAnalysis = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
    }
    setIsRunning(false)
  }, [])

  const getActionIcon = (action: string) => {
    switch (action) {
      case "NAVIGATE": return <Globe className="w-4 h-4 text-blue-400" />
      case "CLICK": return <MousePointer className="w-4 h-4 text-green-400" />
      case "SCREENSHOT": return <Camera className="w-4 h-4 text-orange-400" />
      case "INSPECT": return <Eye className="w-4 h-4 text-yellow-400" />
      case "EXTRACT": return <Zap className="w-4 h-4 text-pink-400" />
      case "BROWSER_START": return <Play className="w-4 h-4 text-green-400" />
      case "CRAWL": return <Activity className="w-4 h-4 text-cyan-400" />
      case "XSS_TEST": return <AlertTriangle className="w-4 h-4 text-red-400" />
      default: return <Activity className="w-4 h-4 text-gray-400" />
    }
  }

  const getSeverityColor = (severity: string) => {
    switch (severity?.toUpperCase()) {
      case "CRITICAL": return "bg-red-500 text-white"
      case "HIGH": return "bg-orange-500 text-white"
      case "MEDIUM": return "bg-yellow-500 text-black"
      case "LOW": return "bg-blue-500 text-white"
      case "INFO": return "bg-gray-500 text-white"
      default: return "bg-gray-500 text-white"
    }
  }

  return (
    <div className="min-h-screen bg-[#000000] text-[#FAFAFA] selection:bg-white/20 overflow-x-hidden" ref={containerRef}>

      {/* Ambient Glow */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-[-50%] left-[-20%] w-[80vw] h-[80vh] bg-gradient-radial from-white/[0.03] via-transparent to-transparent rounded-full blur-3xl" />
        <div className="absolute bottom-[-30%] right-[-10%] w-[60vw] h-[60vh] bg-gradient-radial from-white/[0.02] via-transparent to-transparent rounded-full blur-3xl" />
      </div>

      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-[#000000]/80 backdrop-blur-2xl border-b border-white/[0.06]">
        <div className="max-w-[1400px] mx-auto px-6 md:px-12 lg:px-24">
          <div className="h-16 flex items-center justify-between">

            {/* Logo */}
            <Link href="/" className="flex items-center gap-3 group">
              <div className="w-10 h-10 bg-gradient-to-br from-white to-[#A3A3A3] rounded-xl flex items-center justify-center shadow-[0_0_20px_rgba(255,255,255,0.1)] group-hover:shadow-[0_0_30px_rgba(255,255,255,0.15)] transition-shadow">
                <Box className="w-5 h-5 text-[#000000]" />
              </div>
              <span className="text-xl font-bold tracking-tight">YGB</span>
            </Link>

            {/* Status & Links */}
            <div className="flex items-center gap-5">
              <div className="relative">
                <button
                  onClick={() => setShowConnectionDetails(!showConnectionDetails)}
                  className={`flex items-center gap-2 px-4 py-2 rounded-full text-xs font-medium border transition-all cursor-pointer ${apiStatus === "online"
                    ? "bg-white/[0.03] border-white/[0.1] text-[#FAFAFA] shadow-[0_0_15px_rgba(255,255,255,0.05)] hover:bg-white/[0.06]"
                    : "bg-[#171717] border-[#262626] text-[#525252] hover:bg-[#1a1a1a]"
                    }`}
                >
                  <div className={`w-2 h-2 rounded-full ${apiStatus === "online" ? "bg-[#FAFAFA] shadow-[0_0_8px_rgba(255,255,255,0.5)]" : "bg-[#404040]"}`} />
                  {apiStatus === "online" ? "Connected" : "Offline"}
                  <ChevronDown className={`w-3 h-3 transition-transform ${showConnectionDetails ? "rotate-180" : ""}`} />
                </button>
                {showConnectionDetails && (
                  <div className="absolute right-0 top-full mt-2 w-64 bg-[#0A0A0A] border border-white/[0.1] rounded-xl p-4 shadow-2xl z-[100]">
                    <h4 className="text-xs font-semibold text-[#FAFAFA] mb-3">Connection Details</h4>
                    <div className="space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="text-xs text-[#525252]">API Endpoint</span>
                        <span className="text-xs text-[#A3A3A3] font-mono">localhost:8000</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-xs text-[#525252]">Status</span>
                        <span className={`text-xs font-medium ${apiStatus === "online" ? "text-green-400" : "text-red-400"}`}>
                          {apiStatus === "online" ? "● Online" : "● Offline"}
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-xs text-[#525252]">Protocol</span>
                        <span className="text-xs text-[#A3A3A3]">HTTP + WebSocket</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-xs text-[#525252]">G38 Training</span>
                        <span className={`text-xs font-medium ${g38Status?.available ? "text-green-400" : "text-[#525252]"}`}>
                          {g38Status?.available ? "● Available" : "● Unavailable"}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
              <Link href="/training" className="hidden md:flex items-center gap-2 text-sm text-[#525252] hover:text-[#FAFAFA] transition-colors group">
                <Brain className="w-4 h-4" />
                Training
              </Link>
              <Link href="/dashboard" className="hidden md:flex items-center gap-2 text-sm text-[#525252] hover:text-[#FAFAFA] transition-colors group">
                Dashboard
                <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative pt-40 pb-16 px-6 md:px-12 lg:px-24">
        <div className="absolute top-32 left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-gradient-radial from-white/[0.04] via-transparent to-transparent rounded-full blur-3xl pointer-events-none" />

        <div className="max-w-[1400px] mx-auto relative">
          <div className="max-w-3xl">
            {/* Badge */}
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/[0.03] border border-white/[0.08] text-xs text-[#A3A3A3] mb-10 shadow-[0_0_20px_rgba(255,255,255,0.03)]">
              <Sparkles className="w-3.5 h-3.5" />
              48 phases ready • Chromium/Edge Headless
            </div>

            {/* Title */}
            <h1 className="text-[clamp(3rem,10vw,7rem)] font-bold leading-[0.9] tracking-[-0.04em] relative">
              <span className="relative">
                Security
                <span className="absolute inset-0 blur-2xl bg-white/10 -z-10" />
              </span>
              <br />
              <span className="text-[#525252]">Analysis</span>
            </h1>

            <p className="mt-10 text-lg md:text-xl text-[#525252] max-w-xl leading-relaxed">
              Execute 50 security phases with real browser automation. Watch Edge/Chrome analyze your target in real-time.
            </p>
          </div>

          {/* Input Section */}
          <div className="mt-16 max-w-2xl">
            <div className="relative group">
              <div className="absolute -inset-0.5 bg-gradient-to-r from-white/10 via-white/5 to-white/10 rounded-2xl blur opacity-0 group-focus-within:opacity-100 transition-opacity duration-500" />
              <input
                type="url"
                placeholder="https://target-domain.com"
                value={target}
                onChange={(e) => { setTarget(e.target.value); if (urlError) setUrlError(null) }}
                disabled={isRunning}
                className={`relative w-full h-16 px-6 bg-[#0A0A0A] border rounded-2xl text-[#FAFAFA] text-lg placeholder:text-[#404040] focus:outline-none focus:border-white/20 transition-all disabled:opacity-50 ${urlError ? "border-red-500/50" : "border-white/[0.08]"}`}
              />
              {urlError && (
                <p className="absolute -bottom-7 left-2 text-xs text-red-400 flex items-center gap-1.5">
                  <AlertTriangle className="w-3 h-3" />
                  {urlError}
                </p>
              )}
            </div>

            {/* Button */}
            <div className="flex mt-6">
              {isRunning ? (
                <LiquidMetalButton
                  onClick={stopAnalysis}
                  icon={<Square className="w-5 h-5" />}
                  metalConfig={{ colorBack: "#7f1d1d", colorTint: "#f87171" }}
                  className="flex-1"
                  size="md"
                >
                  Stop Analysis
                </LiquidMetalButton>
              ) : (
                <LiquidMetalButton
                  onClick={startAnalysis}
                  disabled={!target.trim() || apiStatus !== "online"}
                  icon={<Play className="w-5 h-5" />}
                  metalConfig={{ colorBack: "#262626", colorTint: "#FAFAFA" }}
                  className="flex-1"
                  size="md"
                >
                  Start Security Analysis
                </LiquidMetalButton>
              )}
            </div>

            {/* Progress Bar */}
            {isRunning && (
              <div className="mt-6">
                <div className="flex justify-between text-xs text-[#525252] mb-2">
                  <span>Phase {currentPhase} / 50</span>
                  <span>{progress.toFixed(1)}%</span>
                </div>
                <div className="h-2 bg-[#171717] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-[#FAFAFA] to-[#737373] transition-all duration-300"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* G38 Auto-Training Status */}
          {g38Status?.available && (
            <div className="mt-8 bg-[#0A0A0A] border border-white/[0.06] rounded-2xl p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${g38Status.auto_training?.is_training
                    ? "bg-gradient-to-br from-purple-500/30 to-blue-500/30 border border-purple-500/40"
                    : "bg-gradient-to-br from-purple-500/20 to-blue-500/20 border border-purple-500/30"
                    }`}>
                    <Brain className={`w-5 h-5 ${g38Status.auto_training?.is_training ? "text-purple-300 animate-pulse" : "text-purple-400"
                      }`} />
                  </div>
                  <div>
                    <h3 className="font-semibold">G38 Auto-Training</h3>
                    <p className="text-xs text-[#525252]">
                      {g38Status.auto_training?.is_training
                        ? `AI Training Started ${g38Status.auto_training?.progress || 0}% done`
                        : "Device Idle - Ready to train when idle"}
                    </p>
                  </div>
                </div>
                <div className={`px-3 py-1.5 rounded-full text-xs font-medium flex items-center gap-2 ${g38Status.auto_training?.is_training
                  ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                  : "bg-white/[0.03] text-[#737373] border border-white/[0.06]"
                  }`}>
                  <div className={`w-2 h-2 rounded-full ${g38Status.auto_training?.is_training
                    ? "bg-purple-400 animate-pulse"
                    : "bg-[#404040]"
                    }`} />
                  {g38Status.auto_training?.is_training
                    ? `TRAINING ${g38Status.auto_training?.progress || 0}%`
                    : g38Status.auto_training?.state || "IDLE"}
                </div>
              </div>

              {/* Training Progress Bar */}
              {g38Status.auto_training?.is_training && (
                <div className="mb-4">
                  <div className="flex justify-between text-xs text-[#525252] mb-2">
                    <span>Epoch {g38Status.auto_training?.epoch || 0} / {g38Status.auto_training?.total_epochs || 0}</span>
                    <span>{g38Status.auto_training?.progress || 0}%</span>
                  </div>
                  <div className="h-2 bg-[#171717] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-purple-500 to-blue-500 transition-all duration-500"
                      style={{ width: `${g38Status.auto_training?.progress || 0}%` }}
                    />
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="p-3 rounded-xl bg-[#171717] border border-white/[0.04]">
                  <div className="flex items-center gap-2 text-[#525252] text-xs mb-1">
                    <Clock className="w-3 h-3" />
                    Idle Time
                  </div>
                  <div className="text-lg font-bold text-[#FAFAFA]">{g38Status.auto_training?.idle_seconds || 0}s</div>
                </div>
                <div className="p-3 rounded-xl bg-[#171717] border border-white/[0.04]">
                  <div className="flex items-center gap-2 text-[#525252] text-xs mb-1">
                    <Zap className="w-3 h-3" />
                    Epoch
                  </div>
                  <div className="text-lg font-bold text-[#FAFAFA]">{g38Status.auto_training?.epoch || 0}</div>
                </div>
                <div className="p-3 rounded-xl bg-[#171717] border border-white/[0.04]">
                  <div className="flex items-center gap-2 text-[#525252] text-xs mb-1">
                    <Cpu className="w-3 h-3" />
                    GPU
                  </div>
                  <div className={`text-lg font-bold ${g38Status.auto_training?.gpu_available ? "text-green-400" : "text-[#525252]"
                    }`}>{g38Status.auto_training?.gpu_available ? "Available" : "CPU"}</div>
                </div>
                <div className="p-3 rounded-xl bg-[#171717] border border-white/[0.04]">
                  <div className="flex items-center gap-2 text-[#525252] text-xs mb-1">
                    <Power className="w-3 h-3" />
                    Power
                  </div>
                  <div className={`text-lg font-bold ${g38Status.auto_training?.power_connected ? "text-green-400" : "text-yellow-400"
                    }`}>{g38Status.auto_training?.power_connected ? "Connected" : "Battery"}</div>
                </div>
              </div>

              {g38Status.guards && (
                <div className="mt-4">
                  <button
                    onClick={() => setGuardsExpanded(!guardsExpanded)}
                    className="w-full flex items-center justify-between p-3 rounded-xl bg-[#171717] border border-white/[0.04] hover:bg-[#1c1c1c] hover:border-white/[0.08] transition-all cursor-pointer"
                  >
                    <div className="flex items-center gap-2">
                      <Shield className="w-4 h-4 text-green-400" />
                      <span className="text-sm text-[#A3A3A3]">{g38Status.guards.main_guards} Guards</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs ${g38Status.guards.all_verified ? "text-green-400" : "text-red-400"}`}>
                        {g38Status.guards.all_verified ? "✓ All Verified" : "⚠ Guard Failure"}
                      </span>
                      <ChevronDown className={`w-3.5 h-3.5 text-[#525252] transition-transform ${guardsExpanded ? "rotate-180" : ""}`} />
                    </div>
                  </button>
                  {guardsExpanded && (
                    <div className="mt-2 p-4 rounded-xl bg-[#0f0f0f] border border-white/[0.04] space-y-2 animate-in slide-in-from-top-1 duration-200">
                      {["Governance Authority", "Scope Validator", "Rate Limiter", "Session Integrity", "Replay Attack Guard",
                        "Browser Isolation", "CVE Signature Verifier", "Training Freeze Lock", "Determinism Checker",
                        "VRAM Safety Monitor", "Credential Vault"].slice(0, g38Status.guards.main_guards).map((guard, i) => (
                          <div key={i} className="flex items-center justify-between py-1.5 px-2 rounded-lg hover:bg-white/[0.02] transition-colors">
                            <div className="flex items-center gap-2">
                              <div className={`w-1.5 h-1.5 rounded-full ${g38Status.guards!.all_verified ? "bg-green-400" : i < 9 ? "bg-green-400" : "bg-red-400"}`} />
                              <span className="text-xs text-[#A3A3A3]">{guard}</span>
                            </div>
                            <span className="text-[10px] text-[#525252] font-mono">G{(i + 1).toString().padStart(2, '0')}</span>
                          </div>
                        ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </section>

      {/* Execution Panel */}
      <section className="relative px-6 md:px-12 lg:px-24 pb-32">
        <div className="max-w-[1400px] mx-auto">

          {/* Split View */}
          <div className="grid gap-6 lg:grid-cols-[1fr_400px]">

            {/* Left: Phase Execution */}
            <div className="relative group">
              <div className="absolute -inset-px bg-gradient-to-b from-white/[0.08] to-transparent rounded-3xl opacity-0 group-hover:opacity-100 transition-opacity" />
              <div className="relative bg-[#0A0A0A] border border-white/[0.06] rounded-3xl overflow-hidden">
                <div className="px-8 py-6 border-b border-white/[0.06] flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-semibold flex items-center gap-3">
                      <Activity className="w-5 h-5 text-[#737373]" />
                      Execution Log
                    </h2>
                    <p className="text-sm text-[#404040] mt-1">{phases.filter(p => p.type === "phase_complete").length} phases completed</p>
                  </div>
                  {isRunning && (
                    <div className="flex items-center gap-3 px-4 py-2 rounded-full bg-white/[0.03] border border-white/[0.06]">
                      <div className="w-2 h-2 rounded-full bg-[#FAFAFA] animate-pulse shadow-[0_0_8px_rgba(255,255,255,0.5)]" />
                      <span className="text-sm text-[#737373]">Running</span>
                    </div>
                  )}
                </div>

                <ScrollArea className="h-[400px]">
                  <div className="p-6 space-y-2" ref={phaseLogRef}>
                    {phases.length === 0 ? (
                      <div className="flex flex-col items-center justify-center h-[300px]">
                        <div className="w-20 h-20 rounded-3xl bg-gradient-to-br from-white/[0.05] to-transparent border border-white/[0.06] flex items-center justify-center mb-8">
                          <Play className="w-10 h-10 text-[#404040]" />
                        </div>
                        <p className="text-[#525252] text-xl font-medium">Ready to analyze</p>
                        <p className="text-[#404040] text-sm mt-3">Enter a URL and click Start</p>
                      </div>
                    ) : (
                      phases.map((phase, idx) => (
                        <div
                          key={idx}
                          className={`flex items-center gap-3 p-4 rounded-xl border transition-all ${phase.type === "phase_start"
                            ? "bg-white/[0.02] border-white/[0.08]"
                            : phase.status === "SUCCESS"
                              ? "bg-white/[0.01] border-white/[0.04]"
                              : "bg-white/[0.01] border-white/[0.04]"
                            }`}
                        >
                          {phase.type === "phase_start" ? (
                            <Loader2 className="w-4 h-4 text-[#737373] animate-spin" />
                          ) : phase.status === "SUCCESS" ? (
                            <CheckCircle className="w-4 h-4 text-[#FAFAFA]" />
                          ) : (
                            <XCircle className="w-4 h-4 text-[#525252]" />
                          )}
                          <span className="text-sm text-[#A3A3A3] flex-1 truncate">{phase.name}</span>
                          {phase.duration_ms && (
                            <span className="text-xs text-[#404040] flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              {(phase.duration_ms / 1000).toFixed(2)}s
                            </span>
                          )}
                          {phase.phase && (
                            <span className="text-xs text-[#404040]">#{phase.phase}</span>
                          )}
                        </div>
                      ))
                    )}
                  </div>
                </ScrollArea>
              </div>
            </div>

            {/* Right: Browser Activity */}
            <div className="bg-[#0A0A0A] border border-white/[0.06] rounded-3xl overflow-hidden">
              <div className="px-6 py-5 border-b border-white/[0.06] flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Eye className="w-4 h-4 text-[#737373]" />
                  <h3 className="text-sm font-medium">Browser Activity</h3>
                </div>
                <span className="text-xs text-[#404040]">{browserActions.length} actions</span>
              </div>

              <ScrollArea className="h-[355px]">
                <div className="p-4 space-y-2" ref={browserLogRef}>
                  {browserActions.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-[280px] text-[#404040]">
                      <Globe className="w-12 h-12 mb-4 opacity-30" />
                      <p className="text-sm">Browser actions will appear here</p>
                      <p className="text-xs mt-2">Chromium / Edge Headless</p>
                    </div>
                  ) : (
                    browserActions.map((action, idx) => (
                      <div
                        key={idx}
                        className="p-3 rounded-xl bg-[#171717] border border-white/[0.04] hover:border-white/[0.08] transition-colors"
                      >
                        <div className="flex items-center gap-3">
                          {getActionIcon(action.action || "")}
                          <div className="flex-1 min-w-0">
                            <div className="text-sm font-medium text-[#FAFAFA]">{action.action}</div>
                            <div className="text-xs text-[#404040] truncate">{action.target}</div>
                          </div>
                          <span className="text-xs text-[#404040]">{action.duration_ms}ms</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </ScrollArea>

              <div className="px-6 py-4 border-t border-white/[0.06] flex items-center justify-between text-xs text-[#404040]">
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${isRunning ? "bg-[#FAFAFA] animate-pulse" : "bg-[#404040]"}`} />
                  {isRunning ? "Active" : "Idle"}
                </div>
                <span>Chromium / Edge</span>
              </div>
            </div>
          </div>

          {/* Result Summary */}
          {result && (
            <div className="mt-8 relative">
              <div className="absolute -inset-1 bg-gradient-to-r from-white/10 via-white/5 to-white/10 rounded-3xl blur-lg" />
              <div className="relative bg-[#0A0A0A] border border-white/[0.1] rounded-3xl p-10">
                <div className="flex items-center justify-between mb-10">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-[#FAFAFA] flex items-center justify-center shadow-[0_0_20px_rgba(255,255,255,0.2)]">
                      <CheckCircle className="w-5 h-5 text-[#000000]" />
                    </div>
                    <span className="text-xl font-semibold">Analysis Complete</span>
                  </div>
                  {result.summary?.report_file && (
                    <a
                      href={`http://localhost:8000/api/reports/${result.summary.report_file.split(/[\\\/]/).pop()}`}
                      download
                      className="px-4 py-2 bg-gradient-to-r from-white/10 to-white/5 border border-white/[0.1] rounded-xl text-sm font-medium hover:bg-white/10 transition-colors flex items-center gap-2"
                    >
                      <ArrowRight className="w-4 h-4" />
                      Download Report
                    </a>
                  )}
                </div>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-8">
                  <div>
                    <div className="text-5xl font-bold text-[#FAFAFA]">{result.summary?.total_phases}</div>
                    <div className="text-sm text-[#525252] mt-2">Phases</div>
                  </div>
                  <div>
                    <div className="text-5xl font-bold text-[#FAFAFA]">{result.summary?.successful_steps}</div>
                    <div className="text-sm text-[#525252] mt-2">Passed</div>
                  </div>
                  <div>
                    <div className="text-5xl font-bold text-[#404040]">{result.summary?.failed_steps}</div>
                    <div className="text-sm text-[#525252] mt-2">Failed</div>
                  </div>
                  <div>
                    <div className="text-5xl font-bold text-[#FAFAFA]">{result.summary?.findings_count}</div>
                    <div className="text-sm text-[#525252] mt-2">Findings</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-[#737373]">{((result.summary?.total_duration_ms || 0) / 1000).toFixed(1)}s</div>
                    <div className="text-sm text-[#525252] mt-2">Duration</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Real-time Findings */}
          {findings.length > 0 && (
            <div className="mt-8">
              <div className="bg-[#0A0A0A] border border-white/[0.06] rounded-3xl overflow-hidden">
                <div className="px-6 py-5 border-b border-white/[0.06] flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Shield className="w-4 h-4 text-orange-400" />
                    <h3 className="text-sm font-medium">Security Findings</h3>
                  </div>
                  <span className="text-xs text-[#404040]">{findings.length} findings</span>
                </div>

                <div className="max-h-[400px] overflow-y-auto">
                  <div className="p-4 space-y-2">
                    {findings.map((finding, idx) => (
                      <div
                        key={idx}
                        className="p-4 rounded-xl bg-[#171717] border border-white/[0.04] hover:border-white/[0.08] transition-colors"
                      >
                        <div className="flex items-start gap-3">
                          <AlertTriangle className={`w-4 h-4 mt-0.5 ${finding.severity === "CRITICAL" ? "text-red-500" :
                            finding.severity === "HIGH" ? "text-orange-500" :
                              finding.severity === "MEDIUM" ? "text-yellow-500" :
                                finding.severity === "LOW" ? "text-blue-400" :
                                  "text-gray-400"
                            }`} />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <span className={`px-2 py-0.5 rounded-md text-xs font-medium ${getSeverityColor(finding.severity)}`}>
                                {finding.severity}
                              </span>
                              <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-[#262626] text-[#a3a3a3]">
                                {finding.category}
                              </span>
                            </div>
                            <div className="text-sm font-medium text-[#FAFAFA] mb-1">{finding.title}</div>
                            <div className="text-xs text-[#525252]">{finding.description}</div>
                            {finding.url && (
                              <div className="text-xs text-[#404040] mt-2 truncate">
                                URL: {finding.url}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mt-8 p-5 bg-[#0A0A0A] border border-white/[0.06] rounded-2xl flex items-center gap-4">
              <XCircle className="w-5 h-5 text-[#525252] shrink-0" />
              <span className="text-[#737373] text-sm">{error}</span>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
