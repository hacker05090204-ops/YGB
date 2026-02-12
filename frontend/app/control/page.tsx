"use client"

import { useState, useEffect, useCallback } from "react"
import { cn } from "@/lib/utils"
import { Activity, Shield, AlertTriangle } from "lucide-react"

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
import { VoiceControls, type VoiceIntent } from "@/components/voice-controls"
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
                body: JSON.stringify({ text })
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
    }, [handleDiscoverTargets])

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

                        {/* Voice Controls Row */}
                        <div className="mb-6 p-4 rounded-2xl bg-card/50 border border-border/50">
                            <VoiceControls
                                onVoiceInput={handleVoiceInput}
                                lastIntent={lastIntent}
                                isProcessing={voiceProcessing}
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
