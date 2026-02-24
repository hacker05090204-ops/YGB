"use client"

import * as React from "react"

interface GPUStatus {
    gpu_available: boolean
    device_name: string | null
    utilization_percent: number | null
    memory_allocated_mb: number | null
    memory_total_mb: number | null
    temperature: number | null
    compute_capability: string | null
}

export function GpuMonitor({ className = "", refreshInterval = 5000 }) {
    const [status, setStatus] = React.useState<GPUStatus | null>(null)
    const [error, setError] = React.useState<string | null>(null)

    const fetchStatus = React.useCallback(async () => {
        try {
            const res = await fetch((process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000") + "/gpu/status")
            if (!res.ok) throw new Error("Backend unavailable")
            const data = await res.json()
            setStatus(data)
            setError(null)
        } catch {
            setError("Backend Offline")
            setStatus(null)
        }
    }, [])

    React.useEffect(() => {
        fetchStatus()
        const interval = setInterval(fetchStatus, refreshInterval)
        return () => clearInterval(interval)
    }, [fetchStatus, refreshInterval])

    if (error) {
        return (
            <div className={`p-6 rounded-2xl bg-card/50 border border-border/50 ${className}`}>
                <h3 className="text-sm font-semibold text-muted-foreground mb-2">GPU Status</h3>
                <p className="text-red-500 text-sm font-medium">{error}</p>
            </div>
        )
    }

    if (!status) {
        return (
            <div className={`p-6 rounded-2xl bg-card/50 border border-border/50 ${className}`}>
                <h3 className="text-sm font-semibold text-muted-foreground mb-2">GPU Status</h3>
                <p className="text-muted-foreground text-sm">Loading...</p>
            </div>
        )
    }

    const memPercent = status.memory_allocated_mb && status.memory_total_mb
        ? Math.round((status.memory_allocated_mb / status.memory_total_mb) * 100)
        : 0

    return (
        <div className={`p-6 rounded-2xl bg-card/50 border border-border/50 ${className}`}>
            <h3 className="text-sm font-semibold text-muted-foreground mb-4">GPU Status</h3>

            {!status.gpu_available ? (
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-yellow-500" />
                    <span className="text-sm text-muted-foreground">No GPU detected</span>
                </div>
            ) : (
                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <span className="text-sm font-medium">{status.device_name || "GPU"}</span>
                        <div className="flex items-center gap-1">
                            <div className="w-2 h-2 rounded-full bg-green-500" />
                            <span className="text-xs text-green-500">Active</span>
                        </div>
                    </div>

                    {/* Utilization */}
                    {status.utilization_percent !== null && (
                        <div>
                            <div className="flex justify-between text-xs text-muted-foreground mb-1">
                                <span>Utilization</span>
                                <span>{status.utilization_percent}%</span>
                            </div>
                            <div className="h-2 bg-muted rounded-full overflow-hidden">
                                <div
                                    className="h-full bg-blue-500 rounded-full transition-all duration-500"
                                    style={{ width: `${status.utilization_percent}%` }}
                                />
                            </div>
                        </div>
                    )}

                    {/* Memory */}
                    <div>
                        <div className="flex justify-between text-xs text-muted-foreground mb-1">
                            <span>Memory</span>
                            <span>{status.memory_allocated_mb?.toFixed(0) ?? "—"} / {status.memory_total_mb?.toFixed(0) ?? "—"} MB</span>
                        </div>
                        <div className="h-2 bg-muted rounded-full overflow-hidden">
                            <div
                                className="h-full bg-purple-500 rounded-full transition-all duration-500"
                                style={{ width: `${memPercent}%` }}
                            />
                        </div>
                    </div>

                    {/* Temperature */}
                    {status.temperature !== null && (
                        <div className="flex justify-between items-center">
                            <span className="text-xs text-muted-foreground">Temperature</span>
                            <span className={`text-sm font-mono ${status.temperature > 80 ? "text-red-500" : status.temperature > 65 ? "text-yellow-500" : "text-green-500"}`}>
                                {status.temperature}°C
                            </span>
                        </div>
                    )}

                    {status.compute_capability && (
                        <div className="flex justify-between items-center">
                            <span className="text-xs text-muted-foreground">Compute</span>
                            <span className="text-xs font-mono text-muted-foreground">SM {status.compute_capability}</span>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}
