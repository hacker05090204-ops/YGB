"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { cn } from "@/lib/utils"
import { Activity, Shield, AlertTriangle, Play, Square, Crosshair, BookOpen, Gauge, Target, ShieldCheck, Clock } from "lucide-react"

import { AppSidebar } from "@/components/app-sidebar"
import {
    SidebarInset,
    SidebarProvider,
    SidebarTrigger,
} from "@/components/ui/sidebar"

// Import all dashboard components
import { ExecutionState, type ExecutionStateType } from "@/components/execution-state"
import { ModeSelector, type AutonomyModeType } from "@/components/mode-selector"
import { ApprovalPanel, type ApprovalRequest, type RiskLevelType } from "@/components/approval-panel"
import { BrowserAssistant, type AssistantExplanation } from "@/components/browser-assistant"
import { VoiceControls, type VoiceIntent, type VoiceModeType } from "@/components/voice-controls"
import { TargetDiscoveryPanel, type TargetCandidate } from "@/components/target-discovery-panel"
import { TrainingProgress } from "@/components/training-progress"
import { ScopeTargetPanel } from "@/components/scope-target-panel"
import { GpuMonitor } from "@/components/gpu-monitor"
import { ActiveDevices } from "@/components/active-devices"
import { SessionHistory } from "@/components/session-history"
import { LoginAlerts } from "@/components/login-alerts"
import { StorageMonitor } from "@/components/storage-monitor"

// API Base URL
const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

