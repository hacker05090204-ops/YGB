"use client"

import { useState, useRef, useEffect } from "react"
import { cn } from "@/lib/utils"
import { Mic, MicOff, Volume2, VolumeX, Globe, Loader2 } from "lucide-react"

// Voice intent types from G12
export type VoiceIntentType =
    | "SET_TARGET"
    | "SET_SCOPE"
    | "QUERY_STATUS"
    | "QUERY_PROGRESS"
    | "FIND_TARGETS"
    | "SCREEN_TAKEOVER"
    | "REPORT_HELP"
    | "UNKNOWN"

export type VoiceInputStatusType = "PARSED" | "INVALID" | "REJECTED" | "BLOCKED"

export interface VoiceIntent {
    intent_id: string
    intent_type: VoiceIntentType
    raw_text: string
    extracted_value: string | null
    confidence: number
    status: VoiceInputStatusType
    block_reason: string | null
    timestamp: string
}

interface VoiceControlsProps {
    onVoiceInput?: (text: string) => void
    lastIntent?: VoiceIntent | null
    isProcessing?: boolean
    className?: string
}

type LanguageType = "EN" | "HI"

export function VoiceControls({
    onVoiceInput,
    lastIntent,
    isProcessing = false,
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

    return (
        <div className={cn("space-y-4", className)}>
            {/* Main Controls Row */}
            <div className="flex items-center gap-3">
                {/* Voice Toggle */}
                <button
                    onClick={toggleVoice}
                    className={cn(
                        "flex items-center gap-2 px-4 py-2 rounded-xl font-medium transition-all duration-200",
                        voiceEnabled
                            ? "bg-violet-500 text-white shadow-[0_0_20px_rgba(139,92,246,0.3)]"
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
                <div className="p-4 rounded-xl bg-[#0A0A0A] border border-violet-500/20 space-y-3">
                    {/* Mic Button */}
                    <button
                        onClick={isListening ? stopListening : startListening}
                        disabled={isProcessing}
                        className={cn(
                            "w-full flex items-center justify-center gap-3 py-4 rounded-xl font-medium transition-all duration-200",
                            isListening
                                ? "bg-violet-500 text-white animate-pulse shadow-[0_0_30px_rgba(139,92,246,0.4)]"
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

                    {/* Last Intent Result */}
                    {lastIntent && (
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
                        {language === "EN"
                            ? "Try: \"set target example.com\" or \"find targets\""
                            : "Try: \"mera target example.com hai\" or \"targets dhundo\""
                        }
                    </p>
                </div>
            )}

            {/* Voice Cannot Execute Warning */}
            <p className="text-xs text-[#404040] text-center">
                🔒 Voice can query & set targets, but CANNOT approve execution
            </p>
        </div>
    )
}
