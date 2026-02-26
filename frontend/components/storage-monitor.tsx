"use client"

import { useState, useEffect } from "react"
import { authFetch } from "@/lib/ygb-api"
import {
    HardDrive,
    Database,
    CheckCircle,
    AlertTriangle,
    XCircle,
    RefreshCw,
} from "lucide-react"
import {
    Card,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

interface DiskStats {
    total_bytes: number
    free_bytes: number
    used_bytes: number
    percent_used: number
    percent_free: number
    alert_level: string
    hdd_root: string
}

interface EntityBreakdown {
    entity_count: number
    total_bytes: number
    total_mb: number
    file_count: number
}

interface IndexHealth {
    meta_count: number
    log_count: number
    orphaned_logs: number
    healthy: boolean
}

function formatBytes(bytes: number): string {
    if (bytes === 0) return "0 B"
    const k = 1024
    const sizes = ["B", "KB", "MB", "GB", "TB"]
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i]
}

function alertColor(level: string): string {
    switch (level) {
        case "OK": return "text-emerald-400"
        case "WARNING": return "text-amber-400"
        case "CRITICAL": return "text-orange-500"
        case "EMERGENCY": return "text-red-500"
        default: return "text-zinc-400"
    }
}

function alertBadgeVariant(level: string): "default" | "secondary" | "destructive" | "outline" {
    switch (level) {
        case "OK": return "default"
        case "WARNING": return "secondary"
        case "CRITICAL": return "destructive"
        case "EMERGENCY": return "destructive"
        default: return "outline"
    }
}

