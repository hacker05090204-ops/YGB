"use client"

import { cn } from "@/lib/utils"
import {
    Target,
    Globe,
    DollarSign,
    BarChart,
    Plus,
    ExternalLink,
    Check
} from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"

// Types from G14 Target Discovery
export type DiscoverySourceType = "HACKERONE_PUBLIC" | "BUGCROWD_PUBLIC" | "SECURITY_TXT" | "PUBLIC_DISCLOSURE"
export type PayoutTierType = "HIGH" | "MEDIUM" | "LOW" | "UNKNOWN"
export type ReportDensityType = "LOW" | "MEDIUM" | "HIGH"

export interface TargetCandidate {
    candidate_id: string
    program_name: string
    source: DiscoverySourceType
    scope_summary: string
    payout_tier: PayoutTierType
    report_density: ReportDensityType
    is_public: boolean
    requires_invite: boolean
    discovered_at: string
}

interface TargetDiscoveryPanelProps {
    targets: TargetCandidate[]
    selectedTargets: Set<string>
    onSelectTarget: (id: string) => void
    onDiscoverTargets: () => void
    isDiscovering?: boolean
    className?: string
}

const SOURCE_LABELS: Record<DiscoverySourceType, string> = {
    HACKERONE_PUBLIC: "HackerOne",
    BUGCROWD_PUBLIC: "Bugcrowd",
    SECURITY_TXT: "security.txt",
    PUBLIC_DISCLOSURE: "Disclosure"
}

const PAYOUT_COLORS: Record<PayoutTierType, string> = {
    HIGH: "text-emerald-400 bg-emerald-500/20",
    MEDIUM: "text-amber-400 bg-amber-500/20",
    LOW: "text-[#737373] bg-[#262626]",
    UNKNOWN: "text-[#525252] bg-[#171717]"
}

const DENSITY_LABELS: Record<ReportDensityType, string> = {
    LOW: "<10%",
    MEDIUM: "10-30%",
    HIGH: ">30%"
}

export function TargetDiscoveryPanel({
    targets,
    selectedTargets,
    onSelectTarget,
    onDiscoverTargets,
    isDiscovering = false,
    className
}: TargetDiscoveryPanelProps) {
    return (
        <div className={cn(
            "flex flex-col h-full rounded-2xl bg-[#0A0A0A] border border-white/[0.06] overflow-hidden",
            className
        )}>
            {/* Header */}
            <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-[#262626] flex items-center justify-center">
                        <Target className="w-4 h-4 text-[#A3A3A3]" />
                    </div>
                    <div>
                        <h3 className="font-semibold text-[#FAFAFA]">Target Discovery</h3>
                        <p className="text-xs text-[#525252]">{targets.length} targets found</p>
                    </div>
                </div>
                <button
                    onClick={onDiscoverTargets}
                    disabled={isDiscovering}
                    className={cn(
                        "flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-all",
                        isDiscovering
                            ? "bg-[#262626] text-[#525252] cursor-wait"
                            : "bg-[#FAFAFA] text-[#000000] hover:bg-[#E5E5E5]"
                    )}
                >
                    <Plus className="w-4 h-4" />
                    {isDiscovering ? "Discovering..." : "Discover"}
                </button>
            </div>

            {/* Target List */}
            <ScrollArea className="flex-1">
                {targets.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-[300px] text-center px-6">
                        <div className="w-16 h-16 rounded-2xl bg-[#171717] flex items-center justify-center mb-4">
                            <Globe className="w-8 h-8 text-[#404040]" />
                        </div>
                        <p className="text-[#525252]">No targets discovered yet</p>
                        <p className="text-xs text-[#404040] mt-2 max-w-[200px]">
                            Click Discover to search public bug bounty programs
                        </p>
                    </div>
                ) : (
                    <div className="p-4 space-y-2">
                        {targets.map((target) => {
                            const isSelected = selectedTargets.has(target.candidate_id)

                            return (
                                <div
                                    key={target.candidate_id}
                                    onClick={() => onSelectTarget(target.candidate_id)}
                                    className={cn(
                                        "p-4 rounded-xl border cursor-pointer transition-all duration-200",
                                        isSelected
                                            ? "bg-violet-500/10 border-violet-500/30"
                                            : "bg-[#171717] border-white/[0.04] hover:border-white/[0.08]"
                                    )}
                                >
                                    <div className="flex items-start justify-between gap-3">
                                        {/* Left side */}
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-2">
                                                {isSelected && (
                                                    <div className="w-4 h-4 rounded-full bg-violet-500 flex items-center justify-center">
                                                        <Check className="w-3 h-3 text-white" />
                                                    </div>
                                                )}
                                                <span className="font-medium text-[#FAFAFA] truncate">
                                                    {target.program_name}
                                                </span>
                                            </div>
                                            <p className="text-xs text-[#525252] mt-1 font-mono truncate">
                                                {target.scope_summary}
                                            </p>
                                        </div>

                                        {/* Right side badges */}
                                        <div className="flex flex-col items-end gap-1.5 shrink-0">
                                            {/* Payout */}
                                            <span className={cn(
                                                "px-2 py-0.5 rounded-full text-xs font-medium flex items-center gap-1",
                                                PAYOUT_COLORS[target.payout_tier]
                                            )}>
                                                <DollarSign className="w-3 h-3" />
                                                {target.payout_tier}
                                            </span>

                                            {/* Density */}
                                            <span className="px-2 py-0.5 rounded-full text-xs text-[#737373] bg-[#262626] flex items-center gap-1">
                                                <BarChart className="w-3 h-3" />
                                                {DENSITY_LABELS[target.report_density]}
                                            </span>
                                        </div>
                                    </div>

                                    {/* Source & Status Row */}
                                    <div className="flex items-center gap-2 mt-3 pt-3 border-t border-white/[0.04]">
                                        <span className="text-xs text-[#525252]">
                                            {SOURCE_LABELS[target.source]}
                                        </span>
                                        <span className="text-[#262626]">•</span>
                                        <span className={cn(
                                            "text-xs",
                                            target.is_public ? "text-emerald-400" : "text-amber-400"
                                        )}>
                                            {target.is_public ? "Public" : "Private"}
                                        </span>
                                        {target.requires_invite && (
                                            <>
                                                <span className="text-[#262626]">•</span>
                                                <span className="text-xs text-amber-400">Invite Only</span>
                                            </>
                                        )}
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                )}
            </ScrollArea>

            {/* Footer */}
            <div className="px-5 py-3 border-t border-white/[0.06] bg-[#0A0A0A]">
                <div className="flex items-center justify-between">
                    <p className="text-xs text-[#404040]">
                        {selectedTargets.size} selected
                    </p>
                    <p className="text-xs text-[#404040]">
                        Read-only discovery
                    </p>
                </div>
            </div>
        </div>
    )
}
