"use client"

import { useEffect, useRef } from "react"
import {
    Play,
    Square,
    Terminal,
    CheckCircle,
    XCircle,
    Loader2,
    Globe,
    Eye,
    MousePointer,
    Type,
    Camera,
    Clock,
    AlertCircle,
    Server,
    ChevronRight,
    Zap,
    Activity
} from "lucide-react"

import { AppSidebar } from "@/components/app-sidebar"
import {
    SidebarInset,
    SidebarProvider,
    SidebarTrigger,
} from "@/components/ui/sidebar"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useLiveData } from "@/components/providers/live-data-provider"
import { type PhaseUpdate, useWorkflowRunner } from "@/lib/use-workflow-runner"

export default function RunnerPage() {
    const { apiStatus } = useLiveData()
    const {
        targetUrl,
        setTargetUrl,
        mode,
        setMode,
        isRunning,
        phases,
        browserActions,
        currentPhase,
        progress,
        result,
        error,
        start,
        stop,
    } = useWorkflowRunner("READ_ONLY")

    const phaseListRef = useRef<HTMLDivElement>(null)
    const browserListRef = useRef<HTMLDivElement>(null)

    // Auto-scroll phase list
    useEffect(() => {
        if (phaseListRef.current) {
            phaseListRef.current.scrollTop = phaseListRef.current.scrollHeight
        }
    }, [phases])

    // Auto-scroll browser actions
    useEffect(() => {
        if (browserListRef.current) {
            browserListRef.current.scrollTop = browserListRef.current.scrollHeight
        }
    }, [browserActions])


    const getActionIcon = (action: string) => {
        switch (action) {
            case "NAVIGATE": return <Globe className="w-4 h-4 text-blue-400" />
            case "CLICK": return <MousePointer className="w-4 h-4 text-green-400" />
            case "TYPE": return <Type className="w-4 h-4 text-purple-400" />
            case "SCREENSHOT": return <Camera className="w-4 h-4 text-orange-400" />
            case "SCROLL": return <ChevronRight className="w-4 h-4 text-cyan-400" />
            case "INSPECT": return <Eye className="w-4 h-4 text-yellow-400" />
            case "EXTRACT": return <Zap className="w-4 h-4 text-pink-400" />
            default: return <Activity className="w-4 h-4 text-gray-400" />
        }
    }

    const getPhaseStatus = (phase: PhaseUpdate) => {
        if (phase.type === "phase_start") {
            return <Loader2 className="w-4 h-4 text-yellow-400 animate-spin" />
        }
        if (phase.status === "SUCCESS") {
            return <CheckCircle className="w-4 h-4 text-green-400" />
        }
        if (phase.status === "FAILED") {
            return <XCircle className="w-4 h-4 text-red-400" />
        }
        return null
    }

    return (
        <SidebarProvider>
            <AppSidebar variant="inset" />
            <SidebarInset className="bg-[#000000] text-[#FAFAFA]">

                {/* Ambient Glow */}
                <div className="fixed inset-0 pointer-events-none">
                    <div className="absolute top-[-20%] right-[-10%] w-[50vw] h-[50vh] bg-gradient-radial from-purple-500/[0.05] via-transparent to-transparent rounded-full blur-3xl" />
                    <div className="absolute bottom-[-10%] left-[-10%] w-[40vw] h-[40vh] bg-gradient-radial from-blue-500/[0.05] via-transparent to-transparent rounded-full blur-3xl" />
                </div>

                {/* Header */}
                <header className="flex h-16 shrink-0 items-center justify-between gap-2 border-b border-white/[0.06] bg-[#000000]/80 backdrop-blur-xl px-4 sticky top-0 z-10">
                    <div className="flex items-center gap-2">
                        <SidebarTrigger className="-ml-1 text-[#737373] hover:text-[#FAFAFA]" />
                        <div className="ml-4 text-lg font-semibold">Phase Runner</div>
                    </div>
                    <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border ${apiStatus === "online"
                            ? "bg-green-500/10 border-green-500/20 text-green-400"
                            : apiStatus === "offline"
                                ? "bg-red-500/10 border-red-500/20 text-red-400"
                                : "bg-yellow-500/10 border-yellow-500/20 text-yellow-400"
                        }`}>
                        <Server className="w-3 h-3" />
                        {apiStatus === "online" ? "API Online" : apiStatus === "offline" ? "Offline" : "Checking..."}
                    </div>
                </header>

                {/* Main Content - Split View */}
                <div className="flex flex-1 h-[calc(100vh-4rem)]">

                    {/* Left Panel - Phase Execution */}
                    <div className="flex-1 flex flex-col border-r border-white/[0.06]">

                        {/* Target Input */}
                        <div className="p-4 border-b border-white/[0.06]">
                            <div className="flex gap-3">
                                <input
                                    type="url"
                                    placeholder="https://target-domain.com"
                                        value={targetUrl}
                                        onChange={(e) => setTargetUrl(e.target.value)}
                                    disabled={isRunning}
                                    className="flex-1 px-4 py-2 bg-[#0A0A0A] border border-white/[0.1] rounded-lg text-[#FAFAFA] placeholder-[#525252] focus:border-purple-500/50 outline-none"
                                />
                                <select
                                    value={mode}
                                    onChange={(e) => setMode(e.target.value as "READ_ONLY" | "REAL")}
                                    disabled={isRunning}
                                    className="px-4 py-2 bg-[#0A0A0A] border border-white/[0.1] rounded-lg text-[#FAFAFA] outline-none"
                                >
                                    <option value="READ_ONLY">READ_ONLY (Safe)</option>
                                    <option value="REAL">REAL (Full)</option>
                                </select>
                                {isRunning ? (
                                    <button
                                        onClick={stop}
                                        className="px-6 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors flex items-center gap-2"
                                    >
                                        <Square className="w-4 h-4" />
                                        Stop
                                    </button>
                                ) : (
                                    <button
                                        onClick={start}
                                        disabled={!targetUrl.trim() || apiStatus !== "online"}
                                        className="px-6 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                                    >
                                        <Play className="w-4 h-4" />
                                        Run
                                    </button>
                                )}
                            </div>

                            {/* Progress Bar */}
                            {isRunning && (
                                <div className="mt-4">
                                    <div className="flex justify-between text-xs text-[#737373] mb-1">
                                        <span>Phase {currentPhase} / 50</span>
                                        <span>{progress.toFixed(1)}%</span>
                                    </div>
                                    <div className="h-2 bg-[#171717] rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-gradient-to-r from-purple-500 to-blue-500 transition-all duration-300"
                                            style={{ width: `${progress}%` }}
                                        />
                                    </div>
                                </div>
                            )}
                        </div>

                        {/* Phase List */}
                        <div className="flex-1 overflow-hidden">
                            <div className="p-4 border-b border-white/[0.06]">
                                <h3 className="text-sm font-medium text-[#A3A3A3]">Execution Log</h3>
                            </div>
                            <ScrollArea className="h-[calc(100%-3rem)]" ref={phaseListRef as any}>
                                <div className="p-4 space-y-2">
                                    {phases.length === 0 && !isRunning && (
                                        <div className="text-center py-12 text-[#525252]">
                                            <Terminal className="w-12 h-12 mx-auto mb-4 opacity-30" />
                                            <p>Enter a target URL and click Run to start</p>
                                        </div>
                                    )}

                                    {phases.map((phase, idx) => (
                                        <div
                                            key={idx}
                                            className={`flex items-center gap-3 p-3 rounded-lg border transition-all ${phase.type === "phase_start"
                                                    ? "bg-yellow-500/5 border-yellow-500/20"
                                                    : phase.status === "SUCCESS"
                                                        ? "bg-green-500/5 border-green-500/20"
                                                        : phase.status === "FAILED"
                                                            ? "bg-red-500/5 border-red-500/20"
                                                            : "bg-white/[0.02] border-white/[0.06]"
                                                }`}
                                        >
                                            {getPhaseStatus(phase)}
                                            <div className="flex-1 min-w-0">
                                                <div className="text-sm font-medium text-[#FAFAFA] truncate">
                                                    {phase.name || phase.type}
                                                </div>
                                                {phase.duration_ms && (
                                                    <div className="text-xs text-[#525252] flex items-center gap-1">
                                                        <Clock className="w-3 h-3" />
                                                        {(phase.duration_ms / 1000).toFixed(2)}s
                                                    </div>
                                                )}
                                            </div>
                                            {phase.phase && (
                                                <div className="text-xs text-[#525252]">
                                                    #{phase.phase}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </ScrollArea>
                        </div>

                        {/* Result Summary */}
                        {result && (
                            <div className="p-4 border-t border-white/[0.06] bg-[#0A0A0A]">
                                <div className="grid grid-cols-4 gap-4">
                                    <div className="text-center">
                                        <div className="text-2xl font-bold text-[#FAFAFA]">{result.summary?.total_phases || 0}</div>
                                        <div className="text-xs text-[#525252]">Phases</div>
                                    </div>
                                    <div className="text-center">
                                        <div className="text-2xl font-bold text-green-400">{result.summary?.successful_steps || 0}</div>
                                        <div className="text-xs text-[#525252]">Passed</div>
                                    </div>
                                    <div className="text-center">
                                        <div className="text-2xl font-bold text-red-400">{result.summary?.failed_steps || 0}</div>
                                        <div className="text-xs text-[#525252]">Failed</div>
                                    </div>
                                    <div className="text-center">
                                        <div className="text-2xl font-bold text-purple-400">{result.summary?.findings_count || 0}</div>
                                        <div className="text-xs text-[#525252]">Findings</div>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Right Panel - Browser Activity */}
                    <div className="w-[400px] flex flex-col bg-[#0A0A0A]">
                        <div className="p-4 border-b border-white/[0.06]">
                            <div className="flex items-center gap-2">
                                <Eye className="w-4 h-4 text-purple-400" />
                                <h3 className="text-sm font-medium text-[#A3A3A3]">Browser Activity</h3>
                                <span className="ml-auto text-xs text-[#525252]">
                                    {browserActions.length} actions
                                </span>
                            </div>
                        </div>

                        <ScrollArea className="flex-1" ref={browserListRef as any}>
                            <div className="p-4 space-y-2">
                                {browserActions.length === 0 && (
                                    <div className="text-center py-12 text-[#525252]">
                                        <Globe className="w-12 h-12 mx-auto mb-4 opacity-30" />
                                        <p className="text-sm">Browser actions will appear here</p>
                                        <p className="text-xs mt-2">Chromium/Edge Headless</p>
                                    </div>
                                )}

                                {browserActions.map((action, idx) => (
                                    <div
                                        key={idx}
                                        className="p-3 rounded-lg bg-[#171717] border border-white/[0.06] hover:border-purple-500/30 transition-colors"
                                    >
                                        <div className="flex items-center gap-3">
                                            {getActionIcon(action.action || "")}
                                            <div className="flex-1 min-w-0">
                                                <div className="text-sm font-medium text-[#FAFAFA]">
                                                    {action.action}
                                                </div>
                                                <div className="text-xs text-[#525252] truncate">
                                                    {action.target}
                                                </div>
                                            </div>
                                            <div className="text-xs text-[#525252]">
                                                {action.duration_ms}ms
                                            </div>
                                        </div>
                                        {action.details && Object.keys(action.details).length > 0 && (
                                            <div className="mt-2 pt-2 border-t border-white/[0.06]">
                                                <div className="text-xs text-[#525252] font-mono">
                                                    {JSON.stringify(action.details, null, 0).substring(0, 100)}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        </ScrollArea>

                        {/* Browser Info */}
                        <div className="p-4 border-t border-white/[0.06]">
                            <div className="flex items-center gap-3 text-xs text-[#525252]">
                                <div className="flex items-center gap-1">
                                    <div className={`w-2 h-2 rounded-full ${isRunning ? "bg-green-400 animate-pulse" : "bg-gray-600"}`} />
                                    {isRunning ? "Active" : "Idle"}
                                </div>
                                <div className="flex-1 text-center">
                                    Chromium / Edge Headless
                                </div>
                                <div>
                                    {browserActions.length} total
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </SidebarInset>
        </SidebarProvider>
    )
}
