"use client"

import * as React from "react"

interface Session {
    id: string
    user_name?: string
    mode: string | null
    status: string
    ip_address: string | null
    started_at: string
    ended_at: string | null
}

export function SessionHistory({ className = "", refreshInterval = 5000 }) {
    const [sessions, setSessions] = React.useState<Session[]>([])
    const [error, setError] = React.useState<string | null>(null)
    const [loading, setLoading] = React.useState(true)

    const fetchSessions = React.useCallback(async () => {
        try {
            const res = await fetch((process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000") + "/admin/active-sessions")
            if (!res.ok) throw new Error("Backend unavailable")
            const data = await res.json()
            setSessions(data.sessions || [])
            setError(null)
        } catch {
            setError("Backend Offline")
            setSessions([])
        } finally {
            setLoading(false)
        }
    }, [])

    React.useEffect(() => {
        fetchSessions()
        const interval = setInterval(fetchSessions, refreshInterval)
        return () => clearInterval(interval)
    }, [fetchSessions, refreshInterval])

    if (error) {
        return (
            <div className={`p-6 rounded-2xl bg-card/50 border border-border/50 ${className}`}>
                <h3 className="text-sm font-semibold text-muted-foreground mb-2">Active Sessions</h3>
                <p className="text-red-500 text-sm font-medium">{error}</p>
            </div>
        )
    }

    return (
        <div className={`p-6 rounded-2xl bg-card/50 border border-border/50 ${className}`}>
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-muted-foreground">Active Sessions</h3>
                <span className="text-xs text-muted-foreground bg-muted px-2 py-0.5 rounded-full">
                    {sessions.length}
                </span>
            </div>

            {loading ? (
                <p className="text-muted-foreground text-sm">Loading...</p>
            ) : sessions.length === 0 ? (
                <p className="text-muted-foreground text-sm">No active sessions</p>
            ) : (
                <div className="space-y-2 max-h-[300px] overflow-y-auto">
                    {sessions.map((session) => (
                        <div key={session.id} className="flex items-center justify-between p-3 rounded-lg bg-muted/30 border border-border/30">
                            <div className="flex items-center gap-3">
                                <div className={`w-2 h-2 rounded-full ${session.status === "active" ? "bg-green-500" : "bg-gray-400"}`} />
                                <div>
                                    <div className="text-sm font-medium">{session.user_name || "Unknown"}</div>
                                    <div className="text-xs text-muted-foreground">
                                        {session.mode || "—"} · {session.ip_address || "—"}
                                    </div>
                                </div>
                            </div>
                            <div className="text-right">
                                <span className={`text-xs px-2 py-0.5 rounded ${session.status === "active" ? "bg-green-500/10 text-green-500" : "bg-gray-500/10 text-gray-400"}`}>
                                    {session.status}
                                </span>
                                <div className="text-[10px] text-muted-foreground mt-1">
                                    {session.started_at ? new Date(session.started_at).toLocaleTimeString() : "—"}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}
