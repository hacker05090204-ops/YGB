"use client"

import { useState, useEffect, useCallback } from "react"
import { cn } from "@/lib/utils"
import {
    Activity,
    Zap,
    Battery,
    Cpu,
    Clock,
    CheckCircle,
    AlertCircle,
    Loader2,
    TrendingUp
} from "lucide-react"

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

interface G38Status {
    available: boolean
    auto_training: {
        state: string
        is_training: boolean
        epoch: number
        total_epochs: number
        total_completed: number
        progress: number
        idle_seconds: number
        power_connected: boolean
        scan_active: boolean
        gpu_available: boolean
        events_count: number
        last_event: string | null
    }
    guards: {
        main_guards: number
        all_verified: boolean
        message: string
    }
    pretraining: {
        verified: boolean
        message: string
    }
    mode: {
        mode_a_status: string
        message: string
    }
}

interface TrainingEvent {
    event_id: string
    event_type: string
    timestamp: string
    details: string
    idle_seconds: number
    gpu_used: boolean
    epoch: number
}

interface TrainingProgressProps {
    className?: string
    refreshInterval?: number
}

export function TrainingProgress({
    className,
    refreshInterval = 3000
}: TrainingProgressProps) {
    const [status, setStatus] = useState<G38Status | null>(null)
    const [events, setEvents] = useState<TrainingEvent[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const fetchStatus = useCallback(async () => {
        try {
            const [statusRes, eventsRes] = await Promise.all([
                fetch(`${API_BASE}/api/g38/status`),
                fetch(`${API_BASE}/api/g38/events?limit=5`)
            ])

            if (statusRes.ok) {
                const data = await statusRes.json()
                setStatus(data)
                setError(null)
            } else {
                setError("Failed to fetch status")
            }

            if (eventsRes.ok) {
                const data = await eventsRes.json()
                setEvents(data.events || [])
            }
        } catch (e) {
            setError("Connection failed")
        } finally {
            setIsLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchStatus()
        const interval = setInterval(fetchStatus, refreshInterval)
        return () => clearInterval(interval)
    }, [fetchStatus, refreshInterval])

    const getStateColor = (state: string) => {
        switch (state?.toUpperCase()) {
            case "TRAINING": return "text-emerald-400 bg-emerald-500/20"
            case "IDLE": return "text-blue-400 bg-blue-500/20"
            case "PAUSED": return "text-amber-400 bg-amber-500/20"
            case "COMPLETED": return "text-purple-400 bg-purple-500/20"
            case "ERROR": return "text-red-400 bg-red-500/20"
            default: return "text-gray-400 bg-gray-500/20"
        }
    }

    const getStateIcon = (state: string) => {
        switch (state?.toUpperCase()) {
            case "TRAINING": return <Loader2 className="w-4 h-4 animate-spin" />
            case "IDLE": return <Clock className="w-4 h-4" />
            case "COMPLETED": return <CheckCircle className="w-4 h-4" />
            case "ERROR": return <AlertCircle className="w-4 h-4" />
            default: return <Activity className="w-4 h-4" />
        }
    }

    const progress = status?.auto_training?.progress ?? 0
    const epoch = status?.auto_training?.epoch ?? 0
    const totalEpochs = status?.auto_training?.total_epochs ?? 0
    const state = status?.auto_training?.state ?? "UNKNOWN"

    // Circular progress calculation
    const circumference = 2 * Math.PI * 45
    const strokeDashoffset = circumference - (progress / 100) * circumference

    if (isLoading) {
        return (
            <div className={cn("p-6 rounded-2xl bg-card/50 border border-border/50", className)}>
                <div className="flex items-center justify-center h-32">
                    <Loader2 className="w-8 h-8 text-primary animate-spin" />
                </div>
            </div>
        )
    }

    if (error || !status?.available) {
        return (
            <div className={cn("p-6 rounded-2xl bg-card/50 border border-border/50", className)}>
                <div className="flex items-center gap-3 text-amber-400">
                    <AlertCircle className="w-5 h-5" />
                    <span className="text-sm">{error || "G38 modules not available"}</span>
                </div>
            </div>
        )
    }

    return (
        <div className={cn("p-6 rounded-2xl bg-card/50 border border-border/50", className)}>
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-500/20">
                        <TrendingUp className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h3 className="font-semibold text-sm">Training Progress</h3>
                        <p className="text-xs text-muted-foreground">G38 Auto-Training</p>
                    </div>
                </div>
                <div className={cn(
                    "flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium",
                    getStateColor(state)
                )}>
                    {getStateIcon(state)}
                    {state}
                </div>
            </div>

            {/* Progress Circle */}
            <div className="flex items-center justify-center mb-6">
                <div className="relative w-32 h-32">
                    <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
                        {/* Background circle */}
                        <circle
                            cx="50"
                            cy="50"
                            r="45"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="8"
                            className="text-muted/20"
                        />
                        {/* Progress circle */}
                        <circle
                            cx="50"
                            cy="50"
                            r="45"
                            fill="none"
                            stroke="url(#progressGradient)"
                            strokeWidth="8"
                            strokeLinecap="round"
                            strokeDasharray={circumference}
                            strokeDashoffset={strokeDashoffset}
                            className="transition-all duration-500 ease-out"
                        />
                        <defs>
                            <linearGradient id="progressGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                                <stop offset="0%" stopColor="#10b981" />
                                <stop offset="100%" stopColor="#06b6d4" />
                            </linearGradient>
                        </defs>
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <span className="text-3xl font-bold">{Math.round(progress)}%</span>
                        <span className="text-xs text-muted-foreground">Complete</span>
                    </div>
                </div>
            </div>

            {/* Epoch Counter */}
            <div className="text-center mb-6">
                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-muted/10 border border-border/50">
                    <Activity className="w-4 h-4 text-emerald-400" />
                    <span className="text-sm font-medium">
                        Epoch <span className="text-emerald-400">{epoch}</span> of <span className="text-muted-foreground">{totalEpochs}</span>
                    </span>
                </div>
            </div>

            {/* Status Indicators */}
            <div className="grid grid-cols-2 gap-3 mb-6">
                <div className={cn(
                    "flex items-center gap-2 p-3 rounded-lg border",
                    status.auto_training.gpu_available
                        ? "bg-emerald-500/10 border-emerald-500/20"
                        : "bg-muted/10 border-border/50"
                )}>
                    <Cpu className={cn("w-4 h-4", status.auto_training.gpu_available ? "text-emerald-400" : "text-muted-foreground")} />
                    <span className={cn("text-xs font-medium", status.auto_training.gpu_available ? "text-emerald-400" : "text-muted-foreground")}>
                        GPU {status.auto_training.gpu_available ? "Active" : "Inactive"}
                    </span>
                </div>
                <div className={cn(
                    "flex items-center gap-2 p-3 rounded-lg border",
                    status.auto_training.power_connected
                        ? "bg-blue-500/10 border-blue-500/20"
                        : "bg-amber-500/10 border-amber-500/20"
                )}>
                    <Battery className={cn("w-4 h-4", status.auto_training.power_connected ? "text-blue-400" : "text-amber-400")} />
                    <span className={cn("text-xs font-medium", status.auto_training.power_connected ? "text-blue-400" : "text-amber-400")}>
                        {status.auto_training.power_connected ? "Plugged In" : "Battery"}
                    </span>
                </div>
            </div>

            {/* Stats Row */}
            <div className="grid grid-cols-3 gap-2 mb-6">
                <div className="text-center p-2 rounded-lg bg-muted/5">
                    <p className="text-lg font-bold text-foreground">{status.auto_training.total_completed}</p>
                    <p className="text-xs text-muted-foreground">Total Done</p>
                </div>
                <div className="text-center p-2 rounded-lg bg-muted/5">
                    <p className="text-lg font-bold text-foreground">{status.auto_training.idle_seconds}s</p>
                    <p className="text-xs text-muted-foreground">Idle</p>
                </div>
                <div className="text-center p-2 rounded-lg bg-muted/5">
                    <p className="text-lg font-bold text-foreground">{status.auto_training.events_count}</p>
                    <p className="text-xs text-muted-foreground">Events</p>
                </div>
            </div>

            {/* Recent Events */}
            {events.length > 0 && (
                <div className="space-y-2">
                    <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Recent Events</h4>
                    <div className="space-y-1 max-h-32 overflow-y-auto">
                        {events.slice(0, 3).map((event) => (
                            <div
                                key={event.event_id}
                                className="flex items-center gap-2 p-2 rounded-lg bg-muted/5 text-xs"
                            >
                                <Zap className="w-3 h-3 text-amber-400 shrink-0" />
                                <span className="text-muted-foreground truncate flex-1">
                                    {event.event_type}: {event.details}
                                </span>
                                <span className="text-muted-foreground/50 shrink-0">
                                    {new Date(event.timestamp).toLocaleTimeString()}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Guards Status */}
            <div className="mt-4 pt-4 border-t border-border/50">
                <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">Guards Verified</span>
                    <span className={cn(
                        "font-medium",
                        status.guards.all_verified ? "text-emerald-400" : "text-amber-400"
                    )}>
                        {status.guards.main_guards} / {status.guards.main_guards}
                    </span>
                </div>
            </div>
        </div>
    )
}

export type { G38Status, TrainingEvent }
