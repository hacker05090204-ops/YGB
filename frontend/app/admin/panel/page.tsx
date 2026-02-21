"use client"

import { useState, useEffect, useCallback, useRef } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import {
    Shield,
    Cpu,
    Activity,
    Zap,
    Clock,
    Power,
    RefreshCw,
    LogOut,
    Settings,
    Users,
    Lock,
    Thermometer,
    HardDrive,
    Play,
    Pause,
    ChevronDown,
    CheckCircle,
    AlertTriangle,
    XCircle,
    ArrowLeft,
} from "lucide-react"

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

interface GpuStatus {
    available: boolean
    name: string
    temperature: number
    utilization: number
    memory_used_mb: number
    memory_total_mb: number
    power_draw_w: number
}

interface TrainingStatus {
    is_training: boolean
    continuous_mode: boolean
    epoch: number
    total_epochs: number
    loss: number
    accuracy: number
    samples_per_sec: number
    training_interval_sec: number
    monotonic_timestamp: number
    wall_clock_unix: number
    training_duration_seconds: number
    gpu_mem_allocated_mb: number
}

interface AuditEntry {
    timestamp: number
    action: string
    user_id: string
    ip: string
    details: string
}

export default function AdminPanel() {
    const router = useRouter()
    const [authenticated, setAuthenticated] = useState(false)
    const [userRole, setUserRole] = useState("")
    const [userId, setUserId] = useState("")

    // GPU Status
    const [gpu, setGpu] = useState<GpuStatus>({
        available: false,
        name: "Checking...",
        temperature: 0,
        utilization: 0,
        memory_used_mb: 0,
        memory_total_mb: 0,
        power_draw_w: 0,
    })

    // Training Status
    const [training, setTraining] = useState<TrainingStatus>({
        is_training: false,
        continuous_mode: false,
        epoch: 0,
        total_epochs: 100,
        loss: 0,
        accuracy: 0,
        samples_per_sec: 0,
        training_interval_sec: 3,
        monotonic_timestamp: 0,
        wall_clock_unix: 0,
        training_duration_seconds: 0,
        gpu_mem_allocated_mb: 0,
    })

    // Monotonic clock
    const [monotonicDisplay, setMonotonicDisplay] = useState("00:00:00.000")
    const monotonicRef = useRef<number>(0)

    // Settings
    const [continuousMode, setContinuousMode] = useState(false)
    const [interval, setInterval_] = useState(3)
    const [showIntervalDropdown, setShowIntervalDropdown] = useState(false)
    const intervalOptions = [3, 6, 10, 30, 60]

    // Audit log
    const [auditLog, setAuditLog] = useState<AuditEntry[]>([])

    // Live refresh
    const [autoRefresh, setAutoRefresh] = useState(true)
    const [lastRefresh, setLastRefresh] = useState(Date.now())

    // Auth check
    useEffect(() => {
        const token = localStorage.getItem("ygb_session")
        if (!token) {
            router.push("/admin")
            return
        }

        fetch(`${API_BASE}/admin/verify`, {
            headers: { Authorization: `Bearer ${token}` },
        })
            .then((r) => r.json())
            .then((data) => {
                if (data.status === "ok") {
                    setAuthenticated(true)
                    setUserRole(data.role)
                    setUserId(data.user_id)
                } else {
                    localStorage.removeItem("ygb_session")
                    router.push("/admin")
                }
            })
            .catch(() => {
                router.push("/admin")
            })
    }, [router])

    // Fetch status
    const fetchStatus = useCallback(async () => {
        const token = localStorage.getItem("ygb_session")
        if (!token) return

        try {
            const headers = { Authorization: `Bearer ${token}` }

            const [gpuRes, trainRes] = await Promise.allSettled([
                fetch(`${API_BASE}/gpu/status`, { headers }).then((r) => r.json()),
                fetch(`${API_BASE}/training/status`, { headers }).then((r) => r.json()),
            ])

            if (gpuRes.status === "fulfilled" && gpuRes.value) {
                setGpu(gpuRes.value)
            }

            if (trainRes.status === "fulfilled" && trainRes.value) {
                setTraining(trainRes.value)
                monotonicRef.current = trainRes.value.monotonic_timestamp || 0
                setContinuousMode(trainRes.value.continuous_mode || false)
                setInterval_(trainRes.value.training_interval_sec || 3)
            }

            setLastRefresh(Date.now())
        } catch { }
    }, [])

    // Auto refresh polling
    useEffect(() => {
        if (!authenticated || !autoRefresh) return
        fetchStatus()
        const timer = window.setInterval(fetchStatus, (interval || 3) * 1000)
        return () => window.clearInterval(timer)
    }, [authenticated, autoRefresh, interval, fetchStatus])

    // Monotonic clock display
    useEffect(() => {
        const timer = window.setInterval(() => {
            const ts = monotonicRef.current
            if (ts <= 0) {
                setMonotonicDisplay("00:00:00.000")
                return
            }
            const now = Date.now() / 1000
            const elapsed = now - (ts > 1e10 ? ts / 1000 : ts)
            const h = Math.floor(elapsed / 3600)
            const m = Math.floor((elapsed % 3600) / 60)
            const s = Math.floor(elapsed % 60)
            const ms = Math.floor((elapsed * 1000) % 1000)
            setMonotonicDisplay(
                `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}.${String(ms).padStart(3, "0")}`
            )
        }, 50)
        return () => window.clearInterval(timer)
    }, [])

    // Toggle training
    const toggleTraining = async () => {
        const token = localStorage.getItem("ygb_session")
        if (!token) return
        try {
            await fetch(`${API_BASE}/training/${training.is_training ? "stop" : "start"}`, {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${token}`,
                    "Content-Type": "application/json",
                },
            })
            fetchStatus()
        } catch { }
    }

    // Toggle 24/7 mode
    const toggle247 = async () => {
        const token = localStorage.getItem("ygb_session")
        if (!token) return
        try {
            await fetch(`${API_BASE}/training/continuous`, {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${token}`,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ enabled: !continuousMode }),
            })
            setContinuousMode(!continuousMode)
            fetchStatus()
        } catch { }
    }

    // Set interval
    const setTrainingInterval = async (sec: number) => {
        const token = localStorage.getItem("ygb_session")
        if (!token) return
        try {
            await fetch(`${API_BASE}/training/interval`, {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${token}`,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ interval_sec: sec }),
            })
            setInterval_(sec)
            setShowIntervalDropdown(false)
            fetchStatus()
        } catch { }
    }

    // Logout
    const handleLogout = () => {
        localStorage.removeItem("ygb_session")
        localStorage.removeItem("ygb_jwt")
        router.push("/admin")
    }

    if (!authenticated) {
        return (
            <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-violet-500/30 border-t-violet-500 rounded-full animate-spin" />
            </div>
        )
    }

    const tempColor =
        gpu.temperature > 85
            ? "text-red-400"
            : gpu.temperature > 70
                ? "text-amber-400"
                : "text-emerald-400"

    return (
        <div className="min-h-screen bg-[#0a0a0f] text-white">
            {/* Background */}
            <div className="fixed inset-0 bg-gradient-to-br from-violet-950/10 via-transparent to-cyan-950/10 pointer-events-none" />

            {/* Header */}
            <header className="relative border-b border-white/5 px-6 py-4">
                <div className="max-w-7xl mx-auto flex items-center justify-between">
                    <div className="flex items-center gap-4">
                        <Link href="/dashboard" className="text-white/40 hover:text-white/70 transition-colors">
                            <ArrowLeft className="w-5 h-5" />
                        </Link>
                        <div className="flex items-center gap-3">
                            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-violet-500 to-cyan-500 flex items-center justify-center">
                                <Shield className="w-5 h-5 text-white" />
                            </div>
                            <div>
                                <h1 className="text-lg font-semibold">Admin Panel</h1>
                                <p className="text-xs text-white/30">{userId} · {userRole}</p>
                            </div>
                        </div>
                    </div>
                    <div className="flex items-center gap-3">
                        <button
                            onClick={() => setAutoRefresh(!autoRefresh)}
                            className={`p-2 rounded-lg border transition-all ${autoRefresh ? "border-emerald-500/30 text-emerald-400 bg-emerald-500/5" : "border-white/10 text-white/30"}`}
                            title={autoRefresh ? "Auto-refresh ON" : "Auto-refresh OFF"}
                        >
                            <RefreshCw className={`w-4 h-4 ${autoRefresh ? "animate-spin" : ""}`} style={{ animationDuration: "3s" }} />
                        </button>
                        <button
                            onClick={handleLogout}
                            className="p-2 rounded-lg border border-white/10 text-white/40 hover:text-red-400 hover:border-red-500/30 transition-all"
                            title="Logout"
                        >
                            <LogOut className="w-4 h-4" />
                        </button>
                    </div>
                </div>
            </header>

            <main className="relative max-w-7xl mx-auto px-6 py-8 space-y-8">
                {/* ============================================= */}
                {/* MONOTONIC CLOCK - Real-time */}
                {/* ============================================= */}
                <div className="text-center">
                    <p className="text-xs text-white/30 uppercase tracking-widest mb-1">Monotonic Clock</p>
                    <p className="text-4xl font-mono font-bold bg-gradient-to-r from-violet-400 to-cyan-400 bg-clip-text text-transparent">
                        {monotonicDisplay}
                    </p>
                    <p className="text-xs text-white/20 mt-1">
                        Last refresh: {new Date(lastRefresh).toLocaleTimeString()}
                    </p>
                </div>

                {/* ============================================= */}
                {/* GPU STATUS */}
                {/* ============================================= */}
                <section>
                    <h2 className="text-sm font-medium text-white/40 uppercase tracking-wider mb-4 flex items-center gap-2">
                        <Cpu className="w-4 h-4" /> GPU Status
                    </h2>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        {/* GPU Available */}
                        <div className="backdrop-blur-xl bg-white/[0.03] border border-white/10 rounded-xl p-4">
                            <div className="flex items-center gap-2 mb-2">
                                {gpu.available ? (
                                    <CheckCircle className="w-4 h-4 text-emerald-400" />
                                ) : (
                                    <XCircle className="w-4 h-4 text-red-400" />
                                )}
                                <span className="text-xs text-white/40">Status</span>
                            </div>
                            <p className="text-lg font-semibold">{gpu.available ? "Online" : "Offline"}</p>
                            <p className="text-xs text-white/30 truncate">{gpu.name}</p>
                        </div>

                        {/* Temperature */}
                        <div className="backdrop-blur-xl bg-white/[0.03] border border-white/10 rounded-xl p-4">
                            <div className="flex items-center gap-2 mb-2">
                                <Thermometer className={`w-4 h-4 ${tempColor}`} />
                                <span className="text-xs text-white/40">Temperature</span>
                            </div>
                            <p className={`text-lg font-semibold ${tempColor}`}>{gpu.temperature}°C</p>
                            <div className="mt-2 h-1 rounded-full bg-white/5">
                                <div
                                    className={`h-full rounded-full transition-all ${gpu.temperature > 85 ? "bg-red-500" : gpu.temperature > 70 ? "bg-amber-500" : "bg-emerald-500"}`}
                                    style={{ width: `${Math.min(100, (gpu.temperature / 100) * 100)}%` }}
                                />
                            </div>
                        </div>

                        {/* VRAM */}
                        <div className="backdrop-blur-xl bg-white/[0.03] border border-white/10 rounded-xl p-4">
                            <div className="flex items-center gap-2 mb-2">
                                <HardDrive className="w-4 h-4 text-cyan-400" />
                                <span className="text-xs text-white/40">VRAM</span>
                            </div>
                            <p className="text-lg font-semibold">{gpu.memory_used_mb}MB</p>
                            <p className="text-xs text-white/30">of {gpu.memory_total_mb}MB</p>
                            <div className="mt-2 h-1 rounded-full bg-white/5">
                                <div
                                    className="h-full rounded-full bg-cyan-500 transition-all"
                                    style={{ width: `${gpu.memory_total_mb > 0 ? (gpu.memory_used_mb / gpu.memory_total_mb) * 100 : 0}%` }}
                                />
                            </div>
                        </div>

                        {/* Power */}
                        <div className="backdrop-blur-xl bg-white/[0.03] border border-white/10 rounded-xl p-4">
                            <div className="flex items-center gap-2 mb-2">
                                <Zap className="w-4 h-4 text-amber-400" />
                                <span className="text-xs text-white/40">Power</span>
                            </div>
                            <p className="text-lg font-semibold">{gpu.power_draw_w}W</p>
                            <p className="text-xs text-white/30">Utilization: {gpu.utilization}%</p>
                        </div>
                    </div>
                </section>

                {/* ============================================= */}
                {/* TRAINING CONTROLS */}
                {/* ============================================= */}
                <section>
                    <h2 className="text-sm font-medium text-white/40 uppercase tracking-wider mb-4 flex items-center gap-2">
                        <Activity className="w-4 h-4" /> Training Controls
                    </h2>
                    <div className="backdrop-blur-xl bg-white/[0.03] border border-white/10 rounded-2xl p-6">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                            {/* Training Toggle */}
                            <div className="flex flex-col items-center gap-4 p-4 rounded-xl bg-white/[0.02] border border-white/5">
                                <p className="text-sm text-white/40">Training</p>
                                <button
                                    onClick={toggleTraining}
                                    className={`w-20 h-20 rounded-full flex items-center justify-center transition-all ${training.is_training
                                            ? "bg-emerald-500/20 border-2 border-emerald-500 text-emerald-400 shadow-lg shadow-emerald-500/20"
                                            : "bg-white/5 border-2 border-white/10 text-white/40 hover:border-white/20"
                                        }`}
                                >
                                    {training.is_training ? <Pause className="w-8 h-8" /> : <Play className="w-8 h-8 ml-1" />}
                                </button>
                                <p className="text-xs text-white/40">
                                    {training.is_training ? "Running" : "Stopped"}
                                </p>
                            </div>

                            {/* 24/7 Toggle */}
                            <div className="flex flex-col items-center gap-4 p-4 rounded-xl bg-white/[0.02] border border-white/5">
                                <p className="text-sm text-white/40">24/7 Mode</p>
                                <button
                                    onClick={toggle247}
                                    className={`relative w-16 h-8 rounded-full transition-all ${continuousMode ? "bg-violet-500" : "bg-white/10"
                                        }`}
                                >
                                    <div
                                        className={`absolute top-1 w-6 h-6 rounded-full bg-white shadow transition-transform ${continuousMode ? "translate-x-9" : "translate-x-1"
                                            }`}
                                    />
                                </button>
                                <p className="text-xs text-white/40">
                                    {continuousMode ? "Always On" : "Manual"}
                                </p>
                            </div>

                            {/* Interval Selector */}
                            <div className="flex flex-col items-center gap-4 p-4 rounded-xl bg-white/[0.02] border border-white/5">
                                <p className="text-sm text-white/40">Refresh Interval</p>
                                <div className="relative">
                                    <button
                                        onClick={() => setShowIntervalDropdown(!showIntervalDropdown)}
                                        className="flex items-center gap-2 px-4 py-2 rounded-lg border border-white/10 bg-white/5 text-white hover:border-white/20 transition-all"
                                    >
                                        <Clock className="w-4 h-4 text-white/40" />
                                        <span className="font-mono">{interval}s</span>
                                        <ChevronDown className="w-4 h-4 text-white/30" />
                                    </button>
                                    {showIntervalDropdown && (
                                        <div className="absolute top-full mt-2 left-0 right-0 bg-[#1a1a2e] border border-white/10 rounded-lg overflow-hidden z-10 shadow-xl">
                                            {intervalOptions.map((opt) => (
                                                <button
                                                    key={opt}
                                                    onClick={() => setTrainingInterval(opt)}
                                                    className={`w-full px-4 py-2 text-left text-sm hover:bg-white/5 transition-colors ${interval === opt ? "text-violet-400" : "text-white/60"
                                                        }`}
                                                >
                                                    {opt}s {opt === 3 ? "(fast)" : opt === 60 ? "(slow)" : ""}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>
                                <p className="text-xs text-white/40">Polling rate</p>
                            </div>
                        </div>

                        {/* Live Telemetry */}
                        <div className="mt-6 pt-6 border-t border-white/5">
                            <h3 className="text-sm text-white/40 mb-4">Live Telemetry</h3>
                            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                                <div className="text-center">
                                    <p className="text-2xl font-bold font-mono text-violet-400">{training.epoch}</p>
                                    <p className="text-xs text-white/30">Epoch</p>
                                </div>
                                <div className="text-center">
                                    <p className="text-2xl font-bold font-mono text-cyan-400">{training.loss.toFixed(4)}</p>
                                    <p className="text-xs text-white/30">Loss</p>
                                </div>
                                <div className="text-center">
                                    <p className="text-2xl font-bold font-mono text-emerald-400">{(training.accuracy * 100).toFixed(1)}%</p>
                                    <p className="text-xs text-white/30">Accuracy</p>
                                </div>
                                <div className="text-center">
                                    <p className="text-2xl font-bold font-mono text-amber-400">{training.samples_per_sec.toFixed(0)}</p>
                                    <p className="text-xs text-white/30">Samples/sec</p>
                                </div>
                                <div className="text-center">
                                    <p className="text-2xl font-bold font-mono text-pink-400">{training.gpu_mem_allocated_mb}MB</p>
                                    <p className="text-xs text-white/30">GPU Mem</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>

                {/* ============================================= */}
                {/* SECURITY STATUS */}
                {/* ============================================= */}
                <section>
                    <h2 className="text-sm font-medium text-white/40 uppercase tracking-wider mb-4 flex items-center gap-2">
                        <Lock className="w-4 h-4" /> Security
                    </h2>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div className="backdrop-blur-xl bg-white/[0.03] border border-white/10 rounded-xl p-4">
                            <div className="flex items-center gap-2 mb-2">
                                <Shield className="w-4 h-4 text-emerald-400" />
                                <span className="text-sm text-white/60">Auth Method</span>
                            </div>
                            <p className="text-lg font-semibold">OAuth + TOTP</p>
                        </div>
                        <div className="backdrop-blur-xl bg-white/[0.03] border border-white/10 rounded-xl p-4">
                            <div className="flex items-center gap-2 mb-2">
                                <Users className="w-4 h-4 text-violet-400" />
                                <span className="text-sm text-white/60">Role</span>
                            </div>
                            <p className="text-lg font-semibold">{userRole}</p>
                        </div>
                        <div className="backdrop-blur-xl bg-white/[0.03] border border-white/10 rounded-xl p-4">
                            <div className="flex items-center gap-2 mb-2">
                                <Settings className="w-4 h-4 text-cyan-400" />
                                <span className="text-sm text-white/60">Session</span>
                            </div>
                            <p className="text-lg font-semibold">Active</p>
                            <p className="text-xs text-white/30">JWT + HTTPOnly cookie</p>
                        </div>
                    </div>
                </section>
            </main>
        </div>
    )
}
