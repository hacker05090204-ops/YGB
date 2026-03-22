"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  BookOpen,
  Globe,
  Loader2,
  Mic,
  MicOff,
  Search,
  Shield,
  Volume2,
  VolumeX,
} from "lucide-react"

import { credentialedFetch } from "@/lib/auth-token"
import { getApiBase } from "@/lib/ygb-api"
import { cn } from "@/lib/utils"

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

interface OfflineSTTStatus {
  dataset?: {
    status?: string
    sample_count?: number
    total_duration_hours?: number
    training_ready?: boolean
  }
  model?: {
    status?: string
    parameter_millions?: number
  }
}

type LanguageType = "EN" | "HI"

const TARGET_SAMPLE_RATE = 16000

function mergeAudioChunks(chunks: Float32Array[]): Float32Array {
  const totalLength = chunks.reduce((acc, chunk) => acc + chunk.length, 0)
  const merged = new Float32Array(totalLength)
  let offset = 0
  for (const chunk of chunks) {
    merged.set(chunk, offset)
    offset += chunk.length
  }
  return merged
}

function downsampleBuffer(
  buffer: Float32Array,
  inputSampleRate: number,
  outputSampleRate: number
): Float32Array {
  if (outputSampleRate >= inputSampleRate) {
    return buffer
  }
  const ratio = inputSampleRate / outputSampleRate
  const newLength = Math.max(1, Math.round(buffer.length / ratio))
  const result = new Float32Array(newLength)
  let offsetResult = 0
  let offsetBuffer = 0

  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.min(
      buffer.length,
      Math.round((offsetResult + 1) * ratio)
    )
    let accum = 0
    let count = 0
    for (let i = offsetBuffer; i < nextOffsetBuffer; i += 1) {
      accum += buffer[i]
      count += 1
    }
    result[offsetResult] = count > 0 ? accum / count : 0
    offsetResult += 1
    offsetBuffer = nextOffsetBuffer
  }

  return result
}

function writeString(view: DataView, offset: number, value: string) {
  for (let i = 0; i < value.length; i += 1) {
    view.setUint8(offset + i, value.charCodeAt(i))
  }
}

function encodeWav(samples: Float32Array, sampleRate: number): Uint8Array {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)

  writeString(view, 0, "RIFF")
  view.setUint32(4, 36 + samples.length * 2, true)
  writeString(view, 8, "WAVE")
  writeString(view, 12, "fmt ")
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeString(view, 36, "data")
  view.setUint32(40, samples.length * 2, true)

  let offset = 44
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
    offset += 2
  }

  return new Uint8Array(buffer)
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = ""
  const chunkSize = 0x8000
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize)
    binary += String.fromCharCode(...chunk)
  }
  return btoa(binary)
}

function getIntentStatusColor(status: VoiceInputStatusType) {
  switch (status) {
    case "PARSED":
      return "text-emerald-400"
    case "INVALID":
      return "text-amber-400"
    case "REJECTED":
      return "text-red-400"
    case "BLOCKED":
      return "text-red-500"
    default:
      return "text-[#525252]"
  }
}

