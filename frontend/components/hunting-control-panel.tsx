"use client"

import { useState, useEffect, useCallback } from "react"
import { authFetch } from "@/lib/ygb-api"
import { cn } from "@/lib/utils"
import {
    Target,
    Shield,
    Play,
    Square,
    Eye,
    Camera,
    Video,
    FileText,
    CheckCircle,
    XCircle,
    AlertTriangle,
    BarChart,
    Clock,
    Activity,
    Globe,
    DollarSign,
    Lock,
    Loader2,
    ChevronDown,
    ChevronUp,
} from "lucide-react"

const API_BASE = process.env.NEXT_PUBLIC_YGB_API_URL || "http://localhost:8000"

// =========================================================================
// TYPES
// =========================================================================

interface TargetSuggestion {
    domain: string
    program_name: string
    platform: string
    scope_size: number
    api_endpoint_count: number
    wildcard_count: number
    likelihood_percent: number
    difficulty: "LOW" | "MEDIUM" | "HIGH" | "EXPERT"
    bounty_range: { min_usd: number; max_usd: number }
    analysis: string
}

interface ReplayStep {
    sequence: number
    timestamp: number
    endpoint: string
    payload_preview: string
    http_pairs: number
    dom_diffs: number
    hash: string
}

interface EvidenceItem {
    type: "VIDEO" | "SCREENSHOT" | "HTTP_LOG" | "DOM_DIFF" | "REPLAY"
    path: string
    hash: string
    timestamp: number
    size_bytes: number
}

interface ReportPreview {
    title: string
    summary: string
    endpoint: string
    parameter: string
    reproduction_steps: string
    impact: string
    remediation: string
    evidence_count: number
    duplicate_score: number
    language: "ENGLISH" | "HINDI"
}

interface AutoModeState {
    enabled: boolean
    shadow_only: boolean
    integrity_score: number
    conditions_met: boolean
    blocked_reasons: string[]
}

interface HuntingControlPanelProps {
    className?: string
}

// =========================================================================
// DIFFICULTY STYLES
// =========================================================================

const DIFFICULTY_STYLES: Record<string, string> = {
    LOW: "text-emerald-400 bg-emerald-500/20",
    MEDIUM: "text-amber-400 bg-amber-500/20",
    HIGH: "text-orange-400 bg-orange-500/20",
    EXPERT: "text-red-400 bg-red-500/20",
}

// =========================================================================
// COMPONENT
// =========================================================================

