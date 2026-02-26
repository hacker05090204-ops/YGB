"use client"

import { useState, useEffect, useCallback } from "react"
import { authFetch } from "@/lib/ygb-api"
import Link from "next/link"
import {
    ArrowLeft,
    Shield,
    CheckCircle,
    Clock,
    Lock,
    Unlock,
    Zap,
    Activity,
    Target,
    Play,
    Crosshair,
    AlertTriangle,
    ChevronRight,
    Cpu,
    RefreshCw,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

// =========================================================================
// TYPES
// =========================================================================

interface FieldThresholds {
    min_precision: number
    max_fpr: number
    min_dup: number
    max_ece: number
    min_stability_days: number
}

interface FieldProgress {
    overall_percent: number
    precision_score: number | null
    fpr_score: number | null
    dup_score: number | null
    ece_score: number | null
    stability_score: number
    metrics_available: number
    metrics_total: number
    status: string
}

interface FieldData {
    id: number
    name: string
    tier: number
    label: string
    state: string
    precision: number | null
    fpr: number | null
    dup_detection: number | null
    ece: number | null
    stability_days: number
    human_approved: boolean
    active: boolean
    locked: boolean
    certified: boolean
    frozen: boolean
    progress: FieldProgress
    thresholds: FieldThresholds
}

interface LadderState {
    active_field_id: number
    certified_count: number
    total_fields: number
    fields: FieldData[]
    last_updated: string
}

interface AuthorityLock {
    all_locked: boolean
    total_locks: number
    violations: string[]
    status: string
}

interface LedgerStatus {
    entry_count: number
    chain_hash: string
    chain_valid: boolean
}

interface RuntimeStatus {
    containment_active: boolean
    containment_reason: string | null
    precision_breach: boolean
    drift_alert: boolean
    freeze_valid: boolean
    freeze_reason: string | null
    training_velocity_samples_hr: number | null
    training_velocity_batches_sec: number | null
    gpu_utilization: number | null
    determinism_pass: boolean | null
    data_freshness: string | null
    merge_status: string | null
}

interface ApiResponse {
    status: string
    ladder: LadderState
    authority_lock: AuthorityLock
    approval_ledger: LedgerStatus
    runtime: RuntimeStatus | null
    timestamp: string
}

// =========================================================================
// HELPERS
// =========================================================================

function stateColor(state: string): string {
    switch (state) {
        case "NOT_STARTED": return "bg-zinc-800 text-zinc-400"
        case "TRAINING": return "bg-blue-900/60 text-blue-300 animate-pulse"
        case "STABILITY_CHECK": return "bg-amber-900/60 text-amber-300"
        case "CERTIFICATION_PENDING": return "bg-purple-900/60 text-purple-300"
        case "CERTIFIED": return "bg-emerald-900/60 text-emerald-300"
        case "FROZEN": return "bg-cyan-900/60 text-cyan-300"
        case "NEXT_FIELD": return "bg-zinc-700 text-zinc-300"
        default: return "bg-zinc-800 text-zinc-400"
    }
}

function tierBadge(tier: number): string {
    switch (tier) {
        case 1: return "bg-amber-500/20 text-amber-400 border-amber-500/30"
        case 2: return "bg-blue-500/20 text-blue-400 border-blue-500/30"
        case 3: return "bg-purple-500/20 text-purple-400 border-purple-500/30"
        default: return "bg-zinc-500/20 text-zinc-400 border-zinc-500/30"
    }
}

function stateIcon(state: string) {
    switch (state) {
        case "NOT_STARTED": return <Lock className="h-3.5 w-3.5" />
        case "TRAINING": return <Zap className="h-3.5 w-3.5" />
        case "STABILITY_CHECK": return <Clock className="h-3.5 w-3.5" />
        case "CERTIFICATION_PENDING": return <AlertTriangle className="h-3.5 w-3.5" />
        case "CERTIFIED": return <CheckCircle className="h-3.5 w-3.5" />
        case "FROZEN": return <Shield className="h-3.5 w-3.5" />
        case "NEXT_FIELD": return <Unlock className="h-3.5 w-3.5" />
        default: return <Lock className="h-3.5 w-3.5" />
    }
}

function metricDisplay(value: number | null, label: string, unit: string = "%"): string {
    if (value === null || value === undefined) return "Awaiting Data"
    return `${(value * 100).toFixed(1)}${unit}`
}

// =========================================================================
// COMPONENT
// =========================================================================

export default function FieldProgressionDashboard() {
    const [data, setData] = useState<ApiResponse | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [selectedField, setSelectedField] = useState<number>(0)
    const [actionStatus, setActionStatus] = useState<string | null>(null)
    const [lastFetchTime, setLastFetchTime] = useState<number>(Date.now())
    const isStale = Date.now() - lastFetchTime > 60000

    const fetchData = useCallback(async () => {
        try {
            const res = await authFetch(`${API_BASE}/fields/state`)
            if (!res.ok) throw new Error(`HTTP ${res.status}`)
            const json = await res.json()
            setData(json)
            setError(null)
            setLastFetchTime(Date.now())
        } catch {
            setError("Failed to connect to backend API")
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchData()
        const interval = setInterval(fetchData, 30000)
        return () => clearInterval(interval)
    }, [fetchData])

    const handleTrain = async () => {
        setActionStatus("Starting training...")
        try {
            const res = await authFetch(`${API_BASE}/training/start`, { method: "POST" })
            const json = await res.json()
            setActionStatus(json.message || json.status)
            fetchData()
        } catch {
            setActionStatus("Failed to start training")
        }
    }

    const handleHunt = async () => {
        setActionStatus("Checking hunt gates...")
        try {
            const res = await authFetch(`${API_BASE}/hunt/start`, { method: "POST" })
            const json = await res.json()
            setActionStatus(json.message || json.status)
            fetchData()
        } catch {
            setActionStatus("Failed to start hunt")
        }
    }

    const handleApprove = async (fieldId: number) => {
        setActionStatus(`Approving field ${fieldId}...`)
        try {
            const res = await authFetch(`${API_BASE}/fields/approve/${fieldId}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    approver_id: "human-operator",
                    reason: "Manual certification approval via dashboard",
                }),
            })
            const json = await res.json()
            setActionStatus(json.message || json.status)
            fetchData()
        } catch {
            setActionStatus("Failed to approve field")
        }
    }

    if (loading) {
        return (
            <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
                <div className="text-center space-y-4">
                    <RefreshCw className="h-8 w-8 text-blue-400 animate-spin mx-auto" />
                    <p className="text-zinc-400">Loading field state...</p>
                </div>
            </div>
        )
    }

    const ladder = data?.ladder
    const fields = ladder?.fields || []
    const activeField = fields.find(f => f.active) || fields[0]
    const selected = fields[selectedField] || fields[0]
    const authLock = data?.authority_lock
    const ledger = data?.approval_ledger

    // Hunt gate check
    const canHunt = activeField?.certified && activeField?.frozen &&
        activeField?.human_approved && authLock?.all_locked

    return (
        <div className="min-h-screen bg-zinc-950 text-zinc-100">
            {/* Header */}
            <div className="sticky top-0 z-50 bg-zinc-950/80 backdrop-blur-xl border-b border-zinc-800">
                <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <Link href="/" className="text-zinc-400 hover:text-white transition-colors">
                            <ArrowLeft className="h-5 w-5" />
                        </Link>
                        <div>
                            <h1 className="text-lg font-bold tracking-tight">
                                Field Progression Engine
                            </h1>
                            <p className="text-xs text-zinc-500">
                                {ladder?.certified_count || 0}/{ladder?.total_fields || 23} fields certified
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        {/* Train Button */}
                        <button
                            onClick={handleTrain}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg
                                       bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium
                                       transition-all duration-200 hover:scale-105"
                        >
                            <Play className="h-3.5 w-3.5" /> Train
                        </button>

                        {/* Hunt Button */}
                        <button
                            onClick={handleHunt}
                            disabled={!canHunt}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium
                                       transition-all duration-200 ${canHunt
                                    ? "bg-red-600 hover:bg-red-500 text-white hover:scale-105"
                                    : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
                                }`}
                        >
                            <Crosshair className="h-3.5 w-3.5" /> Hunt
                            {!canHunt && <Lock className="h-3 w-3" />}
                        </button>

                        <button
                            onClick={fetchData}
                            className="p-1.5 rounded-lg text-zinc-400 hover:text-white
                                       hover:bg-zinc-800 transition-colors"
                        >
                            <RefreshCw className="h-4 w-4" />
                        </button>
                    </div>
                </div>
            </div>

            {/* Action feedback */}
            {actionStatus && (
                <div className="max-w-7xl mx-auto px-4 pt-2">
                    <div className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-sm
                                    text-zinc-300 flex items-center justify-between">
                        <span>{actionStatus}</span>
                        <button
                            onClick={() => setActionStatus(null)}
                            className="text-zinc-500 hover:text-white"
                        >×</button>
                    </div>
                </div>
            )}

            {error && (
                <div className="max-w-7xl mx-auto px-4 pt-2">
                    <div className="bg-red-950/30 border border-red-800/50 rounded-lg px-3 py-2
                                    text-sm text-red-300">
                        ⚠ {error} — showing default state
                    </div>
                </div>
            )}

            {isStale && !error && (
                <div className="max-w-7xl mx-auto px-4 pt-2">
                    <div className="bg-amber-950/30 border border-amber-800/50 rounded-lg px-3 py-2
                                    text-sm text-amber-300 flex items-center justify-between">
                        <span>⚠ Dashboard data is stale — last update &gt; 60s ago</span>
                        <button onClick={fetchData} className="text-amber-400 hover:text-white text-xs underline">
                            Refresh Now
                        </button>
                    </div>
                </div>
            )}

            <div className="max-w-7xl mx-auto px-4 py-4 space-y-4">
                {/* Overview Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <Card className="bg-zinc-900 border-zinc-800">
                        <CardContent className="p-3">
                            <div className="flex items-center gap-2 text-zinc-400 text-xs mb-1">
                                <Target className="h-3.5 w-3.5" /> Active Field
                            </div>
                            <p className="text-sm font-semibold truncate">
                                {activeField?.name || "None"}
                            </p>
                            <Badge className={`mt-1 text-[10px] ${stateColor(activeField?.state || "")}`}>
                                {stateIcon(activeField?.state || "")}
                                <span className="ml-1">{activeField?.state}</span>
                            </Badge>
                        </CardContent>
                    </Card>

                    <Card className="bg-zinc-900 border-zinc-800">
                        <CardContent className="p-3">
                            <div className="flex items-center gap-2 text-zinc-400 text-xs mb-1">
                                <Activity className="h-3.5 w-3.5" /> Progress
                            </div>
                            <p className="text-2xl font-bold">
                                {activeField?.progress?.overall_percent?.toFixed(1) || "0.0"}%
                            </p>
                            <Progress
                                value={activeField?.progress?.overall_percent || 0}
                                className="mt-1 h-1.5"
                            />
                        </CardContent>
                    </Card>

                    <Card className="bg-zinc-900 border-zinc-800">
                        <CardContent className="p-3">
                            <div className="flex items-center gap-2 text-zinc-400 text-xs mb-1">
                                <Shield className="h-3.5 w-3.5" /> Authority Lock
                            </div>
                            <p className={`text-sm font-semibold ${authLock?.all_locked ? "text-emerald-400" : "text-red-400"
                                }`}>
                                {authLock?.all_locked ? "ALL LOCKED" : "VIOLATION"}
                            </p>
                            <p className="text-[10px] text-zinc-500 mt-1">
                                {authLock?.total_locks || 0} guards active
                            </p>
                        </CardContent>
                    </Card>

                    <Card className="bg-zinc-900 border-zinc-800">
                        <CardContent className="p-3">
                            <div className="flex items-center gap-2 text-zinc-400 text-xs mb-1">
                                <Cpu className="h-3.5 w-3.5" /> Approval Ledger
                            </div>
                            <p className={`text-sm font-semibold ${ledger?.chain_valid ? "text-emerald-400" : "text-red-400"
                                }`}>
                                {ledger?.chain_valid ? "INTACT" : "TAMPERED"}
                            </p>
                            <p className="text-[10px] text-zinc-500 mt-1">
                                {ledger?.entry_count || 0} entries
                            </p>
                        </CardContent>
                    </Card>
                </div>

                {/* Main Content */}
                <Tabs defaultValue="ladder" className="space-y-3">
                    <TabsList className="bg-zinc-900 border border-zinc-800">
                        <TabsTrigger value="ladder">Field Ladder</TabsTrigger>
                        <TabsTrigger value="metrics">Metrics Detail</TabsTrigger>
                        <TabsTrigger value="runtime">Runtime</TabsTrigger>
                    </TabsList>

                    {/* ===== LADDER TAB ===== */}
                    <TabsContent value="ladder" className="space-y-2">
                        <ScrollArea className="h-[calc(100vh-340px)]">
                            <div className="space-y-1.5">
                                {fields.map((field) => (
                                    <button
                                        key={field.id}
                                        onClick={() => setSelectedField(field.id)}
                                        className={`w-full text-left rounded-lg border transition-all
                                                   duration-150 hover:border-zinc-600 p-3 ${selectedField === field.id
                                                ? "bg-zinc-800/80 border-blue-600/50"
                                                : "bg-zinc-900/50 border-zinc-800"
                                            } ${field.locked ? "opacity-50" : ""}`}
                                    >
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-2 min-w-0">
                                                <span className="text-[10px] text-zinc-600 font-mono w-5 shrink-0">
                                                    {String(field.id + 1).padStart(2, "0")}
                                                </span>
                                                <Badge
                                                    className={`shrink-0 text-[9px] border px-1.5 py-0 ${tierBadge(field.tier)}`}
                                                >
                                                    T{field.tier}
                                                </Badge>
                                                <span className="text-sm truncate">{field.name}</span>
                                            </div>
                                            <div className="flex items-center gap-2 shrink-0">
                                                <Badge className={`text-[10px] px-1.5 py-0 ${stateColor(field.state)}`}>
                                                    {stateIcon(field.state)}
                                                    <span className="ml-1 hidden sm:inline">{field.state}</span>
                                                </Badge>
                                                {(field as any).demoted && (
                                                    <Badge className="text-[9px] px-1 py-0 bg-red-900/80 text-red-300 border-red-700">
                                                        DEMOTED
                                                    </Badge>
                                                )}
                                                {field.human_approved && (
                                                    <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
                                                )}
                                                <ChevronRight className="h-3.5 w-3.5 text-zinc-600" />
                                            </div>
                                        </div>

                                        {/* Progress bar for non-locked fields */}
                                        {!field.locked && field.state !== "NOT_STARTED" && (
                                            <div className="mt-2 flex items-center gap-2">
                                                <Progress
                                                    value={field.progress?.overall_percent || 0}
                                                    className="h-1 flex-1"
                                                />
                                                <span className="text-[10px] text-zinc-500 w-10 text-right">
                                                    {field.progress?.overall_percent?.toFixed(0) || 0}%
                                                </span>
                                            </div>
                                        )}
                                    </button>
                                ))}
                            </div>
                        </ScrollArea>
                    </TabsContent>

                    {/* ===== METRICS TAB ===== */}
                    <TabsContent value="metrics" className="space-y-3">
                        <Card className="bg-zinc-900 border-zinc-800">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-base flex items-center gap-2">
                                    <span className="text-zinc-500 font-mono text-xs">
                                        #{selected.id + 1}
                                    </span>
                                    {selected.name}
                                    <Badge className={`text-[10px] border px-1.5 py-0 ${tierBadge(selected.tier)}`}>
                                        Tier {selected.tier}
                                    </Badge>
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                {/* State + Actions */}
                                <div className="flex items-center gap-2 flex-wrap">
                                    <Badge className={`${stateColor(selected.state)}`}>
                                        {stateIcon(selected.state)}
                                        <span className="ml-1">{selected.state}</span>
                                    </Badge>
                                    {selected.state === "CERTIFICATION_PENDING" && !selected.human_approved && (
                                        <button
                                            onClick={() => handleApprove(selected.id)}
                                            className="px-2 py-1 rounded bg-emerald-700 hover:bg-emerald-600
                                                       text-white text-xs font-medium transition-colors"
                                        >
                                            ✓ Approve Certification
                                        </button>
                                    )}
                                </div>

                                {/* Metric Cards */}
                                <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
                                    <MetricCard
                                        label="Precision"
                                        value={selected.precision}
                                        target={selected.thresholds?.min_precision}
                                        higher={true}
                                    />
                                    <MetricCard
                                        label="FPR"
                                        value={selected.fpr}
                                        target={selected.thresholds?.max_fpr}
                                        higher={false}
                                    />
                                    <MetricCard
                                        label="Dup Detection"
                                        value={selected.dup_detection}
                                        target={selected.thresholds?.min_dup}
                                        higher={true}
                                    />
                                    <MetricCard
                                        label="ECE"
                                        value={selected.ece}
                                        target={selected.thresholds?.max_ece}
                                        higher={false}
                                    />
                                    <div className="bg-zinc-800/50 rounded-lg p-2.5">
                                        <p className="text-[10px] text-zinc-500 uppercase tracking-wider">
                                            Stability
                                        </p>
                                        <p className="text-lg font-bold mt-0.5">
                                            {selected.stability_days}/7
                                        </p>
                                        <p className="text-[10px] text-zinc-500">days</p>
                                        <div className="mt-1.5">
                                            <Progress
                                                value={(selected.stability_days / 7) * 100}
                                                className="h-1"
                                            />
                                        </div>
                                    </div>
                                </div>

                                {/* Overall Progress */}
                                <div className="bg-zinc-800/30 rounded-lg p-3">
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-sm text-zinc-400">Overall Progress</span>
                                        <span className="text-sm font-bold">
                                            {selected.progress?.overall_percent?.toFixed(1) || "0.0"}%
                                        </span>
                                    </div>
                                    <Progress
                                        value={selected.progress?.overall_percent || 0}
                                        className="h-2"
                                    />
                                    <p className="text-[10px] text-zinc-500 mt-1.5">
                                        {selected.progress?.metrics_available || 0}/{selected.progress?.metrics_total || 5} metrics available
                                        — {selected.progress?.status || "Awaiting Data"}
                                    </p>
                                </div>
                            </CardContent>
                        </Card>
                    </TabsContent>

                    {/* ===== RUNTIME TAB ===== */}
                    <TabsContent value="runtime" className="space-y-3">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            {/* Containment Status */}
                            <Card className="bg-zinc-900 border-zinc-800">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm flex items-center gap-2">
                                        <Shield className="h-4 w-4 text-red-400" />
                                        Runtime Containment
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <p className={`text-lg font-bold ${data?.runtime?.containment_active
                                        ? "text-red-400" : data?.runtime
                                            ? "text-emerald-400" : "text-zinc-600"
                                        }`}>
                                        {data?.runtime?.containment_active
                                            ? "ACTIVE"
                                            : data?.runtime
                                                ? "CLEAR"
                                                : "Awaiting Data"}
                                    </p>
                                    <p className="text-[10px] text-zinc-500 mt-1">
                                        {data?.runtime?.containment_reason || "No containment events"}
                                    </p>
                                    <div className="mt-2 flex gap-3 text-[10px]">
                                        <span className={data?.runtime?.precision_breach ? "text-red-400" : "text-zinc-500"}>
                                            Precision: {data?.runtime?.precision_breach ? "BREACH" : data?.runtime ? "OK" : "Awaiting Data"}
                                        </span>
                                        <span className={data?.runtime?.drift_alert ? "text-amber-400" : "text-zinc-500"}>
                                            Drift: {data?.runtime?.drift_alert ? "ALERT" : data?.runtime ? "OK" : "Awaiting Data"}
                                        </span>
                                    </div>
                                </CardContent>
                            </Card>

                            {/* Freeze Validity */}
                            <Card className="bg-zinc-900 border-zinc-800">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm flex items-center gap-2">
                                        <Lock className="h-4 w-4 text-cyan-400" />
                                        Freeze Validity
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <p className={`text-lg font-bold ${data?.runtime?.freeze_valid === true
                                        ? "text-cyan-400"
                                        : data?.runtime?.freeze_valid === false
                                            ? "text-red-400"
                                            : "text-zinc-600"
                                        }`}>
                                        {data?.runtime?.freeze_valid === true
                                            ? "VALID"
                                            : data?.runtime?.freeze_valid === false
                                                ? "INVALID"
                                                : "Awaiting Data"}
                                    </p>
                                    <p className="text-[10px] text-zinc-500 mt-1">
                                        {data?.runtime?.freeze_reason || "No freeze events"}
                                    </p>
                                </CardContent>
                            </Card>

                            {/* Training Velocity */}
                            <Card className="bg-zinc-900 border-zinc-800">
                                <CardHeader className="pb-2">
                                    <CardTitle className="text-sm flex items-center gap-2">
                                        <Zap className="h-4 w-4 text-amber-400" />
                                        Training Velocity
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <div className="space-y-1.5">
                                        <div className="flex justify-between">
                                            <span className="text-[10px] text-zinc-500">Samples/hr</span>
                                            <span className="text-sm font-bold">
                                                {data?.runtime?.training_velocity_samples_hr != null
                                                    ? data.runtime.training_velocity_samples_hr.toLocaleString()
                                                    : "Awaiting Data"}
                                            </span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-[10px] text-zinc-500">Batches/sec</span>
                                            <span className="text-sm font-bold">
                                                {data?.runtime?.training_velocity_batches_sec != null
                                                    ? data.runtime.training_velocity_batches_sec.toFixed(2)
                                                    : "Awaiting Data"}
                                            </span>
                                        </div>
                                        <div className="flex justify-between">
                                            <span className="text-[10px] text-zinc-500">GPU Util</span>
                                            <span className="text-sm font-bold">
                                                {data?.runtime?.gpu_utilization != null
                                                    ? `${data.runtime.gpu_utilization}%`
                                                    : "Awaiting Data"}
                                            </span>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        </div>

                        {/* Second row: Determinism, Freshness, Merge */}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            <Card className="bg-zinc-900 border-zinc-800">
                                <CardContent className="p-3">
                                    <div className="flex items-center gap-2 text-zinc-400 text-xs mb-1">
                                        <Cpu className="h-3.5 w-3.5" />
                                        Determinism Proof
                                    </div>
                                    <p className={`text-sm font-semibold ${data?.runtime?.determinism_pass === true
                                        ? "text-emerald-400"
                                        : data?.runtime?.determinism_pass === false
                                            ? "text-red-400"
                                            : "text-zinc-600"
                                        }`}>
                                        {data?.runtime?.determinism_pass === true
                                            ? "3/3 PASS"
                                            : data?.runtime?.determinism_pass === false
                                                ? "FAIL"
                                                : "Awaiting Data"}
                                    </p>
                                </CardContent>
                            </Card>

                            <Card className="bg-zinc-900 border-zinc-800">
                                <CardContent className="p-3">
                                    <div className="flex items-center gap-2 text-zinc-400 text-xs mb-1">
                                        <Activity className="h-3.5 w-3.5" />
                                        Data Freshness
                                    </div>
                                    <p className={`text-sm font-semibold ${data?.runtime?.data_freshness === "HEALTHY"
                                        ? "text-emerald-400"
                                        : data?.runtime?.data_freshness
                                            ? "text-amber-400"
                                            : "text-zinc-600"
                                        }`}>
                                        {data?.runtime?.data_freshness || "Awaiting Data"}
                                    </p>
                                </CardContent>
                            </Card>

                            <Card className="bg-zinc-900 border-zinc-800">
                                <CardContent className="p-3">
                                    <div className="flex items-center gap-2 text-zinc-400 text-xs mb-1">
                                        <RefreshCw className="h-3.5 w-3.5" />
                                        Merge Status
                                    </div>
                                    <p className={`text-sm font-semibold ${data?.runtime?.merge_status === "APPROVED"
                                        ? "text-emerald-400"
                                        : data?.runtime?.merge_status
                                            ? "text-amber-400"
                                            : "text-zinc-600"
                                        }`}>
                                        {data?.runtime?.merge_status || "Awaiting Data"}
                                    </p>
                                </CardContent>
                            </Card>
                        </div>
                    </TabsContent>
                </Tabs>
            </div>
        </div>
    )
}

// =========================================================================
// METRIC CARD SUBCOMPONENT
// =========================================================================

function MetricCard({
    label,
    value,
    target,
    higher,
}: {
    label: string
    value: number | null
    target: number
    higher: boolean
}) {
    const hasData = value !== null && value !== undefined
    const pass = hasData && (higher ? value >= target : value <= target)

    return (
        <div className="bg-zinc-800/50 rounded-lg p-2.5">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</p>
            <p className={`text-lg font-bold mt-0.5 ${!hasData ? "text-zinc-600" : pass ? "text-emerald-400" : "text-amber-400"
                }`}>
                {hasData ? `${(value * 100).toFixed(1)}%` : "—"}
            </p>
            <p className="text-[10px] text-zinc-500">
                {hasData
                    ? `target: ${higher ? "≥" : "≤"} ${(target * 100).toFixed(1)}%`
                    : "Awaiting Data"}
            </p>
            {hasData && (
                <div className="mt-1.5">
                    <Progress
                        value={higher
                            ? Math.min((value / target) * 100, 100)
                            : (value <= target ? 100 : Math.max(0, (1 - value / (target * 2)) * 100))
                        }
                        className="h-1"
                    />
                </div>
            )}
        </div>
    )
}