export function VoiceControls({
  onVoiceInput,
  lastIntent,
  isProcessing = false,
  voiceMode = "SECURITY",
  onModeChange,
  className,
}: VoiceControlsProps) {
  const [voiceEnabled, setVoiceEnabled] = useState(false)
  const [speakerEnabled, setSpeakerEnabled] = useState(true)
  const [language, setLanguage] = useState<LanguageType>("EN")
  const [isListening, setIsListening] = useState(false)
  const [transcript, setTranscript] = useState("")
  const [sampleStatus, setSampleStatus] = useState("")
  const [offlineSttStatus, setOfflineSttStatus] = useState<OfflineSTTStatus | null>(null)

  const recognitionRef = useRef<any>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const audioChunksRef = useRef<Float32Array[]>([])
  const sampleRateRef = useRef<number>(TARGET_SAMPLE_RATE)
  const offlineGrabberSessionRef = useRef<string>("")

  const isResearchMode = voiceMode === "RESEARCH"
  const hasResearchResult =
    lastIntent?.research_result && lastIntent.intent_type === "RESEARCH_QUERY"

  const getOfflineGrabberSessionId = useCallback(() => {
    if (!offlineGrabberSessionRef.current) {
      const randomPart =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID().replace(/-/g, "").slice(0, 16)
          : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`
      offlineGrabberSessionRef.current = `BROWSER-GRAB-${randomPart.toUpperCase()}`
    }
    return offlineGrabberSessionRef.current
  }, [])

  const refreshSttStatus = useCallback(async () => {
    try {
      const res = await credentialedFetch(`${getApiBase()}/api/voice/stt/status`)
      if (!res.ok) {
        return
      }
      const data = (await res.json()) as OfflineSTTStatus
      setOfflineSttStatus(data)
    } catch {
      setOfflineSttStatus(null)
    }
  }, [])

  const cleanupAudioCapture = useCallback(async () => {
    try {
      processorRef.current?.disconnect()
      sourceRef.current?.disconnect()
    } catch {
      // Ignore teardown issues.
    }

    if (mediaStreamRef.current) {
      for (const track of mediaStreamRef.current.getTracks()) {
        track.stop()
      }
    }

    if (audioContextRef.current) {
      try {
        await audioContextRef.current.close()
      } catch {
        // Ignore teardown issues.
      }
    }

    processorRef.current = null
    sourceRef.current = null
    mediaStreamRef.current = null
    audioContextRef.current = null
  }, [])

  const finishAudioCapture = useCallback(async (): Promise<Uint8Array | null> => {
    const chunks = audioChunksRef.current
    const inputSampleRate = sampleRateRef.current
    audioChunksRef.current = []
    await cleanupAudioCapture()

    if (!chunks.length) {
      return null
    }

    const merged = mergeAudioChunks(chunks)
    if (!merged.length) {
      return null
    }

    const downsampled = downsampleBuffer(
      merged,
      inputSampleRate,
      TARGET_SAMPLE_RATE
    )
    if (!downsampled.length) {
      return null
    }

    return encodeWav(downsampled, TARGET_SAMPLE_RATE)
  }, [cleanupAudioCapture])

  const uploadTrainingSample = useCallback(async (
    finalTranscript: string,
    wavBytes: Uint8Array | null
  ) => {
    const cleanedTranscript = finalTranscript.trim()
    if (!cleanedTranscript || !wavBytes || wavBytes.length === 0) {
      return
    }

    setSampleStatus("Saving offline STT sample...")
    try {
      const res = await credentialedFetch(`${getApiBase()}/api/voice/stt/sample`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          audio_wav_b64: bytesToBase64(wavBytes),
          transcript: cleanedTranscript,
          device_id: "browser",
          language: language === "EN" ? "en-US" : "hi-IN",
          provider: "BROWSER_WEBSPEECH",
          session_id: getOfflineGrabberSessionId(),
        }),
      })
      const data = await res.json().catch(() => null)
      if (!res.ok || !data) {
        setSampleStatus("Offline STT sample upload failed.")
        return
      }
      setOfflineSttStatus((current) => ({
        ...(current || {}),
        dataset: data.dataset || current?.dataset,
        model: current?.model,
      }))
      setSampleStatus(
        data.accepted
          ? "Offline STT sample saved for local training."
          : `Offline STT sample rejected: ${data.reason || "unknown"}`
      )
      void refreshSttStatus()
    } catch {
      setSampleStatus("Offline STT sample upload failed.")
    }
  }, [getOfflineGrabberSessionId, language, refreshSttStatus])

  const startAudioCapture = useCallback(async () => {
    if (typeof window === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setSampleStatus("Browser microphone capture is not available.")
      return false
    }

    try {
      const AudioContextCtor =
        window.AudioContext ||
        (window as typeof window & { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext

      if (!AudioContextCtor) {
        setSampleStatus("Web Audio capture is not available in this browser.")
        return false
      }

      audioChunksRef.current = []
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      })
      const context = new AudioContextCtor()
      const source = context.createMediaStreamSource(stream)
      const processor = context.createScriptProcessor(4096, 1, 1)

      sampleRateRef.current = context.sampleRate
      processor.onaudioprocess = (event: AudioProcessingEvent) => {
        const input = event.inputBuffer.getChannelData(0)
        audioChunksRef.current.push(new Float32Array(input))
      }

      source.connect(processor)
      processor.connect(context.destination)

      mediaStreamRef.current = stream
      audioContextRef.current = context
      sourceRef.current = source
      processorRef.current = processor
      setSampleStatus("Recording sample for offline STT...")
      return true
    } catch {
      setSampleStatus("Microphone access was denied or is unavailable.")
      return false
    }
  }, [])

  useEffect(() => {
    return () => {
      recognitionRef.current?.abort()
      recognitionRef.current = null
      void cleanupAudioCapture()
    }
  }, [cleanupAudioCapture])

  const toggleVoice = () => {
    if (!voiceEnabled) {
      const speechWindow = window as typeof window & {
        SpeechRecognition?: any
        webkitSpeechRecognition?: any
      }
      const SpeechRecognition = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition

      if (!SpeechRecognition) {
        setSampleStatus("Speech recognition is not available in this browser.")
        return
      }

      recognitionRef.current = new SpeechRecognition()
      recognitionRef.current.continuous = false
      recognitionRef.current.interimResults = true
      recognitionRef.current.lang = language === "EN" ? "en-US" : "hi-IN"

      recognitionRef.current.onresult = (event: any) => {
        const current = event.resultIndex
        const result = event.results[current]
        const text = String(result[0]?.transcript || "")
        setTranscript(text)

        if (result.isFinal) {
          onVoiceInput?.(text)
          setIsListening(false)
          void finishAudioCapture().then((wavBytes) =>
            uploadTrainingSample(text, wavBytes)
          )
        }
      }

      recognitionRef.current.onend = () => {
        setIsListening(false)
        void finishAudioCapture()
      }

      recognitionRef.current.onerror = () => {
        setSampleStatus("Speech recognition stopped before a final transcript.")
        setIsListening(false)
        void finishAudioCapture()
      }

      setVoiceEnabled(true)
      void refreshSttStatus()
      return
    }

    setVoiceEnabled(false)
    recognitionRef.current?.abort()
    recognitionRef.current = null
    setIsListening(false)
    void finishAudioCapture()
  }

  const startListening = async () => {
    if (!voiceEnabled || !recognitionRef.current) {
      return
    }

    recognitionRef.current.lang = language === "EN" ? "en-US" : "hi-IN"
    setTranscript("")
    setSampleStatus("")
    setIsListening(true)
    await startAudioCapture()

    try {
      recognitionRef.current.start()
    } catch {
      setIsListening(false)
      setSampleStatus("Voice recognition could not start.")
      void finishAudioCapture()
    }
  }

  const stopListening = () => {
    recognitionRef.current?.stop()
    setIsListening(false)
    void finishAudioCapture()
  }

  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex items-center gap-3 flex-wrap">
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

        <div
          className={cn(
            "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider",
            isResearchMode
              ? "bg-cyan-500/10 text-cyan-400 border border-cyan-500/20"
              : "bg-violet-500/10 text-violet-400 border border-violet-500/20"
          )}
        >
          <div
            className={cn(
              "w-1.5 h-1.5 rounded-full",
              isResearchMode ? "bg-cyan-400" : "bg-violet-400"
            )}
          />
          {isResearchMode ? "Research Mode" : "Security Mode"}
        </div>

        <div className="flex-1" />

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

        <button
          onClick={() => setSpeakerEnabled(!speakerEnabled)}
          className={cn(
            "flex items-center justify-center w-10 h-10 rounded-xl transition-all duration-200",
            speakerEnabled
              ? "bg-[#262626] text-[#FAFAFA]"
              : "bg-[#171717] text-[#404040]"
          )}
        >
          {speakerEnabled ? (
            <Volume2 className="w-4 h-4" />
          ) : (
            <VolumeX className="w-4 h-4" />
          )}
        </button>
      </div>

      {voiceEnabled && (
        <div
          className={cn(
            "p-4 rounded-xl bg-[#0A0A0A] border space-y-3",
            isResearchMode ? "border-cyan-500/20" : "border-violet-500/20"
          )}
        >
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

          {transcript && (
            <div className="p-3 rounded-lg bg-[#171717] border border-white/[0.04]">
              <p className="text-xs text-[#525252] uppercase tracking-wider mb-1">
                You said:
              </p>
              <p className="text-sm text-[#FAFAFA]">"{transcript}"</p>
            </div>
          )}

          {sampleStatus && (
            <div className="p-3 rounded-lg bg-[#111827] border border-cyan-500/10">
              <p className="text-xs text-cyan-300">{sampleStatus}</p>
            </div>
          )}

          {offlineSttStatus && (
            <div className="p-3 rounded-lg bg-[#171717] border border-white/[0.04] space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-xs text-[#525252] uppercase tracking-wider">
                  Offline STT
                </p>
                <span
                  className={cn(
                    "text-xs font-medium",
                    offlineSttStatus.model?.status === "AVAILABLE"
                      ? "text-emerald-400"
                      : "text-amber-300"
                  )}
                >
                  {offlineSttStatus.model?.status || "UNKNOWN"}
                </span>
              </div>
              <p className="text-sm text-[#FAFAFA]">
                {(offlineSttStatus.dataset?.status || "EMPTY").replace(/_/g, " ")} •{" "}
                {offlineSttStatus.dataset?.sample_count || 0} samples
              </p>
              <p className="text-xs text-[#A3A3A3]">
                {(offlineSttStatus.model?.parameter_millions || 0).toFixed(2)}M params •{" "}
                {(offlineSttStatus.dataset?.total_duration_hours || 0).toFixed(2)}h audio
              </p>
              <p className="text-xs text-[#A3A3A3]">
                {offlineSttStatus.dataset?.training_ready
                  ? "Local training threshold reached."
                  : "Collecting real audio for the local model."}
              </p>
            </div>
          )}

          {hasResearchResult && lastIntent?.research_result && (
            <div className="p-4 rounded-xl bg-gradient-to-br from-cyan-500/5 to-cyan-500/[0.02] border border-cyan-500/20 space-y-3">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20">
                <span className="text-amber-400 text-[10px] font-semibold uppercase tracking-wider">
                  Research mode is informational only.
                </span>
              </div>

              <div className="flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-cyan-400" />
                <p className="text-xs text-cyan-400 font-semibold uppercase tracking-wider">
                  Research Answer
                </p>
              </div>
              {lastIntent.research_result.title && (
                <p className="text-sm font-medium text-[#FAFAFA]">
                  {lastIntent.research_result.title}
                </p>
              )}
              <p className="text-sm text-[#D4D4D4] leading-relaxed">
                {lastIntent.research_result.summary}
              </p>

              {lastIntent.research_result.confidence > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-[#525252] uppercase tracking-wider">
                    Confidence
                  </span>
                  <div className="h-1.5 flex-1 bg-[#262626] rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full bg-cyan-500"
                      style={{
                        width: `${Math.round(
                          lastIntent.research_result.confidence * 100
                        )}%`,
                      }}
                    />
                  </div>
                  <span className="text-[10px] text-cyan-400 font-medium">
                    {Math.round(lastIntent.research_result.confidence * 100)}%
                  </span>
                </div>
              )}

              {lastIntent.research_result.source_domains?.length > 0 && (
                <div className="space-y-1">
                  <span className="text-[10px] text-[#525252] uppercase tracking-wider">
                    Verified Sources
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {lastIntent.research_result.source_domains.map((domain, index) => (
                      <span
                        key={index}
                        className="px-2 py-0.5 rounded-md bg-emerald-500/10 text-emerald-300 text-[10px] font-medium border border-emerald-500/20"
                      >
                        {domain}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {lastIntent.research_result.key_terms?.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {lastIntent.research_result.key_terms.slice(0, 6).map((term, index) => (
                    <span
                      key={index}
                      className="px-2 py-0.5 rounded-md bg-cyan-500/10 text-cyan-300 text-[10px] font-medium"
                    >
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

          {lastIntent && !hasResearchResult && (
            <div className="p-3 rounded-lg bg-[#171717] border border-white/[0.04]">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs text-[#525252] uppercase tracking-wider">Intent</p>
                <span
                  className={cn("text-xs font-medium", getIntentStatusColor(lastIntent.status))}
                >
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
                  Warning: {lastIntent.block_reason}
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

          <p className="text-xs text-[#404040] text-center">
            {isResearchMode
              ? language === "EN"
                ? 'Try: "What is DNS?" or "Explain encryption"'
                : 'Try: "DNS kya hai?" or "Encryption samjhao"'
              : language === "EN"
                ? 'Try: "set target example.com" or "find targets"'
                : 'Try: "mera target example.com hai" or "targets dhundo"'}
          </p>
        </div>
      )}

      <p className="text-xs text-[#404040] text-center">
        Voice can query and set targets, but cannot approve execution.
        {isResearchMode && " Research mode stays isolated from security AI."}
      </p>
    </div>
  )
}
