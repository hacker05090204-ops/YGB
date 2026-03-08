"use client"

import * as React from "react"
import { authFetch , getApiBase } from "@/lib/ygb-api"

interface ReportItem {
    filename: string
    size: number
    created: string
}

interface VideoItem {
    id: string
    report_id: string | null
    filename: string
    duration_seconds: number
    file_size_bytes: number
    status: string
    started_at: string
    stopped_at: string | null
    storage_path: string | null
    created_by: string
    metadata_json: string
}

interface RuntimeSnapshot {
    status?: string
    stale?: boolean
    determinism_ok?: boolean
}

function safeIso(iso: string): string {
    try {
        return new Date(iso).toLocaleString()
    } catch {
        return iso
    }
}

export function ReportGeneratorSession({ className = "", refreshInterval = 8000 }) {
    const [reports, setReports] = React.useState<ReportItem[]>([])
    const [videos, setVideos] = React.useState<VideoItem[]>([])
    const [title, setTitle] = React.useState("YGB Security Session Report")
    const [targetScope, setTargetScope] = React.useState("")
    const [notes, setNotes] = React.useState("")
    const [selectedReport, setSelectedReport] = React.useState("")
    const [selectedVideo, setSelectedVideo] = React.useState("")
    const [includeTrainingSnapshot, setIncludeTrainingSnapshot] = React.useState(true)
    const [loading, setLoading] = React.useState(true)
    const [generating, setGenerating] = React.useState(false)
    const [error, setError] = React.useState<string | null>(null)
    const [generatedAt, setGeneratedAt] = React.useState<string | null>(null)
    const [isRecording, setIsRecording] = React.useState(false)
    const [recordingId, setRecordingId] = React.useState<string | null>(null)
    const [recordingStart, setRecordingStart] = React.useState<number | null>(null)
    const [recordingElapsed, setRecordingElapsed] = React.useState(0)

    const refresh = React.useCallback(async () => {
        try {
            const [reportsRes, videosRes] = await Promise.all([
                authFetch(`${getApiBase()}/api/reports`),
                authFetch(`${getApiBase()}/api/reports/videos`),
            ])

            if (reportsRes.ok) {
                const reportData = await reportsRes.json()
                setReports(Array.isArray(reportData.reports) ? reportData.reports : [])
            } else {
                setReports([])
            }

            if (videosRes.ok) {
                const videoData = await videosRes.json()
                setVideos(Array.isArray(videoData.videos) ? videoData.videos : [])
            } else {
                setVideos([])
            }
        } catch {
            setReports([])
            setVideos([])
        } finally {
            setLoading(false)
        }
    }, [])

    React.useEffect(() => {
        refresh()
        const timer = setInterval(refresh, refreshInterval)
        return () => clearInterval(timer)
    }, [refresh, refreshInterval])

    // Recording elapsed timer
    React.useEffect(() => {
        if (!isRecording || !recordingStart) return
        const timer = setInterval(() => {
            setRecordingElapsed(Math.floor((Date.now() - recordingStart) / 1000))
        }, 1000)
        return () => clearInterval(timer)
    }, [isRecording, recordingStart])

    const startRecording = React.useCallback(async () => {
        try {
            const res = await authFetch(`${getApiBase()}/api/reports/videos/start`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ report_id: null, metadata: { source: "control_panel" } }),
            })
            if (res.ok) {
                const data = await res.json()
                setRecordingId(data.recording?.id || null)
                setIsRecording(true)
                setRecordingStart(Date.now())
                setRecordingElapsed(0)
            } else {
                setError("Failed to start recording")
            }
        } catch {
            setError("Failed to start recording")
        }
    }, [])

    const stopRecording = React.useCallback(async () => {
        if (!recordingId) return
        try {
            await authFetch(`${getApiBase()}/api/reports/videos/${recordingId}/stop`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    duration_seconds: recordingElapsed,
                    file_size_bytes: 0,
                }),
            })
            setIsRecording(false)
            setRecordingId(null)
            setRecordingStart(null)
            refresh()
        } catch {
            setError("Failed to stop recording")
        }
    }, [recordingId, recordingElapsed, refresh])

    const generateBundle = React.useCallback(async () => {
        setGenerating(true)
        setError(null)

        try {
            let reportContent: string | null = null
            if (selectedReport) {
                const reportRes = await authFetch(`${getApiBase()}/api/reports/${encodeURIComponent(selectedReport)}/content`)
                if (reportRes.ok) {
                    reportContent = await reportRes.text()
                }
            }

            let videoToken: string | null = null
            let selectedVideoMeta: VideoItem | null = null
            if (selectedVideo) {
                selectedVideoMeta = videos.find(v =>
                    v.id === selectedVideo
                ) || null

                if (selectedVideoMeta) {
                    const tokenRes = await authFetch(`${getApiBase()}/api/video/token`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            user_id: selectedVideoMeta.created_by,
                            session_id: selectedVideoMeta.id,
                            filename: selectedVideoMeta.filename,
                        }),
                    })
                    if (tokenRes.ok) {
                        const tokenData = await tokenRes.json()
                        videoToken = typeof tokenData.token === "string" ? tokenData.token : null
                    }
                }
            }

            let runtime: RuntimeSnapshot | null = null
            let accuracy: Record<string, unknown> | null = null
            if (includeTrainingSnapshot) {
                const [runtimeRes, accuracyRes] = await Promise.all([
                    authFetch(`${getApiBase()}/runtime/status`),
                    authFetch(`${getApiBase()}/api/accuracy/snapshot`),
                ])

                if (runtimeRes.ok) {
                    runtime = await runtimeRes.json()
                }
                if (accuracyRes.ok) {
                    accuracy = await accuracyRes.json()
                }
            }

            const bundle = {
                generated_at: new Date().toISOString(),
                report_title: title.trim() || "YGB Security Session Report",
                target_scope: targetScope.trim() || null,
                notes: notes.trim() || null,
                governance: {
                    frontend_execution_authority: false,
                    report_generated_from: "control_panel",
                    includes_video_artifact: Boolean(selectedVideo),
                },
                artifacts: {
                    report: selectedReport
                        ? {
                            filename: selectedReport,
                            content: reportContent,
                        }
                        : null,
                    video: selectedVideoMeta
                        ? {
                            user_id: selectedVideoMeta.created_by,
                            session_id: selectedVideoMeta.id,
                            filename: selectedVideoMeta.filename,
                            created_at: selectedVideoMeta.started_at,
                            size_bytes: selectedVideoMeta.file_size_bytes,
                            stream_token: videoToken,
                        }
                        : null,
                },
                training_snapshot: includeTrainingSnapshot
                    ? {
                        runtime_status: runtime?.status || null,
                        determinism_ok: runtime?.determinism_ok ?? null,
                        stale: runtime?.stale ?? null,
                        accuracy,
                    }
                    : null,
            }

            const fileStem = (title.trim() || "ygb-report")
                .toLowerCase()
                .replace(/[^a-z0-9]+/g, "-")
                .replace(/^-+|-+$/g, "")
            const timestamp = new Date().toISOString().replace(/[:.]/g, "-")
            const fileName = `${fileStem || "ygb-report"}-${timestamp}.json`

            const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" })
            const url = URL.createObjectURL(blob)
            const a = document.createElement("a")
            a.href = url
            a.download = fileName
            a.click()
            URL.revokeObjectURL(url)

            setGeneratedAt(new Date().toISOString())
        } catch {
            setError("Failed to generate report bundle")
        } finally {
            setGenerating(false)
        }
    }, [includeTrainingSnapshot, notes, selectedReport, selectedVideo, targetScope, title, videos])

    return (
        <div className={`p-6 rounded-2xl bg-card/50 border border-border/50 ${className}`}>
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-muted-foreground">Report Generator</h3>
                <span className="text-[10px] px-2 py-1 rounded-full bg-muted text-muted-foreground">
                    reports {reports.length} · videos {videos.length}
                </span>
            </div>

            {/* Video Recording Controls */}
            <div className="flex items-center gap-2 mb-3">
                {isRecording ? (
                    <>
                        <button
                            type="button"
                            onClick={stopRecording}
                            className="flex-1 rounded-lg bg-red-500/20 border border-red-500/30 px-3 py-2 text-sm font-semibold text-red-300 hover:bg-red-500/30 animate-pulse"
                        >
                            Stop Recording ({Math.floor(recordingElapsed / 60)}:{String(recordingElapsed % 60).padStart(2, '0')})
                        </button>
                        <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                    </>
                ) : (
                    <button
                        type="button"
                        onClick={startRecording}
                        disabled={loading}
                        className="flex-1 rounded-lg bg-purple-500/20 border border-purple-500/30 px-3 py-2 text-sm font-semibold text-purple-300 hover:bg-purple-500/30 disabled:opacity-50"
                    >
                        Record Session
                    </button>
                )}
            </div>

            <div className="space-y-3">
                <input
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Report title"
                    className="w-full rounded-lg border border-border/50 bg-background/70 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-cyan-500/40"
                />
                <input
                    value={targetScope}
                    onChange={(e) => setTargetScope(e.target.value)}
                    placeholder="Target / scope"
                    className="w-full rounded-lg border border-border/50 bg-background/70 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-cyan-500/40"
                />
                <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Analyst notes"
                    rows={3}
                    className="w-full rounded-lg border border-border/50 bg-background/70 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-cyan-500/40"
                />

                <select
                    value={selectedReport}
                    onChange={(e) => setSelectedReport(e.target.value)}
                    className="w-full rounded-lg border border-border/50 bg-background/70 px-3 py-2 text-sm"
                >
                    <option value="">Attach report file (optional)</option>
                    {reports.map((r) => (
                        <option key={r.filename} value={r.filename}>
                            {r.filename} · {safeIso(r.created)}
                        </option>
                    ))}
                </select>

                <select
                    value={selectedVideo}
                    onChange={(e) => setSelectedVideo(e.target.value)}
                    className="w-full rounded-lg border border-border/50 bg-background/70 px-3 py-2 text-sm"
                >
                    <option value="">Attach recorded video (optional)</option>
                    {videos.map((v) => {
                        return (
                            <option key={v.id} value={v.id}>
                                {v.id} · {v.filename} · {safeIso(v.started_at)}
                            </option>
                        )
                    })}
                </select>

                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    <input
                        type="checkbox"
                        checked={includeTrainingSnapshot}
                        onChange={(e) => setIncludeTrainingSnapshot(e.target.checked)}
                    />
                    Include runtime training snapshot
                </label>

                {error ? <p className="text-xs text-red-500">{error}</p> : null}
                {generatedAt ? (
                    <p className="text-xs text-emerald-500">Last generated: {safeIso(generatedAt)}</p>
                ) : null}

                <button
                    type="button"
                    disabled={loading || generating}
                    onClick={generateBundle}
                    className="w-full rounded-lg bg-cyan-500/20 border border-cyan-500/30 px-3 py-2 text-sm font-semibold text-cyan-300 hover:bg-cyan-500/30 disabled:opacity-50"
                >
                    {generating ? "Generating..." : "Generate Report Bundle"}
                </button>
            </div>
        </div>
    )
}

