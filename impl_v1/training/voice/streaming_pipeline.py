from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from impl_v1.agents import AgentOrchestrator


@dataclass
class StreamingVoiceEvent:
    event_type: str
    payload: Dict[str, Any]


@dataclass
class StreamingVoiceSession:
    session_id: str
    transcript_chunks: List[str] = field(default_factory=list)
    audio_chunks: int = 0


class StreamingVoicePipeline:
    """Streaming STT -> agent reasoning -> streaming TTS facade."""

    def __init__(
        self,
        orchestrator: AgentOrchestrator,
        stt_adapter: Optional[Callable[[bytes], str]] = None,
        tts_adapter: Optional[Callable[[str], bytes]] = None,
    ):
        self.orchestrator = orchestrator
        self.stt_adapter = stt_adapter or self._default_stt
        self.tts_adapter = tts_adapter or self._default_tts

    def ingest_audio(self, session: StreamingVoiceSession, chunk: bytes) -> StreamingVoiceEvent:
        session.audio_chunks += 1
        transcript = self.stt_adapter(chunk)
        if transcript:
            session.transcript_chunks.append(transcript)
        return StreamingVoiceEvent("stt.partial", {"text": transcript, "audio_chunks": session.audio_chunks})

    def reason(self, session: StreamingVoiceSession, recipient: str = "voice-stream") -> StreamingVoiceEvent:
        full_text = " ".join(t for t in session.transcript_chunks if t).strip()
        response = self.orchestrator.send(
            sender="voice-pipeline",
            recipient=recipient,
            topic="voice.reasoning",
            payload={"session_id": session.session_id, "transcript": full_text},
        )
        return StreamingVoiceEvent("reasoning.output", response)

    def synthesize(self, text: str) -> StreamingVoiceEvent:
        audio = self.tts_adapter(text)
        return StreamingVoiceEvent("tts.chunk", {"audio": audio, "text": text})

    def stream_roundtrip(self, session: StreamingVoiceSession, chunk: bytes, recipient: str = "voice-stream") -> List[StreamingVoiceEvent]:
        partial = self.ingest_audio(session, chunk)
        reasoning = self.reason(session, recipient=recipient)
        tts = self.synthesize(reasoning.payload.get("text", ""))
        return [partial, reasoning, tts]

    def _default_stt(self, chunk: bytes) -> str:
        try:
            return chunk.decode("utf-8", errors="ignore").strip()
        except Exception:
            return ""

    def _default_tts(self, text: str) -> bytes:
        return text.encode("utf-8")
