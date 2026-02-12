"use client"

import * as React from "react"

interface ActivityEvent {
    id: string
    user_id: string | null
    action_type: string
    description: string
    ip_address: string | null
    created_at: string
}

const ACTION_ICONS: Record<string, string> = {
    LOGIN_SUCCESS: "🔐",
    LOGIN_FAILED: "❌",
    USER_REGISTERED: "👤",
    RATE_LIMIT_EXCEEDED: "🛑",
    LOGOUT: "👋",
    SESSION_STARTED: "▶️",
    BOUNTY_SUBMITTED: "🎯",
    TARGET_CREATED: "🔍",
}

export function LoginAlerts({ className = "", refreshInterval = 5000 }) {
    const [events, setEvents] = React.useState<ActivityEvent[]>([])
    const [error, setError] = React.useState<string | null>(null)
    const [loading, setLoading] = React.useState(true)

    const fetchEvents = React.useCallback(async () => {
        try {
            const res = await fetch("http://localhost:8000/api/db/activity?limit=20")
            if (!res.ok) throw new Error("Backend unavailable")
            const data = await res.json()
            // Filter to login-related events
            const loginEvents = (data.activities || []).filter((a: ActivityEvent) =>
                ["LOGIN_SUCCESS", "LOGIN_FAILED", "USER_REGISTERED", "RATE_LIMIT_EXCEEDED", "LOGOUT"].includes(a.action_type)
            )
            setEvents(loginEvents)
            setError(null)
        } catch {
            setError("Backend Offline")
            setEvents([])
        } finally {
            setLoading(false)
        }
    }, [])

    React.useEffect(() => {
        fetchEvents()
        const interval = setInterval(fetchEvents, refreshInterval)
        return () => clearInterval(interval)
    }, [fetchEvents, refreshInterval])

    if (error) {
        return (
            <div className={`p-6 rounded-2xl bg-card/50 border border-border/50 ${className}`}>
                <h3 className="text-sm font-semibold text-muted-foreground mb-2">Login Alerts</h3>
                <p className="text-red-500 text-sm font-medium">{error}</p>
            </div>
        )
    }

    return (
        <div className={`p-6 rounded-2xl bg-card/50 border border-border/50 ${className}`}>
            <h3 className="text-sm font-semibold text-muted-foreground mb-4">Login Activity</h3>

            {loading ? (
                <p className="text-muted-foreground text-sm">Loading...</p>
            ) : events.length === 0 ? (
                <p className="text-muted-foreground text-sm">No login activity</p>
            ) : (
                <div className="space-y-2 max-h-[300px] overflow-y-auto">
                    {events.map((event) => (
                        <div key={event.id} className="flex items-start gap-3 p-2 rounded-lg hover:bg-muted/30 transition-colors">
                            <span className="text-base mt-0.5">
                                {ACTION_ICONS[event.action_type] || "📋"}
                            </span>
                            <div className="flex-1 min-w-0">
                                <div className="text-sm">
                                    <span className={`font-medium ${event.action_type === "LOGIN_FAILED" || event.action_type === "RATE_LIMIT_EXCEEDED" ? "text-red-400" : ""}`}>
                                        {event.action_type.replace(/_/g, " ")}
                                    </span>
                                </div>
                                <div className="text-xs text-muted-foreground truncate">
                                    {event.description}
                                </div>
                                <div className="text-[10px] text-muted-foreground">
                                    {event.ip_address || "—"} · {event.created_at ? new Date(event.created_at).toLocaleString() : "—"}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}