export function StorageMonitor() {
    const [disk, setDisk] = useState<DiskStats | null>(null)
    const [breakdown, setBreakdown] = useState<Record<string, EntityBreakdown>>({})
    const [health, setHealth] = useState<Record<string, IndexHealth>>({})
    const [alerts, setAlerts] = useState<string[]>([])
    const [storageStats, setStorageStats] = useState<{
        total_writes: number
        total_reads: number
        total_entities: number
        total_bytes_written: number
    } | null>(null)
    const [loading, setLoading] = useState(true)
    const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

    const fetchData = async () => {
        setLoading(true)
        try {
            const [diskRes, statsRes] = await Promise.all([
                authFetch(`${API_BASE}/api/storage/disk`),
                authFetch(`${API_BASE}/api/storage/stats`),
            ])

            if (diskRes.ok) {
                const data = await diskRes.json()
                setDisk(data.status || null)
                setBreakdown(data.breakdown || {})
                setHealth(data.index_health || {})
                setAlerts(data.alerts || [])
            }

            if (statsRes.ok) {
                const data = await statsRes.json()
                setStorageStats({
                    total_writes: data.total_writes || 0,
                    total_reads: data.total_reads || 0,
                    total_entities: data.total_entities || 0,
                    total_bytes_written: data.total_bytes_written || 0,
                })
            }

            setLastRefresh(new Date())
        } catch (e) {
            console.error("Failed to fetch storage data:", e)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchData()
        const interval = setInterval(fetchData, 15000)
        return () => clearInterval(interval)
    }, [])

    const healthyCount = Object.values(health).filter(h => h.healthy).length
    const totalEntityTypes = Object.keys(health).length
    const unhealthyTypes = Object.entries(health)
        .filter(([, h]) => !h.healthy)
        .map(([name]) => name)

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <HardDrive className="h-5 w-5 text-blue-400" />
                    <h3 className="text-lg font-semibold">HDD Storage Engine</h3>
                    {disk && (
                        <Badge variant={alertBadgeVariant(disk.alert_level)}>
                            {disk.alert_level}
                        </Badge>
                    )}
                </div>
                <button
                    onClick={fetchData}
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    disabled={loading}
                >
                    <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
                    {lastRefresh ? `Updated ${lastRefresh.toLocaleTimeString()}` : "Loading..."}
                </button>
            </div>

            {/* Disk Usage Bar */}
            {disk && (
                <Card>
                    <CardHeader className="pb-3">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardDescription className="text-xs uppercase tracking-wider">
                                    {disk.hdd_root}
                                </CardDescription>
                                <CardTitle className="text-xl tabular-nums">
                                    {formatBytes(disk.free_bytes)} free
                                    <span className="text-muted-foreground text-sm ml-2">
                                        / {formatBytes(disk.total_bytes)}
                                    </span>
                                </CardTitle>
                            </div>
                            <div className={`text-2xl font-bold tabular-nums ${alertColor(disk.alert_level)}`}>
                                {disk.percent_used.toFixed(1)}%
                            </div>
                        </div>
                        <Progress
                            value={disk.percent_used}
                            className="h-2 mt-2"
                        />
                    </CardHeader>
                </Card>
            )}

            {/* Entity Breakdown Grid */}
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                {Object.entries(breakdown).map(([name, info]) => (
                    <Card key={name} className="@container/card">
                        <CardHeader className="p-3">
                            <div className="flex items-center justify-between">
                                <CardDescription className="text-[11px] uppercase tracking-wider truncate">
                                    {name}
                                </CardDescription>
                                {health[name] && (
                                    health[name].healthy ? (
                                        <CheckCircle className="h-3 w-3 text-emerald-400 shrink-0" />
                                    ) : (
                                        <AlertTriangle className="h-3 w-3 text-amber-400 shrink-0" />
                                    )
                                )}
                            </div>
                            <CardTitle className="text-lg tabular-nums">
                                {info.entity_count ?? 0}
                            </CardTitle>
                            <div className="text-[10px] text-muted-foreground tabular-nums">
                                {info.file_count ?? 0} files · {(info.total_mb ?? 0).toFixed(2)} MB
                            </div>
                        </CardHeader>
                    </Card>
                ))}
            </div>

            {/* Engine Stats + Health */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {/* I/O Stats */}
                <Card>
                    <CardHeader className="p-3">
                        <CardDescription className="text-xs uppercase tracking-wider">
                            Engine I/O
                        </CardDescription>
                        <div className="grid grid-cols-2 gap-2 mt-1">
                            <div>
                                <div className="text-xs text-muted-foreground">Writes</div>
                                <div className="text-lg font-semibold tabular-nums">
                                    {storageStats?.total_writes ?? 0}
                                </div>
                            </div>
                            <div>
                                <div className="text-xs text-muted-foreground">Reads</div>
                                <div className="text-lg font-semibold tabular-nums">
                                    {storageStats?.total_reads ?? 0}
                                </div>
                            </div>
                            <div>
                                <div className="text-xs text-muted-foreground">Entities</div>
                                <div className="text-lg font-semibold tabular-nums">
                                    {storageStats?.total_entities ?? 0}
                                </div>
                            </div>
                            <div>
                                <div className="text-xs text-muted-foreground">Written</div>
                                <div className="text-lg font-semibold tabular-nums">
                                    {formatBytes(storageStats?.total_bytes_written ?? 0)}
                                </div>
                            </div>
                        </div>
                    </CardHeader>
                </Card>

                {/* Index Health */}
                <Card>
                    <CardHeader className="p-3">
                        <CardDescription className="text-xs uppercase tracking-wider">
                            Index Health
                        </CardDescription>
                        <div className="flex items-center gap-2 mt-1">
                            {healthyCount === totalEntityTypes ? (
                                <CheckCircle className="h-5 w-5 text-emerald-400" />
                            ) : (
                                <XCircle className="h-5 w-5 text-amber-400" />
                            )}
                            <span className="text-lg font-semibold tabular-nums">
                                {healthyCount}/{totalEntityTypes}
                            </span>
                            <span className="text-sm text-muted-foreground">healthy</span>
                        </div>
                        {unhealthyTypes.length > 0 && (
                            <div className="text-xs text-amber-400 mt-1">
                                Issues: {unhealthyTypes.join(", ")}
                            </div>
                        )}
                    </CardHeader>
                </Card>
            </div>

            {/* Alerts */}
            {alerts.length > 0 && (
                <Card className="border-amber-500/30">
                    <CardHeader className="p-3">
                        <CardDescription className="text-xs uppercase tracking-wider text-amber-400">
                            Storage Alerts
                        </CardDescription>
                        <div className="space-y-1 mt-1">
                            {alerts.map((alert, i) => (
                                <div key={i} className="text-sm flex items-center gap-2">
                                    <AlertTriangle className="h-3 w-3 text-amber-400 shrink-0" />
                                    {alert}
                                </div>
                            ))}
                        </div>
                    </CardHeader>
                </Card>
            )}
        </div>
    )
}
