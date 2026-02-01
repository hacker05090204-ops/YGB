"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { Check, X, Square, Loader2, Clock, AlertTriangle } from "lucide-react"

// Types from G13 Dashboard Router
export type ApprovalStatusType = "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED" | "CANCELLED"
export type RiskLevelType = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
export type ProposedModeType = "MANUAL" | "AUTONOMOUS_FIND" | "READ_ONLY"

export interface ApprovalRequest {
    request_id: string
    target: string
    scope: string
    proposed_mode: ProposedModeType
    risk_level: RiskLevelType
    risk_summary: string
    status: ApprovalStatusType
    created_at: string
    expires_at: string
}

interface ApprovalPanelProps {
    pendingRequest?: ApprovalRequest | null
    onApprove: (requestId: string, reason?: string) => void
    onReject: (requestId: string, reason?: string) => void
    onStop: () => void
    isLoading?: boolean
    className?: string
}

const RISK_COLORS: Record<RiskLevelType, string> = {
    LOW: "text-emerald-400 bg-emerald-500/20",
    MEDIUM: "text-amber-400 bg-amber-500/20",
    HIGH: "text-orange-400 bg-orange-500/20",
    CRITICAL: "text-red-400 bg-red-500/20"
}

export function ApprovalPanel({
    pendingRequest,
    onApprove,
    onReject,
    onStop,
    isLoading = false,
    className
}: ApprovalPanelProps) {
    const [rejectReason, setRejectReason] = useState("")
    const [showRejectInput, setShowRejectInput] = useState(false)

    const handleApprove = () => {
        if (pendingRequest) {
            onApprove(pendingRequest.request_id)
        }
    }

    const handleReject = () => {
        if (pendingRequest) {
            onReject(pendingRequest.request_id, rejectReason)
            setShowRejectInput(false)
            setRejectReason("")
        }
    }

    return (
        <div className={cn("space-y-4", className)}>
            {/* Header */}
            <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-[#A3A3A3] uppercase tracking-wider">
                    Human Approval
                </h3>
                {pendingRequest && (
                    <span className="flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/20 text-amber-400 text-xs font-medium animate-pulse">
                        <Clock className="w-3 h-3" />
                        Pending
                    </span>
                )}
            </div>

            {/* Pending Request Card */}
            {pendingRequest ? (
                <div className="p-5 rounded-2xl bg-[#0A0A0A] border border-amber-500/30 space-y-4">
                    {/* Target & Scope */}
                    <div className="space-y-2">
                        <div className="flex items-center justify-between">
                            <span className="text-xs text-[#525252] uppercase tracking-wider">Target</span>
                            <span className={cn(
                                "px-2 py-0.5 rounded-full text-xs font-medium",
                                RISK_COLORS[pendingRequest.risk_level]
                            )}>
                                {pendingRequest.risk_level} Risk
                            </span>
                        </div>
                        <p className="text-[#FAFAFA] font-mono text-sm truncate">{pendingRequest.target}</p>
                    </div>

                    <div className="space-y-1">
                        <span className="text-xs text-[#525252] uppercase tracking-wider">Scope</span>
                        <p className="text-[#A3A3A3] text-sm">{pendingRequest.scope}</p>
                    </div>

                    <div className="space-y-1">
                        <span className="text-xs text-[#525252] uppercase tracking-wider">Proposed Mode</span>
                        <p className="text-[#A3A3A3] text-sm">{pendingRequest.proposed_mode}</p>
                    </div>

                    {/* Risk Summary */}
                    <div className="p-3 rounded-xl bg-[#171717] border border-[#262626]">
                        <div className="flex items-start gap-2">
                            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                            <p className="text-xs text-[#737373]">{pendingRequest.risk_summary}</p>
                        </div>
                    </div>

                    {/* Reject Reason Input */}
                    {showRejectInput && (
                        <div className="space-y-2">
                            <input
                                type="text"
                                placeholder="Rejection reason (optional)"
                                value={rejectReason}
                                onChange={(e) => setRejectReason(e.target.value)}
                                className="w-full px-4 py-2 rounded-lg bg-[#171717] border border-[#262626] text-[#FAFAFA] text-sm placeholder:text-[#404040] focus:outline-none focus:border-red-500/50"
                            />
                        </div>
                    )}
                </div>
            ) : (
                <div className="p-8 rounded-2xl bg-[#0A0A0A] border border-[#262626] flex flex-col items-center justify-center">
                    <div className="w-12 h-12 rounded-xl bg-[#171717] flex items-center justify-center mb-4">
                        <Check className="w-6 h-6 text-[#404040]" />
                    </div>
                    <p className="text-[#525252] text-sm">No pending approval requests</p>
                </div>
            )}

            {/* Action Buttons */}
            <div className="grid grid-cols-3 gap-3">
                {/* Approve Button */}
                <button
                    onClick={handleApprove}
                    disabled={!pendingRequest || isLoading}
                    className={cn(
                        "flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-medium transition-all duration-200",
                        pendingRequest && !isLoading
                            ? "bg-emerald-500 text-white hover:bg-emerald-600 shadow-[0_0_20px_rgba(16,185,129,0.3)]"
                            : "bg-[#171717] text-[#404040] cursor-not-allowed"
                    )}
                >
                    {isLoading ? (
                        <Loader2 className="w-5 h-5 animate-spin" />
                    ) : (
                        <Check className="w-5 h-5" />
                    )}
                    Approve
                </button>

                {/* Reject Button */}
                <button
                    onClick={() => showRejectInput ? handleReject() : setShowRejectInput(true)}
                    disabled={!pendingRequest || isLoading}
                    className={cn(
                        "flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-medium transition-all duration-200",
                        pendingRequest && !isLoading
                            ? "bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30"
                            : "bg-[#171717] text-[#404040] cursor-not-allowed"
                    )}
                >
                    <X className="w-5 h-5" />
                    Reject
                </button>

                {/* Stop Button */}
                <button
                    onClick={onStop}
                    disabled={isLoading}
                    className={cn(
                        "flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-medium transition-all duration-200",
                        "bg-[#262626] text-[#A3A3A3] hover:bg-[#404040] hover:text-[#FAFAFA]",
                        isLoading && "opacity-50 cursor-not-allowed"
                    )}
                >
                    <Square className="w-5 h-5" />
                    Stop
                </button>
            </div>

            {/* Safety Note */}
            <p className="text-xs text-[#404040] text-center">
                These buttons only send intent to backend router — no direct execution
            </p>
        </div>
    )
}
