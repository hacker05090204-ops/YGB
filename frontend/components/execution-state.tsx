"use client"

import { cn } from "@/lib/utils"

// Execution states from G01 ExecutionKernel
export type ExecutionStateType = 
  | "IDLE" 
  | "PLANNED" 
  | "SIMULATED" 
  | "AWAIT_HUMAN" 
  | "EXECUTING" 
  | "STOPPED"

interface ExecutionStateProps {
  currentState: ExecutionStateType
  humanApproved?: boolean
  denyReason?: string
  className?: string
}

const STATE_ORDER: ExecutionStateType[] = [
  "IDLE",
  "PLANNED", 
  "SIMULATED",
  "AWAIT_HUMAN",
  "EXECUTING",
  "STOPPED"
]

const STATE_LABELS: Record<ExecutionStateType, string> = {
  IDLE: "Idle",
  PLANNED: "Planned",
  SIMULATED: "Simulated",
  AWAIT_HUMAN: "Awaiting Approval",
  EXECUTING: "Executing",
  STOPPED: "Stopped"
}

const STATE_COLORS: Record<ExecutionStateType, string> = {
  IDLE: "bg-[#404040]",
  PLANNED: "bg-[#525252]",
  SIMULATED: "bg-[#737373]",
  AWAIT_HUMAN: "bg-amber-500",
  EXECUTING: "bg-emerald-500",
  STOPPED: "bg-red-500"
}

export function ExecutionState({ 
  currentState, 
  humanApproved = false,
  denyReason,
  className 
}: ExecutionStateProps) {
  const currentIndex = STATE_ORDER.indexOf(currentState)
  const isTerminal = currentState === "STOPPED"

  return (
    <div className={cn("space-y-4", className)}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[#A3A3A3] uppercase tracking-wider">
          Execution State
        </h3>
        {humanApproved && (
          <span className="px-2 py-1 rounded-full bg-emerald-500/20 text-emerald-400 text-xs font-medium">
            Human Approved
          </span>
        )}
      </div>

      {/* State Pipeline */}
      <div className="flex items-center gap-1">
        {STATE_ORDER.map((state, idx) => {
          const isPast = idx < currentIndex
          const isCurrent = state === currentState
          const isFuture = idx > currentIndex && !isTerminal

          return (
            <div key={state} className="flex items-center flex-1">
              {/* State Node */}
              <div 
                className={cn(
                  "relative flex-1 h-2 rounded-full transition-all duration-300",
                  isCurrent && STATE_COLORS[state],
                  isCurrent && "shadow-[0_0_12px_rgba(255,255,255,0.3)]",
                  isPast && "bg-[#FAFAFA]/60",
                  isFuture && "bg-[#262626]",
                  isTerminal && state === "STOPPED" && "bg-red-500"
                )}
              />
              
              {/* Connector */}
              {idx < STATE_ORDER.length - 1 && (
                <div 
                  className={cn(
                    "w-2 h-0.5",
                    isPast ? "bg-[#FAFAFA]/40" : "bg-[#262626]"
                  )} 
                />
              )}
            </div>
          )
        })}
      </div>

      {/* Current State Label */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={cn(
            "w-3 h-3 rounded-full",
            STATE_COLORS[currentState],
            currentState === "AWAIT_HUMAN" && "animate-pulse"
          )} />
          <span className="text-lg font-semibold text-[#FAFAFA]">
            {STATE_LABELS[currentState]}
          </span>
        </div>
        
        {isTerminal && denyReason && (
          <span className="text-xs text-red-400 max-w-[200px] truncate">
            {denyReason}
          </span>
        )}
      </div>

      {/* State Hints */}
      <div className="text-xs text-[#525252]">
        {currentState === "IDLE" && "Ready to begin workflow"}
        {currentState === "PLANNED" && "Execution plan created"}
        {currentState === "SIMULATED" && "Simulation complete, ready for approval"}
        {currentState === "AWAIT_HUMAN" && "⚠️ Waiting for human approval to proceed"}
        {currentState === "EXECUTING" && "Browser automation in progress..."}
        {currentState === "STOPPED" && "Workflow terminated"}
      </div>
    </div>
  )
}
