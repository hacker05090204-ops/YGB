"use client"

import { Activity, AlertTriangle, BookOpen, Clock, Crosshair, Gauge, Play, Square } from "lucide-react"

import { cn } from "@/lib/utils"

import type { AccuracySnapshot, RuntimeStatus } from "../hooks/use-runtime-telemetry"

interface RuntimeOverviewProps {
  runtimeMode: "IDLE" | "TRAIN" | "HUNT"
  modeLoading: boolean
  onStartTraining: () => void
  onStopTraining: () => void
  onStartHunting: () => void
  onStopHunting: () => void
  accuracySnapshot: AccuracySnapshot | null
  targetsActive: number
  maxTargets: number
  runtimeStatus: RuntimeStatus | null
  liveTime: number
  isStalled: boolean
  formatDuration: (seconds: number) => string
}

export function RuntimeOverview({
  runtimeMode,
  modeLoading,
  onStartTraining,
  onStopTraining,
  onStartHunting,
  onStopHunting,
  accuracySnapshot,
  targetsActive,
  maxTargets,
  runtimeStatus,
  liveTime,
  isStalled,
  formatDuration,
}: RuntimeOverviewProps) {
  return (
    <>
      <div className="mb-6 p-5 rounded-2xl bg-card/50 border border-border/50">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "w-8 h-8 rounded-lg flex items-center justify-center",
                runtimeMode === "TRAIN" ? "bg-blue-500/20" : runtimeMode === "HUNT" ? "bg-red-500/20" : "bg-zinc-500/20"
              )}
            >
              {runtimeMode === "TRAIN" ? (
                <BookOpen className="w-4 h-4 text-blue-400" />
              ) : runtimeMode === "HUNT" ? (
                <Crosshair className="w-4 h-4 text-red-400" />
              ) : (
                <Gauge className="w-4 h-4 text-zinc-400" />
              )}
            </div>
            <div>
              <h2 className="text-sm font-bold">Runtime Mode</h2>
              <p
                className={cn(
                  "text-xs font-medium",
                  runtimeMode === "TRAIN" ? "text-blue-400" : runtimeMode === "HUNT" ? "text-red-400" : "text-zinc-400"
                )}
              >
                {runtimeMode === "TRAIN" ? "LAB TRAINING" : runtimeMode === "HUNT" ? "HUNT EXECUTION" : "IDLE"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {runtimeMode === "IDLE" ? (
              <>
                <button
                  onClick={onStartTraining}
                  disabled={modeLoading}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-500/20 hover:bg-blue-500/30 text-blue-400 text-xs font-medium transition-colors disabled:opacity-50"
                >
                  <Play className="w-3 h-3" /> Start Training
                </button>
                <button
                  onClick={onStartHunting}
                  disabled={modeLoading}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-400 text-xs font-medium transition-colors disabled:opacity-50"
                >
                  <Crosshair className="w-3 h-3" /> Start Hunting
                </button>
              </>
            ) : runtimeMode === "TRAIN" ? (
              <button
                onClick={onStopTraining}
                disabled={modeLoading}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 text-xs font-medium transition-colors disabled:opacity-50"
              >
                <Square className="w-3 h-3" /> Stop Training
              </button>
            ) : (
              <button
                onClick={onStopHunting}
                disabled={modeLoading}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 text-xs font-medium transition-colors disabled:opacity-50"
              >
                <Square className="w-3 h-3" /> Stop Hunting
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <div className="p-3 rounded-xl bg-background/50 border border-border/30">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Lab Accuracy</p>
            <p className="text-lg font-bold text-emerald-400">{accuracySnapshot ? `${(accuracySnapshot.precision * 100).toFixed(1)}%` : "—"}</p>
          </div>
          <div className="p-3 rounded-xl bg-background/50 border border-border/30">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Precision</p>
            <p className="text-lg font-bold text-blue-400">{accuracySnapshot ? `${(accuracySnapshot.precision * 100).toFixed(1)}%` : "—"}</p>
          </div>
          <div className="p-3 rounded-xl bg-background/50 border border-border/30">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Dup Suppression</p>
            <p className="text-lg font-bold text-purple-400">{accuracySnapshot ? `${(accuracySnapshot.dup_suppression_rate * 100).toFixed(0)}%` : "—"}</p>
          </div>
          <div className="p-3 rounded-xl bg-background/50 border border-border/30">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Scope Compliance</p>
            <p className="text-lg font-bold text-cyan-400">{accuracySnapshot ? `${(accuracySnapshot.scope_compliance * 100).toFixed(0)}%` : "—"}</p>
          </div>
          <div className="p-3 rounded-xl bg-background/50 border border-border/30" id="metric-targets">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Targets Active</p>
            <p className="text-lg font-bold">
              <span className={runtimeMode === "HUNT" ? "text-red-400" : "text-zinc-400"}>{targetsActive}</span>
              <span className="text-xs text-muted-foreground">/{maxTargets}</span>
            </p>
          </div>
        </div>
      </div>

      <div className="mb-6 p-5 rounded-2xl bg-card/50 border border-border/50" id="runtime-telemetry">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/20 flex items-center justify-center">
              <Activity className="w-4 h-4 text-emerald-400" />
            </div>
            <div>
              <h2 className="text-sm font-bold">Runtime Telemetry</h2>
              <p className="text-xs text-muted-foreground">
                {runtimeStatus?.source === "g38_live"
                  ? "Live trainer fallback"
                  : runtimeStatus?.source === "telemetry_file_self_healed"
                    ? "Auto-repaired idle baseline"
                    : "Validated telemetry source"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {isStalled && (
              <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-red-500/20 text-red-400 text-xs font-medium animate-pulse">
                <AlertTriangle className="w-3 h-3" />
                ⚠ Training Stalled
              </div>
            )}
            {runtimeStatus?.stale && (
              <div className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-amber-500/20 text-amber-400 text-xs font-medium animate-pulse">
                <AlertTriangle className="w-3 h-3" />
                STALE DATA
              </div>
            )}
            {runtimeStatus?.auto_repaired && !runtimeStatus?.stale && (
              <div className="px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-400 text-xs font-medium">AUTO-FIXED</div>
            )}
            {runtimeStatus?.status === "awaiting_data" && (
              <div className="px-3 py-1 rounded-full bg-zinc-500/20 text-zinc-400 text-xs font-medium">Awaiting Training Start</div>
            )}
          </div>
        </div>

        {runtimeStatus?.runtime && (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-4">
            <div className="p-2.5 rounded-xl bg-background/50 border border-emerald-500/20">
              <div className="flex items-center gap-1.5 mb-1"><Clock className="w-3 h-3 text-emerald-400" /><p className="text-[10px] text-emerald-400 uppercase tracking-wider font-medium">Training Started</p></div>
              <p className="text-xs font-mono text-emerald-300">{runtimeStatus.runtime.wall_clock_unix > 0 ? new Date((runtimeStatus.runtime.wall_clock_unix - runtimeStatus.runtime.training_duration_seconds) * 1000).toLocaleTimeString() : "—"}</p>
            </div>
            <div className="p-2.5 rounded-xl bg-background/50 border border-blue-500/20">
              <div className="flex items-center gap-1.5 mb-1"><Clock className="w-3 h-3 text-blue-400" /><p className="text-[10px] text-blue-400 uppercase tracking-wider font-medium">Elapsed Time</p></div>
              <p className="text-xs font-mono text-blue-300">{formatDuration(runtimeStatus.runtime.training_duration_seconds)}</p>
            </div>
            <div className="p-2.5 rounded-xl bg-background/50 border border-violet-500/20">
              <div className="flex items-center gap-1.5 mb-1"><Clock className="w-3 h-3 text-violet-400" /><p className="text-[10px] text-violet-400 uppercase tracking-wider font-medium">Samples/sec</p></div>
              <p className="text-xs font-mono text-violet-300">{((runtimeStatus.runtime as any).samples_per_sec ?? 0).toFixed(1)}</p>
            </div>
            <div className="p-2.5 rounded-xl bg-background/50 border border-cyan-500/20">
              <div className="flex items-center gap-1.5 mb-1"><Clock className="w-3 h-3 text-cyan-400" /><p className="text-[10px] text-cyan-400 uppercase tracking-wider font-medium">Checkpoints</p></div>
              <p className="text-xs font-mono text-cyan-300">{(runtimeStatus.runtime as any).checkpoints_saved ?? 0}</p>
            </div>
            <div className="p-2.5 rounded-xl bg-background/50 border border-orange-500/20">
              <div className="flex items-center gap-1.5 mb-1"><Clock className="w-3 h-3 text-orange-400" /><p className="text-[10px] text-orange-400 uppercase tracking-wider font-medium">Tensor Files</p></div>
              <p className="text-xs font-mono text-orange-300">{(runtimeStatus.runtime as any).safetensors_files ?? 0}</p>
            </div>
            <div className="p-2.5 rounded-xl bg-background/50 border border-pink-500/20">
              <div className="flex items-center gap-1.5 mb-1"><Clock className="w-3 h-3 text-pink-400" /><p className="text-[10px] text-pink-400 uppercase tracking-wider font-medium">Live Clock</p></div>
              <p className="text-xs font-mono text-pink-300">{new Date(liveTime).toLocaleTimeString()}</p>
            </div>
          </div>
        )}

        {(runtimeStatus?.status === "active" || (runtimeStatus?.status === "idle" && runtimeStatus?.runtime)) && runtimeStatus?.runtime ? (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Epochs</p><p className="text-lg font-bold text-violet-400">{runtimeStatus.runtime.completed_epochs ?? 0}/{runtimeStatus.runtime.total_epochs ?? 0}</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Progress</p><p className="text-lg font-bold text-blue-400">{(runtimeStatus.runtime.progress_pct ?? 0).toFixed(1)}%</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Loss</p><p className="text-lg font-bold text-amber-400">{(runtimeStatus.runtime.current_loss ?? 0).toFixed(4)}<span className={cn("text-xs ml-1", (runtimeStatus.runtime.loss_trend ?? 0) < 0 ? "text-emerald-400" : "text-red-400")}>{(runtimeStatus.runtime.loss_trend ?? 0) < 0 ? "↓" : "↑"}</span></p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Precision</p><p className="text-lg font-bold text-emerald-400">{((runtimeStatus.runtime.precision ?? 0) * 100).toFixed(1)}%</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">ECE</p><p className="text-lg font-bold text-cyan-400">{(runtimeStatus.runtime.ece ?? 0).toFixed(4)}</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Drift KL</p><p className="text-lg font-bold text-purple-400">{(runtimeStatus.runtime.drift_kl ?? 0).toFixed(4)}</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">GPU Util</p><p className="text-lg font-bold text-orange-400">{(runtimeStatus.runtime.gpu_util ?? 0).toFixed(0)}%</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">CPU Util</p><p className="text-lg font-bold text-sky-400">{(runtimeStatus.runtime.cpu_util ?? 0).toFixed(0)}%</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Temp</p><p className={cn("text-lg font-bold", (runtimeStatus.runtime.temperature ?? 0) > 85 ? "text-red-400" : "text-emerald-400")}>{(runtimeStatus.runtime.temperature ?? 0).toFixed(0)}°C</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Dup Rate</p><p className="text-lg font-bold text-pink-400">{((runtimeStatus.runtime.duplicate_rate ?? 0) * 100).toFixed(1)}%</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Determinism</p><p className={cn("text-lg font-bold", runtimeStatus.runtime.determinism_status ? "text-emerald-400" : "text-red-400")}>{runtimeStatus.runtime.determinism_status ? "✓ OK" : "✗ FAIL"}</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Freeze</p><p className={cn("text-lg font-bold", runtimeStatus.runtime.freeze_status ? "text-emerald-400" : "text-amber-400")}>{runtimeStatus.runtime.freeze_status ? "✓ Valid" : "⚠ Invalid"}</p></div>
          </div>
        ) : runtimeStatus?.status === "idle" && runtimeStatus.runtime ? (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Epochs Done</p><p className="text-lg font-bold text-violet-400">{runtimeStatus.runtime.completed_epochs ?? 0}</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Last Accuracy</p><p className="text-lg font-bold text-emerald-400">{((runtimeStatus.runtime.precision ?? 0) * 100).toFixed(1)}%</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Last Loss</p><p className="text-lg font-bold text-amber-400">{(runtimeStatus.runtime.current_loss ?? 0).toFixed(6)}</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Checkpoints</p><p className="text-lg font-bold text-cyan-400">{(runtimeStatus.runtime as any).checkpoints_saved ?? 0}</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Tensor Files</p><p className="text-lg font-bold text-purple-400">{(runtimeStatus.runtime as any).safetensors_files ?? 0}</p></div>
            <div className="p-3 rounded-xl bg-background/50 border border-border/30"><p className="text-[10px] text-muted-foreground uppercase tracking-wider">Dataset</p><p className="text-lg font-bold text-blue-400">{((runtimeStatus.runtime as any).dataset_size ?? 0).toLocaleString()}</p></div>
          </div>
        ) : (
          <div className="text-center py-6 text-muted-foreground text-sm">
            {runtimeStatus?.status === "error" ? "⚠ Error reading runtime state" : "Waiting for training telemetry..."}
          </div>
        )}
      </div>
    </>
  )
}
