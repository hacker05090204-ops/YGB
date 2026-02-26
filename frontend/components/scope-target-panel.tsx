"use client"

import { useState, useEffect, useCallback } from "react"
import { authFetch } from "@/lib/ygb-api"
import { cn } from "@/lib/utils"
import {
    Target,
    Shield,
    Play,
    Square,
    AlertTriangle,
    CheckCircle,
    XCircle,
    Loader2,
    Globe,
    Clock,
    Activity
} from "lucide-react"

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

interface ScopeViolation {
    rule: string
    message: string
}

interface TargetSession {
    session_id: string
    target_url: string
    scope_definition: Record<string, unknown>
    mode: string
    status: string
    started_at: string
    stopped_at: string | null
    violations: ScopeViolation[]
    findings_count: number
}

interface ScopeTargetPanelProps {
    className?: string
}

export function ScopeTargetPanel({ className }: ScopeTargetPanelProps) {
    const [targetUrl, setTargetUrl] = useState("")
    const [scopeJson, setScopeJson] = useState("")
    const [isValidating, setIsValidating] = useState(false)
    const [isStarting, setIsStarting] = useState(false)
    const [isStopping, setIsStopping] = useState(false)

    const [validationResult, setValidationResult] = useState<{
        valid: boolean
        violations: ScopeViolation[]
    } | null>(null)

    const [activeSessions, setActiveSessions] = useState<TargetSession[]>([])
    const [stoppedSessions, setStoppedSessions] = useState<TargetSession[]>([])
    const [recentViolations, setRecentViolations] = useState<ScopeViolation[]>([])

    // Poll target status every 2s
    const fetchStatus = useCallback(async () => {
        try {
            const res = await authFetch(`${API_BASE}/target/status`)
            if (res.ok) {
                const data = await res.json()
                setActiveSessions(data.active_sessions || [])
                setStoppedSessions(data.stopped_sessions || [])
                setRecentViolations(data.violations || [])
            }
        } catch (error) {
            console.error("Failed to fetch target status:", error)
        }
    }, [])

    useEffect(() => {
        fetchStatus()
        const interval = setInterval(fetchStatus, 2000)
        return () => clearInterval(interval)
    }, [fetchStatus])

    // Validate scope
    const handleValidateScope = async () => {
        if (!targetUrl.trim()) return
        setIsValidating(true)
        setValidationResult(null)

        try {
            let scopeDef = {}
            if (scopeJson.trim()) {
                try {
                    scopeDef = JSON.parse(scopeJson)
                } catch {
                    setValidationResult({
                        valid: false,
                        violations: [{ rule: "INVALID_JSON", message: "Scope definition is not valid JSON" }]
                    })
                    setIsValidating(false)
                    return
                }
            }

            const res = await authFetch(`${API_BASE}/scope/validate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ target_url: targetUrl, scope_definition: scopeDef })
            })

            if (res.ok) {
                const data = await res.json()
                setValidationResult({ valid: data.valid, violations: data.violations || [] })
            } else {
                setValidationResult({
                    valid: false,
                    violations: [{ rule: "API_ERROR", message: "Scope validation API returned an error" }]
                })
            }
        } catch (error) {
            console.error("Scope validation failed:", error)
            setValidationResult({
                valid: false,
                violations: [{ rule: "NETWORK_ERROR", message: "Could not reach the backend" }]
            })
        } finally {
            setIsValidating(false)
        }
    }

    // Start target session
    const handleStartSession = async () => {
        if (!targetUrl.trim() || !validationResult?.valid) return
        setIsStarting(true)

        try {
            let scopeDef = {}
            if (scopeJson.trim()) {
                try { scopeDef = JSON.parse(scopeJson) } catch { /* ignore */ }
            }

            const res = await authFetch(`${API_BASE}/target/start`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    target_url: targetUrl,
                    scope_definition: scopeDef,
                    mode: "READ_ONLY"
                })
            })

            if (res.ok) {
                await fetchStatus()
                setTargetUrl("")
                setScopeJson("")
                setValidationResult(null)
            }
        } catch (error) {
            console.error("Failed to start session:", error)
        } finally {
            setIsStarting(false)
        }
    }

    // Stop target session
    const handleStopSession = async (sessionId: string) => {
        setIsStopping(true)
        try {
            await authFetch(`${API_BASE}/target/stop`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ session_id: sessionId })
            })
            await fetchStatus()
        } catch (error) {
            console.error("Failed to stop session:", error)
        } finally {
            setIsStopping(false)
        }
    }

    return (
        <div className={cn("space-y-6", className)}>
            {/* Header */}
            <div className="flex items-center gap-2">
                <Target className="w-5 h-5 text-cyan-400" />
                <h3 className="text-sm font-semibold text-[#A3A3A3] uppercase tracking-wider">
                    Scope & Target Management
                </h3>
            </div>

            {/* Target URL Input */}
            <div className="space-y-3">
                <div>
                    <label className="text-xs text-[#525252] block mb-1">Target URL</label>
                    <div className="flex gap-2">
                        <div className="relative flex-1">
                            <Globe className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#525252]" />
                            <input
                                type="text"
                                value={targetUrl}
                                onChange={(e) => {
                                    setTargetUrl(e.target.value)
                                    setValidationResult(null)
                                }}
                                placeholder="e.g. *.example.com"
                                className="w-full pl-9 pr-4 py-2.5 rounded-xl bg-[#0A0A0A] border border-[#262626] text-[#FAFAFA] text-sm placeholder:text-[#404040] focus:outline-none focus:border-cyan-500/50 transition-colors"
                            />
                        </div>
                        <button
                            onClick={handleValidateScope}
                            disabled={!targetUrl.trim() || isValidating}
                            className="px-4 py-2.5 rounded-xl bg-cyan-500/20 border border-cyan-500/30 text-cyan-400 text-sm font-medium hover:bg-cyan-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                            {isValidating ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                                <Shield className="w-4 h-4" />
                            )}
                            Validate
                        </button>
                    </div>
                </div>

                {/* Scope Definition JSON */}
                <div>
                    <label className="text-xs text-[#525252] block mb-1">
                        Scope Definition (JSON, optional)
                    </label>
                    <textarea
                        value={scopeJson}
                        onChange={(e) => setScopeJson(e.target.value)}
                        placeholder='{"include": ["*.example.com"], "exclude": ["admin.example.com"]}'
                        rows={2}
                        className="w-full px-4 py-2.5 rounded-xl bg-[#0A0A0A] border border-[#262626] text-[#FAFAFA] text-sm placeholder:text-[#404040] focus:outline-none focus:border-cyan-500/50 transition-colors resize-none font-mono text-xs"
                    />
                </div>

                {/* Validation Result */}
                {validationResult && (
                    <div className={cn(
                        "p-3 rounded-xl border",
                        validationResult.valid
                            ? "bg-green-500/10 border-green-500/20"
                            : "bg-red-500/10 border-red-500/20"
                    )}>
                        <div className="flex items-center gap-2 mb-1">
                            {validationResult.valid ? (
                                <>
                                    <CheckCircle className="w-4 h-4 text-green-400" />
                                    <span className="text-sm font-medium text-green-400">Scope Valid</span>
                                </>
                            ) : (
                                <>
                                    <XCircle className="w-4 h-4 text-red-400" />
                                    <span className="text-sm font-medium text-red-400">Scope Invalid</span>
                                </>
                            )}
                        </div>
                        {validationResult.violations.length > 0 && (
                            <ul className="space-y-1 mt-2">
                                {validationResult.violations.map((v, i) => (
                                    <li key={i} className="text-xs text-red-400/80 flex items-start gap-1.5">
                                        <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                                        <span><strong>{v.rule}</strong>: {v.message}</span>
                                    </li>
                                ))}
                            </ul>
                        )}
                    </div>
                )}

                {/* Start Button */}
                {validationResult?.valid && (
                    <button
                        onClick={handleStartSession}
                        disabled={isStarting}
                        className="w-full px-4 py-3 rounded-xl bg-green-500/20 border border-green-500/30 text-green-400 font-medium hover:bg-green-500/30 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                    >
                        {isStarting ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                            <Play className="w-4 h-4" />
                        )}
                        Start Target Session
                    </button>
                )}
            </div>

            {/* Active Sessions */}
            {activeSessions.length > 0 && (
                <div className="space-y-2">
                    <h4 className="text-xs font-semibold text-[#A3A3A3] uppercase tracking-wider flex items-center gap-1.5">
                        <Activity className="w-3.5 h-3.5 text-green-400" />
                        Active Sessions ({activeSessions.length})
                    </h4>
                    {activeSessions.map((session) => (
                        <div
                            key={session.session_id}
                            className="p-3 rounded-xl bg-green-500/5 border border-green-500/10"
                        >
                            <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                    <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                                    <span className="text-sm font-medium text-[#FAFAFA] truncate max-w-[200px]">
                                        {session.target_url}
                                    </span>
                                </div>
                                <button
                                    onClick={() => handleStopSession(session.session_id)}
                                    disabled={isStopping}
                                    className="px-2.5 py-1 rounded-lg bg-red-500/20 border border-red-500/30 text-red-400 text-xs hover:bg-red-500/30 transition-colors disabled:opacity-50 flex items-center gap-1"
                                >
                                    {isStopping ? (
                                        <Loader2 className="w-3 h-3 animate-spin" />
                                    ) : (
                                        <Square className="w-3 h-3" />
                                    )}
                                    Stop
                                </button>
                            </div>
                            <div className="flex items-center gap-3 text-xs text-[#525252]">
                                <span className="px-1.5 py-0.5 rounded bg-[#171717] border border-white/[0.04]">
                                    {session.mode}
                                </span>
                                <span className="flex items-center gap-1">
                                    <Clock className="w-3 h-3" />
                                    {new Date(session.started_at).toLocaleTimeString()}
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Recent Violations */}
            {recentViolations.length > 0 && (
                <div className="space-y-2">
                    <h4 className="text-xs font-semibold text-red-400 uppercase tracking-wider flex items-center gap-1.5">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        Scope Violations ({recentViolations.length})
                    </h4>
                    {recentViolations.slice(0, 5).map((v, i) => (
                        <div
                            key={i}
                            className="p-2 rounded-lg bg-red-500/5 border border-red-500/10 text-xs text-red-400/80"
                        >
                            <strong>{v.rule}</strong>: {v.message}
                        </div>
                    ))}
                </div>
            )}

            {/* Stopped Sessions (Audit Log) */}
            {stoppedSessions.length > 0 && (
                <div className="space-y-2">
                    <h4 className="text-xs font-semibold text-[#525252] uppercase tracking-wider">
                        Recent Sessions
                    </h4>
                    {stoppedSessions.slice(0, 5).map((session) => (
                        <div
                            key={session.session_id}
                            className="flex items-center justify-between p-2 rounded-lg bg-[#0A0A0A] border border-white/[0.04] text-xs"
                        >
                            <span className="text-[#737373] truncate max-w-[180px]">{session.target_url}</span>
                            <div className="flex items-center gap-2">
                                <span className="text-[#404040]">
                                    {session.stopped_at ? new Date(session.stopped_at).toLocaleTimeString() : "—"}
                                </span>
                                <span className="px-1.5 py-0.5 rounded bg-[#171717] text-[#525252]">
                                    {session.status}
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}
