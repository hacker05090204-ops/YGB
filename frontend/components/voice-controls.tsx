"use client"

import { useState, useRef, useEffect } from "react"
import { cn } from "@/lib/utils"
import { Mic, MicOff, Volume2, VolumeX, Globe, Loader2, Shield, Search, BookOpen } from "lucide-react"

// Voice intent types from G12 (extended with RESEARCH_QUERY)
export type VoiceIntentType =
    | "SET_TARGET"
    | "SET_SCOPE"
    | "QUERY_STATUS"
    | "QUERY_PROGRESS"
    | "QUERY_GPU"
    | "QUERY_TRAINING"
    | "FIND_TARGETS"
    | "SCREEN_TAKEOVER"
    | "REPORT_HELP"
    | "RESEARCH_QUERY"
    | "UNKNOWN"

export type VoiceInputStatusType = "PARSED" | "INVALID" | "REJECTED" | "BLOCKED"

export type VoiceModeType = "SECURITY" | "RESEARCH"

export interface ResearchResultData {
    title: string
    summary: string
    source: string
    source_domains: string[]
    confidence: number
    key_terms: string[]
    word_count: number
    elapsed_ms: number
}

export interface VoiceIntent {
    intent_id: string
    intent_type: VoiceIntentType
    raw_text: string
    extracted_value: string | null
    confidence: number
    status: VoiceInputStatusType
    block_reason: string | null
    active_mode?: VoiceModeType
    research_result?: ResearchResultData | null
    timestamp: string
}

interface VoiceControlsProps {
    onVoiceInput?: (text: string) => void
    lastIntent?: VoiceIntent | null
    isProcessing?: boolean
    voiceMode?: VoiceModeType
    onModeChange?: (mode: VoiceModeType) => void
    className?: string
}

type LanguageType = "EN" | "HI"

