"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { Clock, Shield, Eye, Zap } from "lucide-react"

// Autonomy modes from G06
export type AutonomyModeType = "READ_ONLY" | "AUTONOMOUS_FIND" | "REAL"

interface ModeSelectorProps {
    currentMode: AutonomyModeType
    onModeChange: (mode: AutonomyModeType, hours?: number) => void
    disabled?: boolean
    className?: string
}

const MODE_CONFIG: Record<AutonomyModeType, {
    label: string
    description: string
    icon: React.ReactNode
    color: string
    requiresHours?: boolean
    requiresHumanEnable?: boolean
}> = {
    READ_ONLY: {
        label: "Read Only",
        description: "Analysis and reconnaissance only",
        icon: <Eye className="w-4 h-4" />,
        color: "bg-blue-500/20 border-blue-500/40"
    },
    AUTONOMOUS_FIND: {
        label: "Autonomous Find",
        description: "Timed discovery (max 12 hours)",
        icon: <Clock className="w-4 h-4" />,
        color: "bg-amber-500/20 border-amber-500/40",
        requiresHours: true
    },
    REAL: {
        label: "Real",
        description: "Full execution - requires explicit enable",
        icon: <Zap className="w-4 h-4" />,
        color: "bg-red-500/20 border-red-500/40",
        requiresHumanEnable: true
    }
}

const HOUR_OPTIONS = [
    { value: 0, label: "Infinite (until STOP)" },
    { value: 1, label: "1 hour" },
    { value: 2, label: "2 hours" },
    { value: 4, label: "4 hours" },
    { value: 8, label: "8 hours" },
    { value: 12, label: "12 hours (max)" }
]

export function ModeSelector({
    currentMode,
    onModeChange,
    disabled = false,
    className
}: ModeSelectorProps) {
    const [hours, setHours] = useState(0)
    const [humanEnabled, setHumanEnabled] = useState(false)

    const handleModeSelect = (mode: AutonomyModeType) => {
        if (disabled) return

        if (mode === "AUTONOMOUS_FIND") {
            onModeChange(mode, hours)
        } else if (mode === "REAL" && !humanEnabled) {
            // Cannot select REAL without human enable
            return
        } else {
            onModeChange(mode)
        }
    }

    return (
        <div className={cn("space-y-4", className)}>
            {/* Header */}
            <h3 className="text-sm font-semibold text-[#A3A3A3] uppercase tracking-wider">
                Autonomy Mode
            </h3>

            {/* Mode Grid */}
            <div className="grid grid-cols-2 gap-3">
                {(Object.keys(MODE_CONFIG) as AutonomyModeType[]).map((mode) => {
                    const config = MODE_CONFIG[mode]
                    const isSelected = currentMode === mode
                    const isDisabled = disabled || (mode === "REAL" && !humanEnabled)

                    return (
                        <button
                            key={mode}
                            onClick={() => handleModeSelect(mode)}
                            disabled={isDisabled}
                            className={cn(
                                "relative p-4 rounded-xl border-2 transition-all duration-200 text-left",
                                isSelected
                                    ? cn(config.color, "shadow-[0_0_20px_rgba(255,255,255,0.1)]")
                                    : "bg-[#0A0A0A] border-[#262626] hover:border-[#404040]",
                                isDisabled && "opacity-50 cursor-not-allowed"
                            )}
                        >
                            {/* Icon */}
                            <div className={cn(
                                "w-8 h-8 rounded-lg flex items-center justify-center mb-3",
                                isSelected ? "bg-white/10 text-white" : "bg-[#171717] text-[#525252]"
                            )}>
                                {config.icon}
                            </div>

                            {/* Label */}
                            <div className="font-medium text-[#FAFAFA]">{config.label}</div>

                            {/* Description */}
                            <div className="text-xs text-[#525252] mt-1">{config.description}</div>

                            {/* Selected Indicator */}
                            {isSelected && (
                                <div className="absolute top-3 right-3 w-2 h-2 rounded-full bg-white shadow-[0_0_8px_rgba(255,255,255,0.5)]" />
                            )}
                        </button>
                    )
                })}
            </div>

            {/* Hours Selector (for AUTONOMOUS_FIND) */}
            {currentMode === "AUTONOMOUS_FIND" && (
                <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/20">
                    <label className="text-sm font-medium text-amber-400 block mb-3">
                        Duration
                    </label>
                    <select
                        value={hours}
                        onChange={(e) => {
                            const newHours = parseInt(e.target.value)
                            setHours(newHours)
                            onModeChange("AUTONOMOUS_FIND", newHours)
                        }}
                        disabled={disabled}
                        className="w-full px-4 py-2 rounded-lg bg-[#0A0A0A] border border-[#262626] text-[#FAFAFA] focus:outline-none focus:border-amber-500/50"
                    >
                        {HOUR_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                                {opt.label}
                            </option>
                        ))}
                    </select>
                    <p className="text-xs text-amber-400/60 mt-2">
                        Allowed: target analysis, CVE correlation, passive discovery, draft reports
                    </p>
                </div>
            )}

            {/* Human Enable Checkbox (for REAL mode) */}
            <div className="flex items-center gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/20">
                <input
                    type="checkbox"
                    id="humanEnable"
                    checked={humanEnabled}
                    onChange={(e) => setHumanEnabled(e.target.checked)}
                    disabled={disabled}
                    className="w-4 h-4 rounded border-red-500/50 bg-transparent"
                />
                <label htmlFor="humanEnable" className="text-sm text-red-400">
                    Enable REAL mode (full execution authority)
                </label>
            </div>

            {/* Safety Note */}
            <p className="text-xs text-[#404040] text-center">
                All modes require human approval for execution via Dashboard Router
            </p>
        </div>
    )
}
