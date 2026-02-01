"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import {
    Bot,
    Check,
    X,
    Lightbulb,
    ChevronDown,
    ChevronRight,
    Sparkles,
    AlertCircle
} from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"

// Types from G05 AssistantMode
export type MethodDecisionType = "SELECTED" | "REJECTED" | "PROPOSED"

export interface MethodExplanation {
    method_id: string
    method_name: string
    decision: MethodDecisionType
    reason: string
    confidence: number
    alternatives: string[]
}

export interface AssistantExplanation {
    explanation_id: string
    mode: "EXPLAIN" | "SUGGEST" | "GUIDE"
    selected_method: MethodExplanation | null
    rejected_methods: MethodExplanation[]
    amse_proposals: MethodExplanation[]
    summary: string
    requires_approval: boolean
    approval_reason: string
    timestamp: string
}

interface BrowserAssistantProps {
    currentAction?: string
    explanations: AssistantExplanation[]
    isActive?: boolean
    className?: string
}

export function BrowserAssistant({
    currentAction,
    explanations,
    isActive = false,
    className
}: BrowserAssistantProps) {
    const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set())

    const toggleExpand = (id: string) => {
        setExpandedItems(prev => {
            const next = new Set(prev)
            next.has(id) ? next.delete(id) : next.add(id)
            return next
        })
    }

    const latestExplanation = explanations[explanations.length - 1]

    return (
        <div className={cn(
            "flex flex-col h-full rounded-2xl bg-[#0A0A0A] border border-white/[0.06] overflow-hidden",
            className
        )}>
            {/* Header */}
            <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between bg-gradient-to-r from-[#0A0A0A] to-[#171717]">
                <div className="flex items-center gap-3">
                    <div className={cn(
                        "w-8 h-8 rounded-lg flex items-center justify-center",
                        isActive
                            ? "bg-gradient-to-br from-violet-500 to-purple-600 shadow-[0_0_20px_rgba(139,92,246,0.3)]"
                            : "bg-[#262626]"
                    )}>
                        <Bot className={cn(
                            "w-4 h-4",
                            isActive ? "text-white" : "text-[#525252]"
                        )} />
                    </div>
                    <div>
                        <h3 className="font-semibold text-[#FAFAFA]">Browser Assistant</h3>
                        <p className="text-xs text-[#525252]">Explain-only intelligence</p>
                    </div>
                </div>
                {isActive && (
                    <span className="px-2 py-1 rounded-full bg-violet-500/20 text-violet-400 text-xs font-medium animate-pulse">
                        Active
                    </span>
                )}
            </div>

            {/* Current Action Banner */}
            {currentAction && (
                <div className="px-5 py-3 bg-gradient-to-r from-violet-500/10 to-purple-500/10 border-b border-violet-500/20">
                    <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-violet-400 animate-pulse" />
                        <span className="text-sm text-violet-300">Currently: {currentAction}</span>
                    </div>
                </div>
            )}

            {/* Content */}
            <ScrollArea className="flex-1 p-5">
                {explanations.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full py-12 text-center">
                        <div className="w-16 h-16 rounded-2xl bg-[#171717] flex items-center justify-center mb-4">
                            <Sparkles className="w-8 h-8 text-[#404040]" />
                        </div>
                        <p className="text-[#525252]">No activity yet</p>
                        <p className="text-xs text-[#404040] mt-2 max-w-[200px]">
                            Assistant will explain what the system is doing and why
                        </p>
                    </div>
                ) : (
                    <div className="space-y-4">
                        {explanations.slice().reverse().map((exp) => (
                            <div
                                key={exp.explanation_id}
                                className="rounded-xl bg-[#171717] border border-white/[0.04] overflow-hidden"
                            >
                                {/* Summary */}
                                <div
                                    className="px-4 py-3 flex items-start gap-3 cursor-pointer hover:bg-white/[0.02]"
                                    onClick={() => toggleExpand(exp.explanation_id)}
                                >
                                    {expandedItems.has(exp.explanation_id) ? (
                                        <ChevronDown className="w-4 h-4 text-[#525252] mt-0.5 shrink-0" />
                                    ) : (
                                        <ChevronRight className="w-4 h-4 text-[#525252] mt-0.5 shrink-0" />
                                    )}
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm text-[#A3A3A3]">{exp.summary}</p>
                                        {exp.requires_approval && (
                                            <div className="flex items-center gap-1 mt-2 text-xs text-amber-400">
                                                <AlertCircle className="w-3 h-3" />
                                                {exp.approval_reason}
                                            </div>
                                        )}
                                    </div>
                                </div>

                                {/* Expanded Details */}
                                {expandedItems.has(exp.explanation_id) && (
                                    <div className="px-4 pb-4 space-y-3 border-t border-white/[0.04] pt-3">
                                        {/* Selected Method */}
                                        {exp.selected_method && (
                                            <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                                                <div className="flex items-center gap-2 mb-2">
                                                    <Check className="w-4 h-4 text-emerald-400" />
                                                    <span className="text-xs font-medium text-emerald-400 uppercase tracking-wider">Selected</span>
                                                </div>
                                                <p className="text-sm text-[#FAFAFA] font-medium">{exp.selected_method.method_name}</p>
                                                <p className="text-xs text-emerald-400/70 mt-1">{exp.selected_method.reason}</p>
                                                <div className="flex items-center gap-2 mt-2">
                                                    <div className="h-1 flex-1 bg-[#262626] rounded-full overflow-hidden">
                                                        <div
                                                            className="h-full bg-emerald-500 rounded-full"
                                                            style={{ width: `${exp.selected_method.confidence * 100}%` }}
                                                        />
                                                    </div>
                                                    <span className="text-xs text-emerald-400">
                                                        {Math.round(exp.selected_method.confidence * 100)}%
                                                    </span>
                                                </div>
                                            </div>
                                        )}

                                        {/* Rejected Methods */}
                                        {exp.rejected_methods.length > 0 && (
                                            <div className="space-y-2">
                                                <div className="flex items-center gap-2">
                                                    <X className="w-4 h-4 text-red-400" />
                                                    <span className="text-xs font-medium text-red-400 uppercase tracking-wider">Rejected</span>
                                                </div>
                                                {exp.rejected_methods.map((method) => (
                                                    <div
                                                        key={method.method_id}
                                                        className="p-2 rounded-lg bg-red-500/10 border border-red-500/10"
                                                    >
                                                        <p className="text-xs text-[#A3A3A3]">{method.method_name}</p>
                                                        <p className="text-xs text-red-400/60 mt-1">{method.reason}</p>
                                                    </div>
                                                ))}
                                            </div>
                                        )}

                                        {/* AMSE Proposals */}
                                        {exp.amse_proposals.length > 0 && (
                                            <div className="space-y-2">
                                                <div className="flex items-center gap-2">
                                                    <Lightbulb className="w-4 h-4 text-blue-400" />
                                                    <span className="text-xs font-medium text-blue-400 uppercase tracking-wider">AMSE Proposals</span>
                                                </div>
                                                {exp.amse_proposals.map((method) => (
                                                    <div
                                                        key={method.method_id}
                                                        className="p-2 rounded-lg bg-blue-500/10 border border-blue-500/10"
                                                    >
                                                        <p className="text-xs text-[#A3A3A3]">{method.method_name}</p>
                                                        <p className="text-xs text-blue-400/60 mt-1">{method.reason}</p>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </ScrollArea>

            {/* Footer - No Authority Notice */}
            <div className="px-5 py-3 border-t border-white/[0.06] bg-[#0A0A0A]">
                <p className="text-xs text-[#404040] text-center">
                    🔒 Assistant has NO execution authority — display only
                </p>
            </div>
        </div>
    )
}