export function VoiceControls({
    onVoiceInput,
    lastIntent,
    isProcessing = false,
    voiceMode = "SECURITY",
    onModeChange,
    className
}: VoiceControlsProps) {
    const [voiceEnabled, setVoiceEnabled] = useState(false)
    const [speakerEnabled, setSpeakerEnabled] = useState(true)
    const [language, setLanguage] = useState<LanguageType>("EN")
    const [isListening, setIsListening] = useState(false)
    const [transcript, setTranscript] = useState("")

    // Web Speech API recognition
    const recognitionRef = useRef<any>(null)

    useEffect(() => {
        // Initialize speech recognition
        if (typeof window !== "undefined" && "webkitSpeechRecognition" in window) {
            const SpeechRecognition = (window as any).webkitSpeechRecognition
            recognitionRef.current = new SpeechRecognition()
            recognitionRef.current.continuous = false
            recognitionRef.current.interimResults = true
            recognitionRef.current.lang = language === "EN" ? "en-US" : "hi-IN"

            recognitionRef.current.onresult = (event: any) => {
                const current = event.resultIndex
                const result = event.results[current]
                const text = result[0].transcript
                setTranscript(text)

                if (result.isFinal) {
                    onVoiceInput?.(text)
                    setIsListening(false)
                }
            }

            recognitionRef.current.onend = () => {
                setIsListening(false)
            }

            recognitionRef.current.onerror = () => {
                setIsListening(false)
            }
        }

        return () => {
            if (recognitionRef.current) {
                recognitionRef.current.abort()
            }
        }
    }, [language, onVoiceInput])

    const toggleVoice = () => {
        if (!voiceEnabled) {
            setVoiceEnabled(true)
        } else {
            setVoiceEnabled(false)
            if (isListening) {
                recognitionRef.current?.abort()
                setIsListening(false)
            }
        }
    }

    const startListening = () => {
        if (!voiceEnabled || !recognitionRef.current) return

        recognitionRef.current.lang = language === "EN" ? "en-US" : "hi-IN"
        setTranscript("")
        setIsListening(true)

        try {
            recognitionRef.current.start()
        } catch (e) {
            // Already started
        }
    }

    const stopListening = () => {
        recognitionRef.current?.stop()
        setIsListening(false)
    }

    const getIntentStatusColor = (status: VoiceInputStatusType) => {
        switch (status) {
            case "PARSED": return "text-emerald-400"
            case "INVALID": return "text-amber-400"
            case "REJECTED": return "text-red-400"
            case "BLOCKED": return "text-red-500"
            default: return "text-[#525252]"
        }
    }

    const isResearchMode = voiceMode === "RESEARCH"
    const hasResearchResult = lastIntent?.research_result && lastIntent.intent_type === "RESEARCH_QUERY"

    return (
        <div className={cn("space-y-4", className)}>
            {/* Mode Toggle + Main Controls Row */}
            <div className="flex items-center gap-3 flex-wrap">
                {/* Dual Mode Toggle */}
                <div className="flex items-center bg-[#0A0A0A] rounded-xl border border-white/[0.06] p-1">
                    <button
                        onClick={() => onModeChange?.("SECURITY")}
                        className={cn(
                            "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200",
                            voiceMode === "SECURITY"
                                ? "bg-violet-500/20 text-violet-400 shadow-[0_0_10px_rgba(139,92,246,0.15)]"
                                : "text-[#525252] hover:text-[#A3A3A3]"
                        )}
                    >
                        <Shield className="w-3.5 h-3.5" />
                        Security
                    </button>
                    <button
                        onClick={() => onModeChange?.("RESEARCH")}
                        className={cn(
                            "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200",
                            voiceMode === "RESEARCH"
                                ? "bg-cyan-500/20 text-cyan-400 shadow-[0_0_10px_rgba(6,182,212,0.15)]"
                                : "text-[#525252] hover:text-[#A3A3A3]"
                        )}
                    >
                        <Search className="w-3.5 h-3.5" />
                        Research
                    </button>
                </div>

                {/* Active Mode Badge */}
                <div className={cn(
                    "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider",
                    isResearchMode
                        ? "bg-cyan-500/10 text-cyan-400 border border-cyan-500/20"
                        : "bg-violet-500/10 text-violet-400 border border-violet-500/20"
                )}>
                    <div className={cn(
                        "w-1.5 h-1.5 rounded-full",
                        isResearchMode ? "bg-cyan-400" : "bg-violet-400"
                    )} />
                    {isResearchMode ? "Research Mode" : "Security Mode"}
                </div>

                <div className="flex-1" />

                {/* Voice Toggle */}
                <button
                    onClick={toggleVoice}
                    className={cn(
                        "flex items-center gap-2 px-4 py-2 rounded-xl font-medium transition-all duration-200",
                        voiceEnabled
                            ? isResearchMode
                                ? "bg-cyan-500 text-white shadow-[0_0_20px_rgba(6,182,212,0.3)]"
                                : "bg-violet-500 text-white shadow-[0_0_20px_rgba(139,92,246,0.3)]"
                            : "bg-[#171717] text-[#525252] hover:bg-[#262626]"
                    )}
                >
                    {voiceEnabled ? <Mic className="w-4 h-4" /> : <MicOff className="w-4 h-4" />}
                    Voice {voiceEnabled ? "ON" : "OFF"}
                </button>

                {/* Language Toggle */}
                <button
                    onClick={() => setLanguage(language === "EN" ? "HI" : "EN")}
                    className={cn(
                        "flex items-center gap-2 px-3 py-2 rounded-xl font-medium transition-all duration-200",
                        "bg-[#171717] text-[#A3A3A3] hover:bg-[#262626]"
                    )}
                >
                    <Globe className="w-4 h-4" />
                    {language}
                </button>

                {/* Speaker Toggle */}
                <button
                    onClick={() => setSpeakerEnabled(!speakerEnabled)}
                    className={cn(
                        "flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-200",
                        speakerEnabled
                            ? "bg-[#262626] text-[#FAFAFA]"
                            : "bg-[#171717] text-[#404040]"
                    )}
                >
                    {speakerEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
                </button>
            </div>

            {/* Listening Area */}
            {voiceEnabled && (
                <div className={cn(
                    "p-4 rounded-xl bg-[#0A0A0A] border space-y-3",
                    isResearchMode ? "border-cyan-500/20" : "border-violet-500/20"
                )}>
                    {/* Mic Button */}
                    <button
                        onClick={isListening ? stopListening : startListening}
                        disabled={isProcessing}
                        className={cn(
                            "w-full flex items-center justify-center gap-3 py-4 rounded-xl font-medium transition-all duration-200",
                            isListening
                                ? isResearchMode
                                    ? "bg-cyan-500 text-white animate-pulse shadow-[0_0_30px_rgba(6,182,212,0.4)]"
                                    : "bg-violet-500 text-white animate-pulse shadow-[0_0_30px_rgba(139,92,246,0.4)]"
                                : isResearchMode
                                    ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/30"
                                    : "bg-violet-500/20 text-violet-400 border border-violet-500/30 hover:bg-violet-500/30"
                        )}
                    >
                        {isProcessing ? (
                            <Loader2 className="w-5 h-5 animate-spin" />
                        ) : isListening ? (
                            <>
                                <div className="w-3 h-3 rounded-full bg-white animate-ping" />
                                Listening...
                            </>
                        ) : (
                            <>
                                <Mic className="w-5 h-5" />
                                Click to speak
                            </>
                        )}
                    </button>

                    {/* Transcript */}
                    {transcript && (
                        <div className="p-3 rounded-lg bg-[#171717] border border-white/[0.04]">
                            <p className="text-xs text-[#525252] uppercase tracking-wider mb-1">You said:</p>
                            <p className="text-sm text-[#FAFAFA]">"{transcript}"</p>
                        </div>
                    )}

                    {/* Research Result Panel */}
                    {hasResearchResult && lastIntent?.research_result && (
                        <div className="p-4 rounded-xl bg-gradient-to-br from-cyan-500/5 to-cyan-500/[0.02] border border-cyan-500/20 space-y-3">
                            {/* Informational Banner */}
                            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
                                <span className="text-amber-400 text-[10px] font-semibold uppercase tracking-wider">
                                    ⚠️ Research mode is informational only.
                                </span>
                            </div>

                            <div className="flex items-center gap-2">
                                <BookOpen className="w-4 h-4 text-cyan-400" />
                                <p className="text-xs text-cyan-400 font-semibold uppercase tracking-wider">Research Answer</p>
                            </div>
                            {lastIntent.research_result.title && (
                                <p className="text-sm font-medium text-[#FAFAFA]">
                                    {lastIntent.research_result.title}
                                </p>
                            )}
                            <p className="text-sm text-[#D4D4D4] leading-relaxed">
                                {lastIntent.research_result.summary}
                            </p>

                            {/* Confidence Score Bar */}
                            {lastIntent.research_result.confidence > 0 && (
                                <div className="flex items-center gap-2">
                                    <span className="text-[10px] text-[#525252] uppercase tracking-wider">Confidence</span>
                                    <div className="h-1.5 flex-1 bg-[#262626] rounded-full overflow-hidden">
                                        <div
                                            className="h-full rounded-full bg-cyan-500"
                                            style={{ width: `${Math.round(lastIntent.research_result.confidence * 100)}%` }}
                                        />
                                    </div>
                                    <span className="text-[10px] text-cyan-400 font-medium">
                                        {Math.round(lastIntent.research_result.confidence * 100)}%
                                    </span>
                                </div>
                            )}

                            {/* Source Domains */}
                            {lastIntent.research_result.source_domains?.length > 0 && (
                                <div className="space-y-1">
                                    <span className="text-[10px] text-[#525252] uppercase tracking-wider">Verified Sources</span>
                                    <div className="flex flex-wrap gap-1.5">
                                        {lastIntent.research_result.source_domains.map((domain, i) => (
                                            <span key={i} className="px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-300 text-[10px] font-medium border border-emerald-500/20">
                                                🌐 {domain}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {lastIntent.research_result.key_terms?.length > 0 && (
                                <div className="flex flex-wrap gap-1.5">
                                    {lastIntent.research_result.key_terms.slice(0, 6).map((term, i) => (
                                        <span key={i} className="px-2 py-0.5 rounded-md bg-cyan-500/10 text-cyan-300 text-[10px] font-medium">
                                            {term}
                                        </span>
                                    ))}
                                </div>
                            )}
                            <div className="flex items-center gap-4 text-[10px] text-[#525252]">
                                {lastIntent.research_result.source && (
                                    <span>Source: {lastIntent.research_result.source}</span>
                                )}
                                {lastIntent.research_result.word_count > 0 && (
                                    <span>{lastIntent.research_result.word_count} words</span>
                                )}
                                {lastIntent.research_result.elapsed_ms > 0 && (
                                    <span>{Math.round(lastIntent.research_result.elapsed_ms)}ms</span>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Security Intent Result (non-research) */}
                    {lastIntent && !hasResearchResult && (
                        <div className="p-3 rounded-lg bg-[#171717] border border-white/[0.04]">
                            <div className="flex items-center justify-between mb-2">
                                <p className="text-xs text-[#525252] uppercase tracking-wider">Intent</p>
                                <span className={cn(
                                    "text-xs font-medium",
                                    getIntentStatusColor(lastIntent.status)
                                )}>
                                    {lastIntent.status}
                                </span>
                            </div>
                            <p className="text-sm font-medium text-[#FAFAFA]">
                                {lastIntent.intent_type.replace(/_/g, " ")}
                            </p>
                            {lastIntent.extracted_value && (
                                <p className="text-xs text-[#A3A3A3] mt-1">
                                    Value: {lastIntent.extracted_value}
                                </p>
                            )}
                            {lastIntent.block_reason && (
                                <p className="text-xs text-red-400 mt-1">
                                    ⚠️ {lastIntent.block_reason}
                                </p>
                            )}
                            <div className="flex items-center gap-2 mt-2">
                                <div className="h-1 flex-1 bg-[#262626] rounded-full overflow-hidden">
                                    <div
                                        className={cn(
                                            "h-full rounded-full",
                                            lastIntent.status === "PARSED" ? "bg-emerald-500" : "bg-red-500"
                                        )}
                                        style={{ width: `${lastIntent.confidence * 100}%` }}
                                    />
                                </div>
                                <span className="text-xs text-[#525252]">
                                    {Math.round(lastIntent.confidence * 100)}%
                                </span>
                            </div>
                        </div>
                    )}

                    {/* Language Hint */}
                    <p className="text-xs text-[#404040] text-center">
                        {isResearchMode
                            ? language === "EN"
                                ? "Try: \"What is DNS?\" or \"Explain encryption\""
                                : "Try: \"DNS kya hai?\" or \"Encryption samjhao\""
                            : language === "EN"
                                ? "Try: \"set target example.com\" or \"find targets\""
                                : "Try: \"mera target example.com hai\" or \"targets dhundo\""
                        }
                    </p>
                </div>
            )}

            {/* Voice Cannot Execute Warning */}
            <p className="text-xs text-[#404040] text-center">
                🔒 Voice can query & set targets, but CANNOT approve execution
                {isResearchMode && " • Research mode is isolated from security AI"}
            </p>
        </div>
    )
}