export default function ControlPage() {
    // Dashboard State
    const [dashboardId, setDashboardId] = useState<string | null>(null)
    const [isConnected, setIsConnected] = useState(false)
    const [isLoading, setIsLoading] = useState(true)

    // Execution State (from G01)
    const [executionState, setExecutionState] = useState<ExecutionStateType>("IDLE")
    const [humanApproved, setHumanApproved] = useState(false)
    const [denyReason, setDenyReason] = useState<string | undefined>()

    // Autonomy Mode (from G06)
    const [autonomyMode, setAutonomyMode] = useState<AutonomyModeType>("READ_ONLY")

    // Approval Requests (from G13)
    const [pendingRequest, setPendingRequest] = useState<ApprovalRequest | null>(null)
    const [approvalLoading, setApprovalLoading] = useState(false)

    // Target Discovery (from G14)
    const [targets, setTargets] = useState<TargetCandidate[]>([])
    const [selectedTargets, setSelectedTargets] = useState<Set<string>>(new Set())
    const [isDiscovering, setIsDiscovering] = useState(false)

    // Browser Assistant (from G05)
    const [assistantActive, setAssistantActive] = useState(false)
    const [currentAction, setCurrentAction] = useState<string | undefined>()
    const [explanations, setExplanations] = useState<AssistantExplanation[]>([])

    // Voice (from G12)
    const [lastIntent, setLastIntent] = useState<VoiceIntent | null>(null)
    const [voiceProcessing, setVoiceProcessing] = useState(false)
    const [voiceMode, setVoiceMode] = useState<VoiceModeType>("SECURITY")

    // Runtime Mode Control (Train/Hunt separation)
    const [runtimeMode, setRuntimeMode] = useState<"IDLE" | "TRAIN" | "HUNT">("IDLE")
    const [modeLoading, setModeLoading] = useState(false)
    const [accuracySnapshot, setAccuracySnapshot] = useState<{
        precision: number; recall: number; ece_score: number;
        dup_suppression_rate: number; scope_compliance: number;
    } | null>(null)
    const [targetsActive, setTargetsActive] = useState(0)
    const maxTargets = 5

    // Runtime telemetry — polled from /runtime/status (C++ authoritative source)
    const [runtimeStatus, setRuntimeStatus] = useState<{
        status: string;
        runtime?: {
            total_epochs: number; completed_epochs: number; current_loss: number;
            precision: number; ece: number; drift_kl: number; duplicate_rate: number;
            gpu_util: number; cpu_util: number; temperature: number;
            determinism_status: boolean; freeze_status: boolean;
            mode: string; progress_pct: number; loss_trend: number;
            // Phase 2: Real-time training visibility
            wall_clock_unix: number;
            monotonic_start_time: number;
            training_duration_seconds: number;
        };
        determinism_ok?: boolean;
        stale?: boolean;
        last_update_ms?: number;
        signature?: string;
    } | null>(null)

    // Phase 2: Real-time clock and stall detection
    const [liveTime, setLiveTime] = useState<number>(Date.now())
    const lastTelemetryTs = useRef<number>(0)
    const [isStalled, setIsStalled] = useState(false)

    // Initialize dashboard
    useEffect(() => {
        const initDashboard = async () => {
            try {
                const response = await fetch(`${API_BASE}/api/dashboard/create`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ user_id: "user-001", user_name: "Researcher" })
                })

                if (response.ok) {
                    const data = await response.json()
                    setDashboardId(data.dashboard_id)
                    setIsConnected(true)
                } else {
                    console.error("Dashboard init failed: non-OK response")
                    setDashboardId(null)
                    setIsConnected(false)
                }
            } catch (error) {
                console.error("Dashboard init failed:", error)
                setDashboardId(null)
                setIsConnected(false)
            } finally {
                setIsLoading(false)
            }
        }

        initDashboard()
    }, [])

    // Poll accuracy snapshot — every 1s for real-time updates
    useEffect(() => {
        const fetchAccuracy = async () => {
            try {
                const res = await fetch(`${API_BASE}/api/accuracy/snapshot`)
                if (res.ok) {
                    const data = await res.json()
                    setAccuracySnapshot(data)
                }
            } catch { /* offline fallback */ }
        }
        fetchAccuracy()
        const interval = setInterval(fetchAccuracy, 1000)
        return () => clearInterval(interval)
    }, [])

    // Poll runtime status from backend — every 1s for real-time updates
    useEffect(() => {
        const fetchRuntimeStatus = async () => {
            try {
                const res = await fetch(`${API_BASE}/runtime/status`)
                if (res.ok) {
                    const data = await res.json()
                    setRuntimeStatus(data)
                    // Phase 2: Track telemetry freshness for stall detection
                    if (data.runtime?.wall_clock_unix) {
                        const newTs = data.runtime.wall_clock_unix
                        if (lastTelemetryTs.current > 0 && newTs === lastTelemetryTs.current) {
                            // Timestamp hasn't changed — check stall threshold (30s)
                            const elapsed = (Date.now() / 1000) - newTs
                            setIsStalled(elapsed > 30)
                        } else {
                            setIsStalled(false)
                        }
                        lastTelemetryTs.current = newTs
                    }
                }
            } catch { /* backend offline — keep last known state */ }
        }
        fetchRuntimeStatus()
        const interval = setInterval(fetchRuntimeStatus, 1000)
        return () => clearInterval(interval)
    }, [])

    // Phase 2: Live clock tick every 1s
    useEffect(() => {
        const tick = setInterval(() => setLiveTime(Date.now()), 1000)
        return () => clearInterval(tick)
    }, [])

    // Phase 2: Format seconds duration to HH:MM:SS
    const formatDuration = (seconds: number): string => {
        const h = Math.floor(seconds / 3600)
        const m = Math.floor((seconds % 3600) / 60)
        const s = Math.floor(seconds % 60)
        return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
    }

    // Mode transition handlers
    const handleStartTraining = useCallback(async () => {
        setModeLoading(true)
        try {
            const res = await fetch(`${API_BASE}/api/mode/train/start`, { method: "POST" })
            if (res.ok) setRuntimeMode("TRAIN")
        } catch (e) { console.error("Start training failed:", e) }
        finally { setModeLoading(false) }
    }, [])

    const handleStopTraining = useCallback(async () => {
        setModeLoading(true)
        try {
            const res = await fetch(`${API_BASE}/api/mode/train/stop`, { method: "POST" })
            if (res.ok) setRuntimeMode("IDLE")
        } catch (e) { console.error("Stop training failed:", e) }
        finally { setModeLoading(false) }
    }, [])

    const handleStartHunting = useCallback(async () => {
        setModeLoading(true)
        try {
            const res = await fetch(`${API_BASE}/api/mode/hunt/start`, { method: "POST" })
            if (res.ok) setRuntimeMode("HUNT")
        } catch (e) { console.error("Start hunting failed:", e) }
        finally { setModeLoading(false) }
    }, [])

    const handleStopHunting = useCallback(async () => {
        setModeLoading(true)
        try {
            const res = await fetch(`${API_BASE}/api/mode/hunt/stop`, { method: "POST" })
            if (res.ok) setRuntimeMode("IDLE")
        } catch (e) { console.error("Stop hunting failed:", e) }
        finally { setModeLoading(false) }
    }, [])

    // Mode Change Handler
    const handleModeChange = useCallback(async (mode: AutonomyModeType, hours?: number) => {
        setAutonomyMode(mode)

        try {
            await fetch(`${API_BASE}/api/autonomy/session`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ mode, duration_hours: hours || 0 })
            })
        } catch (error) {
            console.error("Mode change failed:", error)
        }
    }, [])

    // Approval Handlers
    const handleApprove = useCallback(async (requestId: string, reason?: string) => {
        setApprovalLoading(true)

        try {
            const response = await fetch(`${API_BASE}/api/approval/decision`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    request_id: requestId,
                    approved: true,
                    approver_id: "user-001",
                    reason
                })
            })

            if (response.ok) {
                setPendingRequest(null)
                setExecutionState("EXECUTING")
                setHumanApproved(true)
                setAssistantActive(true)
                setCurrentAction("Starting approved workflow...")
            }
        } catch (error) {
            console.error("Approval failed:", error)
        } finally {
            setApprovalLoading(false)
        }
    }, [])

    const handleReject = useCallback(async (requestId: string, reason?: string) => {
        setApprovalLoading(true)

        try {
            const response = await fetch(`${API_BASE}/api/approval/decision`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    request_id: requestId,
                    approved: false,
                    approver_id: "user-001",
                    reason
                })
            })

            if (response.ok) {
                setPendingRequest(null)
                setExecutionState("STOPPED")
                setDenyReason(reason || "Rejected by user")
            }
        } catch (error) {
            console.error("Rejection failed:", error)
        } finally {
            setApprovalLoading(false)
        }
    }, [])

    const handleStop = useCallback(async () => {
        try {
            await fetch(`${API_BASE}/api/execution/transition`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    transition: "ABORT",
                    actor_id: "user-001",
                    reason: "User requested stop"
                })
            })

            setExecutionState("STOPPED")
            setAssistantActive(false)
            setCurrentAction(undefined)
        } catch (error) {
            console.error("Stop failed:", error)
            setExecutionState("STOPPED")
        }
    }, [])

    // Target Discovery Handler
    const handleDiscoverTargets = useCallback(async () => {
        setIsDiscovering(true)

        try {
            const response = await fetch(`${API_BASE}/api/targets/discover`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ min_payout: "LOW", max_density: "MEDIUM", public_only: true })
            })

            if (response.ok) {
                const data = await response.json()
                setTargets(data.candidates || [])
            } else {
                console.error("Target discovery failed: non-OK response")
                setTargets([])
            }
        } catch (error) {
            console.error("Discovery failed:", error)
            setTargets([])
        } finally {
            setIsDiscovering(false)
        }
    }, [])

    // Target Selection Handler
    const handleSelectTarget = useCallback((id: string) => {
        setSelectedTargets(prev => {
            const next = new Set(prev)
            next.has(id) ? next.delete(id) : next.add(id)
            return next
        })

        // Create approval request when first target selected
        if (selectedTargets.size === 0 && !pendingRequest) {
            const target = targets.find(t => t.candidate_id === id)
            if (target) {
                setPendingRequest({
                    request_id: `APR-${Date.now()}`,
                    target: target.scope_summary,
                    scope: target.scope_summary,
                    proposed_mode: "READ_ONLY",
                    risk_level: (target.payout_tier === "HIGH" ? "LOW" : "MEDIUM") as RiskLevelType,
                    risk_summary: `Analysis of ${target.program_name} (${target.scope_summary})`,
                    status: "PENDING",
                    created_at: new Date().toISOString(),
                    expires_at: new Date(Date.now() + 3600000).toISOString()
                })
                setExecutionState("AWAIT_HUMAN")
            }
        }
    }, [targets, selectedTargets, pendingRequest])

    // Voice Input Handler
    const handleVoiceInput = useCallback(async (text: string) => {
        setVoiceProcessing(true)

        try {
            const response = await fetch(`${API_BASE}/api/voice/parse`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text, mode: voiceMode })
            })

            if (response.ok) {
                const intent = await response.json()
                setLastIntent(intent)

                if (intent.intent_type === "FIND_TARGETS" && intent.status === "PARSED") {
                    handleDiscoverTargets()
                }
            } else {
                setLastIntent({
                    intent_id: `VOC-${Date.now()}`,
                    intent_type: "UNKNOWN",
                    raw_text: text,
                    extracted_value: null,
                    confidence: 0,
                    status: "INVALID",
                    block_reason: "Could not parse intent",
                    timestamp: new Date().toISOString()
                })
            }
        } catch (error) {
            console.error("Voice parse failed:", error)
        } finally {
            setVoiceProcessing(false)
        }
    }, [handleDiscoverTargets, voiceMode])

    // Loading State
    if (isLoading) {
        return (
            <SidebarProvider
                style={{
                    "--sidebar-width": "calc(var(--spacing) * 64)",
                    "--header-height": "calc(var(--spacing) * 12)",
                } as React.CSSProperties}
            >
                <AppSidebar variant="inset" />
                <SidebarInset>
                    <div className="min-h-screen flex items-center justify-center">
                        <div className="text-center">
                            <div className="w-16 h-16 rounded-2xl bg-card flex items-center justify-center mx-auto mb-4 animate-pulse">
                                <Activity className="w-8 h-8 text-primary" />
                            </div>
                            <p className="text-muted-foreground">Initializing Control Panel...</p>
                        </div>
                    </div>
                </SidebarInset>
            </SidebarProvider>
        )
    }

    return (
        <SidebarProvider
            style={{
                "--sidebar-width": "calc(var(--spacing) * 64)",
                "--header-height": "calc(var(--spacing) * 12)",
            } as React.CSSProperties}
        >
            <AppSidebar variant="inset" />
            <SidebarInset>
                {/* Header */}
                <header className="sticky top-0 z-50 flex h-16 shrink-0 items-center justify-between gap-2 border-b border-border/40 px-4 bg-background/50 backdrop-blur-md">
                    <div className="flex items-center gap-4">
                        <SidebarTrigger className="-ml-1" />
                        <div className="flex items-center gap-3">
                            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-[0_0_15px_rgba(139,92,246,0.3)]">
                                <Shield className="w-4 h-4 text-white" />
                            </div>
                            <div>
                                <h1 className="font-bold text-sm">Phase-49 Control</h1>
                                <p className="text-xs text-muted-foreground">ID: {dashboardId}</p>
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center gap-4 pr-4">
                        <div className={cn(
                            "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium",
                            isConnected
                                ? "bg-emerald-500/20 text-emerald-500"
                                : "bg-red-500/20 text-red-500"
                        )}>
                            <div className={cn(
                                "w-2 h-2 rounded-full",
                                isConnected ? "bg-emerald-400" : "bg-red-400"
                            )} />
                            {isConnected ? "Connected" : "Offline"}
                        </div>
                    </div>
                </header>

                {/* Main Content */}
                <main className="flex-1 p-6">
                    <div className="max-w-[1600px] mx-auto">

                        {/* Runtime Mode Control Panel */}
                        <div className="mb-6 p-5 rounded-2xl bg-card/50 border border-border/50">
                            <div className="flex items-center justify-between mb-4">
                                <div className="flex items-center gap-3">
                                    <div className={cn(
                                        "w-8 h-8 rounded-lg flex items-center justify-center",
                                        runtimeMode === "TRAIN" ? "bg-blue-500/20" :
                                            runtimeMode === "HUNT" ? "bg-red-500/20" : "bg-zinc-500/20"
                                    )}>
                                        {runtimeMode === "TRAIN" ? <BookOpen className="w-4 h-4 text-blue-400" /> :
                                            runtimeMode === "HUNT" ? <Crosshair className="w-4 h-4 text-red-400" /> :
                                                <Gauge className="w-4 h-4 text-zinc-400" />}
                                    </div>
                                    <div>
                                        <h2 className="text-sm font-bold">Runtime Mode</h2>
                                        <p className={cn(
                                            "text-xs font-medium",
                                            runtimeMode === "TRAIN" ? "text-blue-400" :
                                                runtimeMode === "HUNT" ? "text-red-400" : "text-zinc-400"
                                        )}>
                                            {runtimeMode === "TRAIN" ? "LAB TRAINING" :
                                                runtimeMode === "HUNT" ? "HUNT EXECUTION" : "IDLE"}
                                        </p>
                                    </div>
                                </div>

                                <div className="flex items-center gap-2">
                                    {runtimeMode === "IDLE" ? (
                                        <>
                                            <button
                                                onClick={handleStartTraining}
                                                disabled={modeLoading}
                                                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/20 hover:bg-blue-500/30 text-blue-400 text-xs font-medium transition-colors disabled:opacity-50"
                                            >
                                                <Play className="w-3 h-3" /> Start Training
                                            </button>
                                            <button
                                                onClick={handleStartHunting}
                                                disabled={modeLoading}
                                                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-400 text-xs font-medium transition-colors disabled:opacity-50"
                                            >
                                                <Crosshair className="w-3 h-3" /> Start Hunting
                                            </button>
                                        </>
                                    ) : runtimeMode === "TRAIN" ? (
                                        <button
                                            onClick={handleStopTraining}
                                            disabled={modeLoading}
                                            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 text-xs font-medium transition-colors disabled:opacity-50"
                                        >
                                            <Square className="w-3 h-3" /> Stop Training
                                        </button>
                                    ) : (
                                        <button
                                            onClick={handleStopHunting}
                                            disabled={modeLoading}
                                            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 text-xs font-medium transition-colors disabled:opacity-50"
                                        >
                                            <Square className="w-3 h-3" /> Stop Hunting
                                        </button>
                                    )}
                                </div>
                            </div>

                            {/* Metrics Strip */}
                            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                                <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Lab Accuracy</p>
                                    <p className="text-lg font-bold text-emerald-400">
                                        {accuracySnapshot ? `${(accuracySnapshot.precision * 100).toFixed(1)}%` : "—"}
                                    </p>
                                </div>
                                <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Precision</p>
                                    <p className="text-lg font-bold text-blue-400">
                                        {accuracySnapshot ? `${(accuracySnapshot.precision * 100).toFixed(1)}%` : "—"}
                                    </p>
                                </div>
                                <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Dup Suppression</p>
                                    <p className="text-lg font-bold text-purple-400">
                                        {accuracySnapshot ? `${(accuracySnapshot.dup_suppression_rate * 100).toFixed(0)}%` : "—"}
                                    </p>
                                </div>
                                <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Scope Compliance</p>
                                    <p className="text-lg font-bold text-cyan-400">
                                        {accuracySnapshot ? `${(accuracySnapshot.scope_compliance * 100).toFixed(0)}%` : "—"}
                                    </p>
                                </div>
                                <div className="p-3 rounded-xl bg-background/50 border border-border/30" id="metric-targets">
                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Targets Active</p>
                                    <p className="text-lg font-bold">
                                        <span className={runtimeMode === "HUNT" ? "text-red-400" : "text-zinc-400"}>
                                            {targetsActive}
                                        </span>
                                        <span className="text-xs text-muted-foreground">/{maxTargets}</span>
                                    </p>
                                </div>
                            </div>
                        </div>

                        {/* ═══ Runtime Telemetry Panel ═══ */}
                        <div className="mb-6 p-5 rounded-2xl bg-card/50 border border-border/50" id="runtime-telemetry">
                            <div className="flex items-center justify-between mb-4">
                                <div className="flex items-center gap-3">
                                    <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center">
                                        <Activity className="w-4 h-4 text-emerald-400" />
                                    </div>
                                    <div>
                                        <h2 className="text-sm font-bold">Runtime Telemetry</h2>
                                        <p className="text-xs text-muted-foreground">C++ Authoritative Source</p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    {isStalled && (
                                        <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-red-500/20 text-red-400 text-xs font-medium animate-pulse">
                                            <AlertTriangle className="w-3 h-3" />
                                            ⚠ Training Stalled
                                        </div>
                                    )}
                                    {runtimeStatus?.stale && (
                                        <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/20 text-amber-400 text-xs font-medium animate-pulse">
                                            <AlertTriangle className="w-3 h-3" />
                                            STALE DATA
                                        </div>
                                    )}
                                    {runtimeStatus?.status === "awaiting_data" && (
                                        <div className="px-3 py-1 rounded-full bg-zinc-500/20 text-zinc-400 text-xs font-medium">
                                            Awaiting Training Start
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Phase 2: Real-time timestamp display */}
                            {runtimeStatus?.status === "active" && runtimeStatus.runtime && (
                                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                                    <div className="p-2.5 rounded-xl bg-background/50 border border-emerald-500/20">
                                        <div className="flex items-center gap-1.5 mb-1">
                                            <Clock className="w-3 h-3 text-emerald-400" />
                                            <p className="text-[10px] text-emerald-400 uppercase tracking-wider font-medium">Training Started</p>
                                        </div>
                                        <p className="text-xs font-mono text-emerald-300">
                                            {runtimeStatus.runtime.wall_clock_unix > 0
                                                ? new Date((runtimeStatus.runtime.wall_clock_unix - runtimeStatus.runtime.training_duration_seconds) * 1000).toLocaleTimeString()
                                                : "—"}
                                        </p>
                                    </div>
                                    <div className="p-2.5 rounded-xl bg-background/50 border border-blue-500/20">
                                        <div className="flex items-center gap-1.5 mb-1">
                                            <Clock className="w-3 h-3 text-blue-400" />
                                            <p className="text-[10px] text-blue-400 uppercase tracking-wider font-medium">Elapsed Time</p>
                                        </div>
                                        <p className="text-xs font-mono text-blue-300">
                                            {formatDuration(runtimeStatus.runtime.training_duration_seconds)}
                                        </p>
                                    </div>
                                    <div className="p-2.5 rounded-xl bg-background/50 border border-violet-500/20">
                                        <div className="flex items-center gap-1.5 mb-1">
                                            <Clock className="w-3 h-3 text-violet-400" />
                                            <p className="text-[10px] text-violet-400 uppercase tracking-wider font-medium">Last Update</p>
                                        </div>
                                        <p className="text-xs font-mono text-violet-300">
                                            {runtimeStatus.runtime.wall_clock_unix > 0
                                                ? new Date(runtimeStatus.runtime.wall_clock_unix * 1000).toLocaleTimeString()
                                                : "—"}
                                        </p>
                                    </div>
                                    <div className="p-2.5 rounded-xl bg-background/50 border border-cyan-500/20">
                                        <div className="flex items-center gap-1.5 mb-1">
                                            <Clock className="w-3 h-3 text-cyan-400" />
                                            <p className="text-[10px] text-cyan-400 uppercase tracking-wider font-medium">Live Clock</p>
                                        </div>
                                        <p className="text-xs font-mono text-cyan-300">
                                            {new Date(liveTime).toLocaleTimeString()}
                                        </p>
                                    </div>
                                </div>
                            )}

                            {runtimeStatus?.status === "active" && runtimeStatus.runtime ? (
                                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                                    <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Epochs</p>
                                        <p className="text-lg font-bold text-violet-400">
                                            {runtimeStatus.runtime.completed_epochs}/{runtimeStatus.runtime.total_epochs}
                                        </p>
                                    </div>
                                    <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Progress</p>
                                        <p className="text-lg font-bold text-blue-400">
                                            {runtimeStatus.runtime.progress_pct.toFixed(1)}%
                                        </p>
                                    </div>
                                    <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Loss</p>
                                        <p className="text-lg font-bold text-amber-400">
                                            {runtimeStatus.runtime.current_loss.toFixed(4)}
                                            <span className={cn("text-xs ml-1", runtimeStatus.runtime.loss_trend < 0 ? "text-emerald-400" : "text-red-400")}>
                                                {runtimeStatus.runtime.loss_trend < 0 ? "↓" : "↑"}
                                            </span>
                                        </p>
                                    </div>
                                    <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Precision</p>
                                        <p className="text-lg font-bold text-emerald-400">
                                            {(runtimeStatus.runtime.precision * 100).toFixed(1)}%
                                        </p>
                                    </div>
                                    <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">ECE</p>
                                        <p className="text-lg font-bold text-cyan-400">
                                            {runtimeStatus.runtime.ece.toFixed(4)}
                                        </p>
                                    </div>
                                    <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Drift KL</p>
                                        <p className="text-lg font-bold text-purple-400">
                                            {runtimeStatus.runtime.drift_kl.toFixed(4)}
                                        </p>
                                    </div>
                                    <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">GPU Util</p>
                                        <p className="text-lg font-bold text-orange-400">
                                            {runtimeStatus.runtime.gpu_util.toFixed(0)}%
                                        </p>
                                    </div>
                                    <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">CPU Util</p>
                                        <p className="text-lg font-bold text-sky-400">
                                            {runtimeStatus.runtime.cpu_util.toFixed(0)}%
                                        </p>
                                    </div>
                                    <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Temp</p>
                                        <p className={cn("text-lg font-bold", runtimeStatus.runtime.temperature > 85 ? "text-red-400" : "text-emerald-400")}>
                                            {runtimeStatus.runtime.temperature.toFixed(0)}°C
                                        </p>
                                    </div>
                                    <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Dup Rate</p>
                                        <p className="text-lg font-bold text-pink-400">
                                            {(runtimeStatus.runtime.duplicate_rate * 100).toFixed(1)}%
                                        </p>
                                    </div>
                                    <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Determinism</p>
                                        <p className={cn("text-lg font-bold", runtimeStatus.runtime.determinism_status ? "text-emerald-400" : "text-red-400")}>
                                            {runtimeStatus.runtime.determinism_status ? "✓ OK" : "✗ FAIL"}
                                        </p>
                                    </div>
                                    <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Freeze</p>
                                        <p className={cn("text-lg font-bold", runtimeStatus.runtime.freeze_status ? "text-emerald-400" : "text-amber-400")}>
                                            {runtimeStatus.runtime.freeze_status ? "✓ Valid" : "⚠ Invalid"}
                                        </p>
                                    </div>
                                </div>
                            ) : (
                                <div className="text-center py-6 text-muted-foreground text-sm">
                                    {runtimeStatus?.status === "error"
                                        ? "⚠ Error reading runtime state"
                                        : "Waiting for training telemetry..."}
                                </div>
                            )}
                        </div>

                        {/* Distributed Training Panel */}
                        <div className="mb-6 p-5 rounded-2xl bg-card/50 border border-border/50">
                            <div className="flex items-center gap-3 mb-4">
                                <div className="w-8 h-8 rounded-lg bg-violet-500/20 flex items-center justify-center">
                                    <Target className="w-4 h-4 text-violet-400" />
                                </div>
                                <div>
                                    <h2 className="text-sm font-bold">Distributed Training</h2>
                                    <p className="text-xs text-muted-foreground">Single-Field Multi-GPU</p>
                                </div>
                            </div>
                            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
                                <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Active Field</p>
                                    <p className="text-sm font-bold text-violet-400">Web/Client</p>
                                </div>
                                <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">RTX 3050</p>
                                    <p className="text-lg font-bold text-emerald-400">—</p>
                                </div>
                                <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">RTX 2050 ×2</p>
                                    <p className="text-lg font-bold text-emerald-400">—</p>
                                </div>
                                <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Mac M1</p>
                                    <p className="text-lg font-bold text-emerald-400">—</p>
                                </div>
                                <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Merge Ready</p>
                                    <p className="text-lg font-bold text-amber-400">—</p>
                                </div>
                                <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Node Contrib</p>
                                    <p className="text-lg font-bold text-blue-400">—</p>
                                </div>
                                <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Stability</p>
                                    <p className="text-lg font-bold text-cyan-400">—</p>
                                </div>
                                <div className="p-3 rounded-xl bg-background/50 border border-border/30">
                                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Mode</p>
                                    <p className="text-sm font-bold text-zinc-400">A — Lab</p>
                                </div>
                            </div>
                        </div>

                        {/* Field Progression Dashboard */}
                        <div className="mb-6 p-5 rounded-2xl bg-card/50 border border-border/50">
                            <div className="flex items-center gap-3 mb-4">
                                <div className="w-8 h-8 rounded-lg bg-cyan-500/20 flex items-center justify-center">
                                    <ShieldCheck className="w-4 h-4 text-cyan-400" />
                                </div>
                                <div>
                                    <h2 className="text-sm font-bold">Field Progression Ladder</h2>
                                    <p className="text-xs text-muted-foreground">23 Fields — Metric-Based Progression</p>
                                </div>
                                <div className="ml-auto flex gap-2">
                                    <button
                                        className="px-3 py-1.5 rounded-lg bg-emerald-500/20 border border-emerald-500/30 text-xs font-semibold text-emerald-400 hover:bg-emerald-500/30 transition-colors disabled:opacity-50"
                                        disabled={runtimeMode === "HUNT"}
                                    >
                                        <Play className="w-3 h-3 inline mr-1" />Train
                                    </button>
                                    <button
                                        className="px-3 py-1.5 rounded-lg bg-red-500/20 border border-red-500/30 text-xs font-semibold text-red-400 hover:bg-red-500/30 transition-colors disabled:opacity-50"
                                        disabled={runtimeMode !== "HUNT"}
                                    >
                                        <Crosshair className="w-3 h-3 inline mr-1" />Hunt
                                    </button>
                                </div>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 max-h-[280px] overflow-y-auto pr-1">
                                {[
                                    { name: "Client-Side Security", master: true },
                                    { name: "API / Business Logic", master: true },
                                    { name: "Subdomain Intelligence", master: false },
                                    { name: "Authentication", master: false },
                                    { name: "Authorization", master: false },
                                    { name: "Rate Limiting", master: false },
                                    { name: "Token Security", master: false },
                                    { name: "Session Mgmt", master: false },
                                    { name: "CORS Misconfig", master: false },
                                    { name: "SSRF", master: false },
                                    { name: "Request Smuggling", master: false },
                                    { name: "Template Injection", master: false },
                                    { name: "Cache Poisoning", master: false },
                                    { name: "Cloud Misconfig", master: false },
                                    { name: "IAM", master: false },
                                    { name: "CI/CD Security", master: false },
                                    { name: "Container Security", master: false },
                                    { name: "Kubernetes", master: false },
                                    { name: "WAF Bypass", master: false },
                                    { name: "CDN Misconfig", master: false },
                                    { name: "Data Leakage", master: false },
                                    { name: "Supply Chain", master: false },
                                    { name: "Dependency Confusion", master: false },
                                ].map((field, i) => (
                                    <div key={i} className={cn(
                                        "flex items-center gap-2 p-2 rounded-lg border transition-colors",
                                        i === 0 ? "bg-violet-500/10 border-violet-500/30" : "bg-background/50 border-border/30",
                                        field.master && "ring-1 ring-violet-500/20"
                                    )}>
                                        <span className={cn(
                                            "w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold",
                                            i === 0 ? "bg-violet-500 text-white" : "bg-zinc-700 text-zinc-400"
                                        )}>{i + 1}</span>
                                        <span className="text-xs font-medium truncate flex-1">{field.name}</span>
                                        <span className={cn(
                                            "text-[9px] px-1.5 py-0.5 rounded font-semibold",
                                            i === 0 ? "bg-amber-500/20 text-amber-400" : "bg-zinc-800 text-zinc-500"
                                        )}>{i === 0 ? "ACTIVE" : "LOCKED"}</span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Voice Controls Row */}
                        <div className="mb-6 p-4 rounded-2xl bg-card/50 border border-border/50">
                            <VoiceControls
                                onVoiceInput={handleVoiceInput}
                                lastIntent={lastIntent}
                                isProcessing={voiceProcessing}
                                voiceMode={voiceMode}
                                onModeChange={setVoiceMode}
                            />
                        </div>

                        <div className="grid grid-cols-12 gap-6">

                            {/* Left Column: Targets & Controls */}
                            <div className="col-span-12 lg:col-span-4 space-y-6">
                                <TargetDiscoveryPanel
                                    targets={targets}
                                    selectedTargets={selectedTargets}
                                    onSelectTarget={handleSelectTarget}
                                    onDiscoverTargets={handleDiscoverTargets}
                                    isDiscovering={isDiscovering}
                                    className="h-[400px]"
                                />

                                <div className="p-5 rounded-2xl bg-card/50 border border-border/50">
                                    <ScopeTargetPanel />
                                </div>

                                <div className="p-5 rounded-2xl bg-card/50 border border-border/50">
                                    <ModeSelector
                                        currentMode={autonomyMode}
                                        onModeChange={handleModeChange}
                                        disabled={executionState === "EXECUTING"}
                                    />
                                </div>
                            </div>

                            {/* Center Column: Approval & State */}
                            <div className="col-span-12 lg:col-span-4 space-y-6">
                                <div className="p-5 rounded-2xl bg-card/50 border border-border/50">
                                    <ExecutionState
                                        currentState={executionState}
                                        humanApproved={humanApproved}
                                        denyReason={denyReason}
                                    />
                                </div>

                                <div className="p-5 rounded-2xl bg-card/50 border border-border/50">
                                    <ApprovalPanel
                                        pendingRequest={pendingRequest}
                                        onApprove={handleApprove}
                                        onReject={handleReject}
                                        onStop={handleStop}
                                        isLoading={approvalLoading}
                                    />
                                </div>

                                <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20">
                                    <div className="flex items-start gap-3">
                                        <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
                                        <div>
                                            <p className="text-sm font-medium text-amber-400">Safety Mode Active</p>
                                            <p className="text-xs text-amber-400/70 mt-1">
                                                All actions route via Dashboard Router. Frontend has NO execution authority.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Right Column: Training Progress, GPU, Sessions & Browser Assistant */}
                            <div className="col-span-12 lg:col-span-4 space-y-6">
                                <TrainingProgress refreshInterval={3000} />
                                <GpuMonitor refreshInterval={5000} />
                                <div className="p-5 rounded-2xl bg-card/50 border border-border/50">
                                    <StorageMonitor />
                                </div>
                                <ActiveDevices refreshInterval={5000} />
                                <SessionHistory refreshInterval={5000} />
                                <LoginAlerts refreshInterval={5000} />

                                <BrowserAssistant
                                    currentAction={currentAction}
                                    explanations={explanations}
                                    isActive={assistantActive}
                                    className="h-[calc(100vh-580px)] min-h-[300px]"
                                />
                            </div>
                        </div>
                    </div>
                </main>
            </SidebarInset>
        </SidebarProvider>
    )
}
