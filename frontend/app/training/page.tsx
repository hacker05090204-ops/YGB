"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import {
    ArrowLeft,
    Brain,
    CheckCircle,
    Clock,
    Cpu,
    Database,
    Hash,
    Activity,
    Zap,
    Shield,
    RefreshCw,
    Play
} from "lucide-react"

import { ScrollArea } from "@/components/ui/scroll-area"

interface TrainingEvent {
    event_id: string
    event_type: string
    timestamp: string
    details: string
    idle_seconds: number
    gpu_used: boolean
    epoch: number | null
}

interface G38Status {
    available: boolean
    auto_training?: {
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
    guards?: {
        main_guards: number
        all_verified: boolean
        message: string
    }
}

const API_BASE = "http://localhost:8000"

export default function TrainingDashboard() {
    const [status, setStatus] = useState<G38Status | null>(null)
    const [events, setEvents] = useState<TrainingEvent[]>([])
    const [loading, setLoading] = useState(true)
    const [startingTraining, setStartingTraining] = useState(false)

    const fetchData = async () => {
        try {
            const [statusRes, eventsRes] = await Promise.all([
                fetch(`${API_BASE}/api/g38/status`),
                fetch(`${API_BASE}/api/g38/events?limit=100`)
            ])

            if (statusRes.ok) {
                const statusData = await statusRes.json()
                setStatus(statusData)
            }

            if (eventsRes.ok) {
                const eventsData = await eventsRes.json()
                setEvents(eventsData.events || [])
            }
        } catch (error) {
            console.error("Failed to fetch training data:", error)
        } finally {
            setLoading(false)
        }
    }

    const startTraining = async (epochs: number) => {
        setStartingTraining(true)
        try {
            await fetch(`${API_BASE}/api/g38/start?epochs=${epochs}`, { method: "POST" })
            await fetchData()
        } catch (error) {
            console.error("Failed to start training:", error)
        } finally {
            setStartingTraining(false)
        }
    }

    useEffect(() => {
        fetchData()
        const interval = setInterval(fetchData, 5000)
        return () => clearInterval(interval)
    }, [])

    const getEventColor = (type: string) => {
        switch (type) {
            case "TRAINING_STARTED": return "text-green-400"
            case "TRAINING_STOPPED": return "text-blue-400"
            case "CHECKPOINT_SAVED": return "text-purple-400"
            case "IDLE_DETECTED": return "text-yellow-400"
            case "MANUAL_START": return "text-cyan-400"
            case "ERROR": return "text-red-400"
            default: return "text-gray-400"
        }
    }

    const getEventIcon = (type: string) => {
        switch (type) {
            case "TRAINING_STARTED": return <Play className="w-4 h-4" />
            case "TRAINING_STOPPED": return <CheckCircle className="w-4 h-4" />
            case "CHECKPOINT_SAVED": return <Database className="w-4 h-4" />
            case "IDLE_DETECTED": return <Clock className="w-4 h-4" />
            default: return <Activity className="w-4 h-4" />
        }
    }

    const checkpoints = events.filter(e => e.event_type === "CHECKPOINT_SAVED")

    return (
        <div className="min-h-screen bg-[#000000] text-[#FAFAFA]">
            {/* Navigation */}
            <nav className="fixed top-0 left-0 right-0 z-50 bg-[#000000]/80 backdrop-blur-2xl border-b border-white/[0.06]">
                <div className="max-w-[1400px] mx-auto px-6 md:px-12 lg:px-24">
                    <div className="h-16 flex items-center justify-between">
                        <Link href="/" className="flex items-center gap-3 text-[#525252] hover:text-[#FAFAFA] transition-colors">
                            <ArrowLeft className="w-5 h-5" />
                            <span>Back to Dashboard</span>
                        </Link>
                        <div className="flex items-center gap-3">
                            <Brain className="w-5 h-5 text-purple-400" />
                            <span className="font-semibold">G38 Training Data</span>
                        </div>
                    </div>
                </div>
            </nav>

            <main className="pt-24 pb-16 px-6 md:px-12 lg:px-24">
                <div className="max-w-[1400px] mx-auto">

                    {/* Header */}
                    <div className="mb-8">
                        <h1 className="text-4xl font-bold mb-2">Training Dashboard</h1>
                        <p className="text-[#525252]">All G38 auto-training data and event history</p>
                    </div>

                    {loading ? (
                        <div className="flex items-center justify-center h-64">
                            <RefreshCw className="w-8 h-8 animate-spin text-[#525252]" />
                        </div>
                    ) : (
                        <>
                            {/* Summary Cards */}
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                                <div className="p-6 rounded-2xl bg-[#0A0A0A] border border-white/[0.06]">
                                    <div className="flex items-center gap-2 text-[#525252] text-sm mb-2">
                                        <Zap className="w-4 h-4" />
                                        Total Epochs
                                    </div>
                                    <div className="text-3xl font-bold text-[#FAFAFA]">
                                        {status?.auto_training?.total_completed || 0}
                                    </div>
                                </div>

                                <div className="p-6 rounded-2xl bg-[#0A0A0A] border border-white/[0.06]">
                                    <div className="flex items-center gap-2 text-[#525252] text-sm mb-2">
                                        <Activity className="w-4 h-4" />
                                        Total Events
                                    </div>
                                    <div className="text-3xl font-bold text-[#FAFAFA]">
                                        {status?.auto_training?.events_count || 0}
                                    </div>
                                </div>

                                <div className="p-6 rounded-2xl bg-[#0A0A0A] border border-white/[0.06]">
                                    <div className="flex items-center gap-2 text-[#525252] text-sm mb-2">
                                        <Database className="w-4 h-4" />
                                        Checkpoints
                                    </div>
                                    <div className="text-3xl font-bold text-purple-400">
                                        {checkpoints.length}
                                    </div>
                                </div>

                                <div className="p-6 rounded-2xl bg-[#0A0A0A] border border-white/[0.06]">
                                    <div className="flex items-center gap-2 text-[#525252] text-sm mb-2">
                                        <Shield className="w-4 h-4" />
                                        Guards
                                    </div>
                                    <div className="text-3xl font-bold text-green-400">
                                        {status?.guards?.main_guards || 0}
                                    </div>
                                    <div className="text-xs text-green-400 mt-1">
                                        {status?.guards?.all_verified ? "✓ All Verified" : "⚠ Check Guards"}
                                    </div>
                                </div>
                            </div>

                            {/* Current Status & Quick Actions */}
                            <div className="grid md:grid-cols-2 gap-6 mb-8">
                                {/* Current Status */}
                                <div className="p-6 rounded-2xl bg-[#0A0A0A] border border-white/[0.06]">
                                    <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                                        <Brain className={`w-5 h-5 ${status?.auto_training?.is_training ? "text-purple-400 animate-pulse" : "text-[#525252]"}`} />
                                        Current Status
                                    </h2>
                                    <div className="space-y-3">
                                        <div className="flex justify-between">
                                            <span className="text-[#525252]">State</span>
                                            <span className={`font-medium ${status?.auto_training?.is_training ? "text-purple-400" : "text-[#737373]"}`}>
                                                {status?.auto_training?.state || "UNKNOWN"}
                                            </span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-[#525252]">Progress</span>
                                            <span>{status?.auto_training?.progress || 0}%</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-[#525252]">Current Epoch</span>
                                            <span>{status?.auto_training?.epoch || 0} / {status?.auto_training?.total_epochs || 0}</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-[#525252]">Idle Time</span>
                                            <span>{status?.auto_training?.idle_seconds || 0}s</span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-[#525252]">GPU</span>
                                            <span className={status?.auto_training?.gpu_available ? "text-green-400" : "text-[#525252]"}>
                                                {status?.auto_training?.gpu_available ? "Available" : "CPU Only"}
                                            </span>
                                        </div>
                                    </div>
                                </div>

                                {/* Quick Actions */}
                                <div className="p-6 rounded-2xl bg-[#0A0A0A] border border-white/[0.06]">
                                    <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                                        <Play className="w-5 h-5 text-[#525252]" />
                                        Start Training
                                    </h2>
                                    <div className="grid grid-cols-3 gap-3">
                                        {[5, 10, 20, 50, 100, 200].map((epochs) => (
                                            <button
                                                key={epochs}
                                                onClick={() => startTraining(epochs)}
                                                disabled={startingTraining || status?.auto_training?.is_training}
                                                className="px-4 py-3 rounded-xl bg-[#171717] border border-white/[0.06] hover:bg-[#262626] hover:border-white/[0.1] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                                            >
                                                <div className="text-lg font-bold">{epochs}</div>
                                                <div className="text-xs text-[#525252]">epochs</div>
                                            </button>
                                        ))}
                                    </div>
                                    {status?.auto_training?.is_training && (
                                        <p className="text-sm text-purple-400 mt-4 text-center">Training in progress...</p>
                                    )}
                                </div>
                            </div>

                            {/* Checkpoints */}
                            <div className="mb-8 p-6 rounded-2xl bg-[#0A0A0A] border border-white/[0.06]">
                                <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                                    <Database className="w-5 h-5 text-purple-400" />
                                    Recent Checkpoints
                                </h2>
                                {checkpoints.length === 0 ? (
                                    <p className="text-[#525252] text-center py-8">No checkpoints yet</p>
                                ) : (
                                    <div className="grid gap-2">
                                        {checkpoints.slice(0, 10).map((cp) => (
                                            <div
                                                key={cp.event_id}
                                                className="flex items-center justify-between p-3 rounded-xl bg-[#171717] border border-white/[0.04]"
                                            >
                                                <div className="flex items-center gap-3">
                                                    <Hash className="w-4 h-4 text-purple-400" />
                                                    <span className="font-medium">Epoch {cp.epoch}</span>
                                                </div>
                                                <div className="flex items-center gap-4">
                                                    <code className="text-xs text-[#525252] bg-[#0A0A0A] px-2 py-1 rounded">
                                                        {cp.details.includes("hash:") ? cp.details.split("hash: ")[1]?.replace(")", "") : "N/A"}
                                                    </code>
                                                    <span className="text-xs text-[#404040]">
                                                        {new Date(cp.timestamp).toLocaleTimeString()}
                                                    </span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>

                            {/* Event History */}
                            <div className="p-6 rounded-2xl bg-[#0A0A0A] border border-white/[0.06]">
                                <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                                    <Activity className="w-5 h-5 text-[#525252]" />
                                    Event History (Last 100)
                                </h2>
                                <ScrollArea className="h-[400px]">
                                    <div className="space-y-2">
                                        {events.length === 0 ? (
                                            <p className="text-[#525252] text-center py-8">No events yet</p>
                                        ) : (
                                            events.map((event) => (
                                                <div
                                                    key={event.event_id}
                                                    className="flex items-center gap-3 p-3 rounded-xl bg-[#171717] border border-white/[0.04] hover:border-white/[0.08] transition-colors"
                                                >
                                                    <div className={getEventColor(event.event_type)}>
                                                        {getEventIcon(event.event_type)}
                                                    </div>
                                                    <div className="flex-1 min-w-0">
                                                        <div className="flex items-center gap-2">
                                                            <span className={`text-sm font-medium ${getEventColor(event.event_type)}`}>
                                                                {event.event_type}
                                                            </span>
                                                            {event.epoch !== null && (
                                                                <span className="text-xs text-[#404040]">Epoch {event.epoch}</span>
                                                            )}
                                                        </div>
                                                        <div className="text-xs text-[#525252] truncate">{event.details}</div>
                                                    </div>
                                                    <div className="text-xs text-[#404040] whitespace-nowrap">
                                                        {new Date(event.timestamp).toLocaleTimeString()}
                                                    </div>
                                                </div>
                                            ))
                                        )}
                                    </div>
                                </ScrollArea>
                            </div>
                        </>
                    )}
                </div>
            </main>
        </div>
    )
}
