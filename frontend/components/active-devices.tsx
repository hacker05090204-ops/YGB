"use client"

import * as React from "react"
import { authFetch } from "@/lib/ygb-api"

interface Device {
    id: string
    user_name?: string
    device_hash: string
    ip_address: string | null
    user_agent: string | null
    last_seen: string
    is_trusted: number
    active_sessions: number
}

export function ActiveDevices({ className = "", refreshInterval = 5000 }) {
    const [devices, setDevices] = React.useState<Device[]>([])
    const [error, setError] = React.useState<string | null>(null)
    const [loading, setLoading] = React.useState(true)

    const fetchDevices = React.useCallback(async () => {
        try {
            const res = await authFetch((process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000") + "/admin/active-devices")
            if (!res.ok) throw new Error("Backend unavailable")
            const data = await res.json()
            setDevices(data.devices || [])
            setError(null)
        } catch {
            setError("Backend Offline")
            setDevices([])
        } finally {
            setLoading(false)
        }
    }, [])

    React.useEffect(() => {
        fetchDevices()
        const interval = setInterval(fetchDevices, refreshInterval)
        return () => clearInterval(interval)
    }, [fetchDevices, refreshInterval])

    if (error) {
        return (
            <div className={`p-6 rounded-2xl bg-card/50 border border-border/50 ${className}`}>
                <h3 className="text-sm font-semibold text-muted-foreground mb-2">Active Devices</h3>
                <p className="text-red-500 text-sm font-medium">{error}</p>
            </div>
        )
    }

    return (
        <div className={`p-6 rounded-2xl bg-card/50 border border-border/50 ${className}`}>
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-muted-foreground">Active Devices</h3>
                <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                    {devices.length}
                </span>
            </div>

            {loading ? (
                <p className="text-muted-foreground text-sm">Loading...</p>
            ) : devices.length === 0 ? (
                <p className="text-muted-foreground text-sm">No active devices</p>
            ) : (
                <div className="space-y-3 max-h-[300px] overflow-y-auto">
                    {devices.map((device) => (
                        <div key={device.id} className="flex items-start gap-3 p-3 rounded-lg bg-muted/30 border border-border/30">
                            <div className={`w-2 h-2 rounded-full mt-1.5 ${device.active_sessions > 0 ? "bg-green-500" : "bg-gray-400"}`} />
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                    <span className="text-sm font-medium truncate">
                                        {device.user_name || "Unknown User"}
                                    </span>
                                    {device.is_trusted ? (
                                        <span className="text-[10px] text-green-500 bg-green-500/10 px-1.5 py-0.5 rounded">Trusted</span>
                                    ) : null}
                                </div>
                                <div className="text-xs text-muted-foreground truncate mt-0.5">
                                    {device.ip_address || "—"} · {device.device_hash?.slice(0, 8)}...
                                </div>
                                <div className="text-xs text-muted-foreground mt-0.5">
                                    Last seen: {device.last_seen ? new Date(device.last_seen).toLocaleString() : "—"}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}