export function HuntingControlPanel({ className }: HuntingControlPanelProps) {
    // --- State ---
    const [targets, setTargets] = useState<TargetSuggestion[]>([])
    const [replaySteps, setReplaySteps] = useState<ReplayStep[]>([])
    const [evidence, setEvidence] = useState<EvidenceItem[]>([])
    const [report, setReport] = useState<ReportPreview | null>(null)
    const [autoMode, setAutoMode] = useState<AutoModeState>({
        enabled: false,
        shadow_only: true,
        integrity_score: 0,
        conditions_met: false,
        blocked_reasons: [],
    })
    const [selectedTarget, setSelectedTarget] = useState<TargetSuggestion | null>(null)
    const [expandedSection, setExpandedSection] = useState<string | null>("targets")
    const [loading, setLoading] = useState(false)

    // --- Section Toggle ---
    const toggleSection = useCallback((section: string) => {
        setExpandedSection(prev => prev === section ? null : section)
    }, [])

    // --- Data Fetching (real endpoints, no mock) ---
    const fetchTargets = useCallback(async () => {
        setLoading(true)
        try {
            const res = await authFetch(`${API_BASE}/api/hunting/targets`)
            if (res.ok) {
                const data = await res.json()
                setTargets(data.targets || [])
            }
        } catch {
            // API not available yet — show empty state
        } finally {
            setLoading(false)
        }
    }, [])

    const fetchAutoModeState = useCallback(async () => {
        try {
            const res = await authFetch(`${API_BASE}/api/hunting/auto-mode`)
            if (res.ok) {
                const data = await res.json()
                setAutoMode(data)
            }
        } catch {
            // API not available yet
        }
    }, [])

    useEffect(() => {
        fetchAutoModeState()
    }, [fetchAutoModeState])

    // --- Target Approval ---
    const approveTarget = useCallback((target: TargetSuggestion) => {
        setSelectedTarget(target)
    }, [])

    const rejectTarget = useCallback((domain: string) => {
        setTargets(prev => prev.filter(t => t.domain !== domain))
    }, [])

    // =========================================================================
    // RENDER
    // =========================================================================

    return (
        <div className={cn("space-y-4", className)}>
            {/* Header */}
            <div className="flex items-center gap-3">
                <div className="p-2 rounded-lg bg-gradient-to-br from-purple-500/20 to-blue-500/20 border border-purple-500/30">
                    <Target className="w-5 h-5 text-purple-400" />
                </div>
                <div>
                    <h3 className="text-sm font-semibold text-[#FAFAFA]">Hunting Control</h3>
                    <p className="text-[10px] text-[#525252]">Governance-safe autonomous hunting</p>
                </div>
                {/* Auto-mode indicator */}
                <div className="ml-auto flex items-center gap-2">
                    <div className={cn(
                        "px-2 py-0.5 rounded-full text-[10px] font-medium",
                        autoMode.enabled
                            ? "bg-purple-500/20 text-purple-400 border border-purple-500/30"
                            : "bg-[#262626] text-[#525252] border border-[#333]"
                    )}>
                        {autoMode.enabled ? "AUTO (SHADOW)" : "MANUAL"}
                    </div>
                    <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-[#262626] text-[10px]">
                        <Shield className="w-3 h-3 text-emerald-400" />
                        <span className="text-emerald-300 font-medium">
                            {autoMode.integrity_score}%
                        </span>
                    </div>
                </div>
            </div>

            {/* Governance Banner */}
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
                <Lock className="w-3 h-3 text-amber-400 flex-shrink-0" />
                <span className="text-amber-400 text-[10px] font-medium">
                    No auto-submission. Manual approval required for all exports.
                </span>
            </div>

            {/* ============================================================ */}
            {/* TARGET SUGGESTIONS */}
            {/* ============================================================ */}
            <div className="rounded-xl border border-[#262626] overflow-hidden">
                <button
                    onClick={() => toggleSection("targets")}
                    className="w-full flex items-center gap-2 px-4 py-2.5 bg-[#171717] hover:bg-[#1a1a1a] transition-colors"
                >
                    <Target className="w-4 h-4 text-purple-400" />
                    <span className="text-xs font-semibold text-[#FAFAFA]">Target Suggestions</span>
                    <span className="ml-auto text-[10px] text-[#525252]">{targets.length} targets</span>
                    {expandedSection === "targets"
                        ? <ChevronUp className="w-3 h-3 text-[#525252]" />
                        : <ChevronDown className="w-3 h-3 text-[#525252]" />
                    }
                </button>
                {expandedSection === "targets" && (
                    <div className="p-3 space-y-2 bg-[#0a0a0a]">
                        {targets.length === 0 && (
                            <div className="text-center py-6">
                                <Target className="w-6 h-6 text-[#333] mx-auto mb-2" />
                                <p className="text-xs text-[#525252]">
                                    No targets yet. Use voice: &quot;Find good target&quot;
                                </p>
                                <button
                                    onClick={fetchTargets}
                                    className="mt-2 px-3 py-1 text-[10px] rounded-md bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 transition-colors"
                                >
                                    {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : "Discover Targets"}
                                </button>
                            </div>
                        )}
                        {targets.map((target, i) => (
                            <div key={i} className="p-3 rounded-lg bg-[#171717] border border-[#262626] space-y-2">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <Globe className="w-3 h-3 text-cyan-400" />
                                        <span className="text-xs text-[#FAFAFA] font-medium">{target.domain}</span>
                                    </div>
                                    <span className={cn("px-2 py-0.5 rounded text-[10px] font-medium", DIFFICULTY_STYLES[target.difficulty])}>
                                        {target.difficulty}
                                    </span>
                                </div>
                                <div className="grid grid-cols-3 gap-2 text-[10px]">
                                    <div>
                                        <span className="text-[#525252]">Likelihood</span>
                                        <p className="text-cyan-400 font-medium">{target.likelihood_percent}%</p>
                                    </div>
                                    <div>
                                        <span className="text-[#525252]">Bounty Range</span>
                                        <p className="text-emerald-400 font-medium">
                                            ${target.bounty_range.min_usd}-${target.bounty_range.max_usd}
                                        </p>
                                    </div>
                                    <div>
                                        <span className="text-[#525252]">Platform</span>
                                        <p className="text-[#A3A3A3] font-medium">{target.platform}</p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <button
                                        onClick={() => approveTarget(target)}
                                        className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-md bg-emerald-500/20 text-emerald-300 text-[10px] font-medium hover:bg-emerald-500/30 transition-colors"
                                    >
                                        <CheckCircle className="w-3 h-3" /> Accept
                                    </button>
                                    <button
                                        onClick={() => rejectTarget(target.domain)}
                                        className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-md bg-red-500/20 text-red-300 text-[10px] font-medium hover:bg-red-500/30 transition-colors"
                                    >
                                        <XCircle className="w-3 h-3" /> Reject
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* ============================================================ */}
            {/* LIVE REPLAY TIMELINE */}
            {/* ============================================================ */}
            <div className="rounded-xl border border-[#262626] overflow-hidden">
                <button
                    onClick={() => toggleSection("replay")}
                    className="w-full flex items-center gap-2 px-4 py-2.5 bg-[#171717] hover:bg-[#1a1a1a] transition-colors"
                >
                    <Play className="w-4 h-4 text-cyan-400" />
                    <span className="text-xs font-semibold text-[#FAFAFA]">Live Replay</span>
                    <span className="ml-auto text-[10px] text-[#525252]">{replaySteps.length} steps</span>
                    {expandedSection === "replay"
                        ? <ChevronUp className="w-3 h-3 text-[#525252]" />
                        : <ChevronDown className="w-3 h-3 text-[#525252]" />
                    }
                </button>
                {expandedSection === "replay" && (
                    <div className="p-3 space-y-1 bg-[#0a0a0a] max-h-48 overflow-y-auto">
                        {replaySteps.length === 0 && (
                            <p className="text-center text-[10px] text-[#525252] py-4">No replay steps recorded</p>
                        )}
                        {replaySteps.map((step, i) => (
                            <div key={i} className="flex items-center gap-2 px-2 py-1 rounded bg-[#171717] text-[10px]">
                                <span className="text-[#525252] w-4">#{step.sequence}</span>
                                <span className="text-cyan-400 flex-1 truncate">{step.endpoint}</span>
                                <span className="text-[#525252]">{step.http_pairs} req</span>
                                <span className="text-[#333] font-mono truncate w-16">{step.hash.slice(0, 8)}</span>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* ============================================================ */}
            {/* EVIDENCE GALLERY */}
            {/* ============================================================ */}
            <div className="rounded-xl border border-[#262626] overflow-hidden">
                <button
                    onClick={() => toggleSection("evidence")}
                    className="w-full flex items-center gap-2 px-4 py-2.5 bg-[#171717] hover:bg-[#1a1a1a] transition-colors"
                >
                    <Camera className="w-4 h-4 text-amber-400" />
                    <span className="text-xs font-semibold text-[#FAFAFA]">Evidence</span>
                    <span className="ml-auto text-[10px] text-[#525252]">{evidence.length} items</span>
                    {expandedSection === "evidence"
                        ? <ChevronUp className="w-3 h-3 text-[#525252]" />
                        : <ChevronDown className="w-3 h-3 text-[#525252]" />
                    }
                </button>
                {expandedSection === "evidence" && (
                    <div className="p-3 bg-[#0a0a0a]">
                        {evidence.length === 0 && (
                            <p className="text-center text-[10px] text-[#525252] py-4">No evidence captured yet</p>
                        )}
                        <div className="grid grid-cols-2 gap-2">
                            {evidence.map((item, i) => (
                                <div key={i} className="p-2 rounded-lg bg-[#171717] border border-[#262626]">
                                    <div className="flex items-center gap-1.5 mb-1">
                                        {item.type === "VIDEO"
                                            ? <Video className="w-3 h-3 text-purple-400" />
                                            : item.type === "SCREENSHOT"
                                                ? <Camera className="w-3 h-3 text-amber-400" />
                                                : <FileText className="w-3 h-3 text-cyan-400" />
                                        }
                                        <span className="text-[10px] text-[#A3A3A3]">{item.type}</span>
                                    </div>
                                    <p className="text-[10px] text-[#525252] font-mono truncate">{item.hash.slice(0, 16)}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {/* ============================================================ */}
            {/* REPORT PREVIEW */}
            {/* ============================================================ */}
            <div className="rounded-xl border border-[#262626] overflow-hidden">
                <button
                    onClick={() => toggleSection("report")}
                    className="w-full flex items-center gap-2 px-4 py-2.5 bg-[#171717] hover:bg-[#1a1a1a] transition-colors"
                >
                    <FileText className="w-4 h-4 text-emerald-400" />
                    <span className="text-xs font-semibold text-[#FAFAFA]">Report Preview</span>
                    {report && (
                        <span className="ml-auto flex items-center gap-1 text-[10px]">
                            <span className={cn(
                                "px-1.5 py-0.5 rounded",
                                report.duplicate_score > 80
                                    ? "bg-red-500/20 text-red-300"
                                    : report.duplicate_score > 50
                                        ? "bg-amber-500/20 text-amber-300"
                                        : "bg-emerald-500/20 text-emerald-300"
                            )}>
                                Dup: {report.duplicate_score}%
                            </span>
                        </span>
                    )}
                    {expandedSection === "report"
                        ? <ChevronUp className="w-3 h-3 text-[#525252]" />
                        : <ChevronDown className="w-3 h-3 text-[#525252]" />
                    }
                </button>
                {expandedSection === "report" && (
                    <div className="p-3 space-y-2 bg-[#0a0a0a]">
                        {!report && (
                            <p className="text-center text-[10px] text-[#525252] py-4">
                                No report generated. Use voice: &quot;Generate report&quot;
                            </p>
                        )}
                        {report && (
                            <>
                                <div className="space-y-1">
                                    <label className="text-[10px] text-[#525252] uppercase tracking-wider">Title</label>
                                    <p className="text-xs text-[#FAFAFA] font-medium">{report.title}</p>
                                </div>
                                <div className="space-y-1">
                                    <label className="text-[10px] text-[#525252] uppercase tracking-wider">Summary</label>
                                    <p className="text-[11px] text-[#A3A3A3] leading-relaxed">{report.summary}</p>
                                </div>
                                <div className="grid grid-cols-2 gap-2 text-[10px]">
                                    <div>
                                        <span className="text-[#525252]">Endpoint</span>
                                        <p className="text-cyan-400 font-mono">{report.endpoint}</p>
                                    </div>
                                    <div>
                                        <span className="text-[#525252]">Parameter</span>
                                        <p className="text-amber-400 font-mono">{report.parameter}</p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2 text-[10px]">
                                    <span className="text-[#525252]">{report.evidence_count} evidence files</span>
                                    <span className="text-[#525252]">{report.language}</span>
                                </div>
                                {/* Duplicate warning */}
                                {report.duplicate_score > 80 && (
                                    <div className="flex items-center gap-2 px-2 py-1 rounded bg-red-500/10 border border-red-500/20">
                                        <AlertTriangle className="w-3 h-3 text-red-400" />
                                        <span className="text-[10px] text-red-300">
                                            High similarity ({report.duplicate_score}%) — export blocked
                                        </span>
                                    </div>
                                )}
                            </>
                        )}
                    </div>
                )}
            </div>

            {/* ============================================================ */}
            {/* AUTO MODE TOGGLE */}
            {/* ============================================================ */}
            <div className="rounded-xl p-3 border border-[#262626] bg-[#171717] space-y-2">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Activity className="w-4 h-4 text-purple-400" />
                        <span className="text-xs font-semibold text-[#FAFAFA]">Auto Mode</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300">
                            SHADOW ONLY
                        </span>
                    </div>
                    <button
                        className={cn(
                            "w-8 h-4 rounded-full transition-colors relative",
                            autoMode.conditions_met && autoMode.enabled
                                ? "bg-purple-500"
                                : "bg-[#333]"
                        )}
                        disabled={!autoMode.conditions_met}
                        onClick={() => setAutoMode(prev => ({ ...prev, enabled: !prev.enabled }))}
                    >
                        <div className={cn(
                            "w-3 h-3 rounded-full bg-white absolute top-0.5 transition-transform",
                            autoMode.enabled ? "translate-x-4" : "translate-x-0.5"
                        )} />
                    </button>
                </div>
                {autoMode.blocked_reasons.length > 0 && (
                    <div className="space-y-1">
                        {autoMode.blocked_reasons.map((reason, i) => (
                            <div key={i} className="flex items-center gap-1 text-[10px] text-red-400">
                                <XCircle className="w-3 h-3 flex-shrink-0" />
                                <span>{reason}</span>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Selected Target Info */}
            {selectedTarget && (
                <div className="rounded-xl p-3 border border-emerald-500/20 bg-emerald-500/5 space-y-2">
                    <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-emerald-400">Active Target</span>
                        <button
                            onClick={() => setSelectedTarget(null)}
                            className="text-[10px] text-red-400 hover:text-red-300"
                        >
                            Stop
                        </button>
                    </div>
                    <p className="text-xs text-[#FAFAFA]">{selectedTarget.domain}</p>
                    <div className="flex items-center gap-3 text-[10px] text-[#525252]">
                        <span>{selectedTarget.program_name}</span>
                        <span>{selectedTarget.platform}</span>
                        <span className="text-emerald-400">
                            ${selectedTarget.bounty_range.min_usd}-${selectedTarget.bounty_range.max_usd}
                        </span>
                    </div>
                </div>
            )}
        </div>
    )
}
