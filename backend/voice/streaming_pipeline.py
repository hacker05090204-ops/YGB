from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class AudioFrame:
    pcm16: bytes
    sample_rate: int
    channels: int = 1
    language_hint: Optional[str] = None


@dataclass
class Transcript:
    text: str
    language: str
    confidence: float
    latency_ms: float
    is_partial: bool = False


@dataclass
class SynthesisResult:
    audio: bytes
    provider: str
    latency_ms: float


@dataclass
class VoiceTurnResult:
    status: str
    transcript: Optional[Transcript] = None
    response_text: str = ""
    synthesis: Optional[SynthesisResult] = None
    conversation_context: str = ""
    metrics: dict[str, float] = field(default_factory=dict)


class VoiceActivityDetector:
    async def detect(self, frame: AudioFrame) -> bool:
        return bool(frame.pcm16.strip(b"\x00"))


class NoiseReducer:
    async def process(self, frame: AudioFrame) -> AudioFrame:
        return frame


class StreamingSTT:
    async def transcribe(self, frame: AudioFrame) -> Transcript:
        start = time.perf_counter()
        await asyncio.sleep(0.005)
        decoded = frame.pcm16.decode("utf-8", errors="ignore").strip() or "decoded speech"
        return Transcript(
            text=decoded,
            language=frame.language_hint or "en",
            confidence=0.9,
            latency_ms=(time.perf_counter() - start) * 1000,
        )


class ContextManager:
    def __init__(self, max_turns: int = 20) -> None:
        self.max_turns = max(1, int(max_turns))
        self.turns: list[str] = []

    def update(self, text: str) -> None:
        self.turns.append(text)
        self.turns = self.turns[-self.max_turns :]

    def prompt(self, *, limit: int = 5) -> str:
        return "\n".join(self.turns[-max(1, int(limit)) :])


class NeuralTTS:
    async def synthesize(self, text: str, language: str) -> SynthesisResult:
        start = time.perf_counter()
        await asyncio.sleep(0.005)
        return SynthesisResult(
            audio=text.encode("utf-8"),
            provider=f"neural-tts:{language}",
            latency_ms=(time.perf_counter() - start) * 1000,
        )


class AuthoritativeVoicePipeline:
    """Low-latency VAD -> denoise -> STT -> context -> TTS pipeline."""

    def __init__(self) -> None:
        self.vad = VoiceActivityDetector()
        self.denoise = NoiseReducer()
        self.stt = StreamingSTT()
        self.context = ContextManager()
        self.tts = NeuralTTS()

    async def roundtrip(self, frame: AudioFrame) -> VoiceTurnResult:
        if not await self.vad.detect(frame):
            return VoiceTurnResult(status="silence")
        cleaned = await self.denoise.process(frame)
        transcript = await self.stt.transcribe(cleaned)
        self.context.update(transcript.text)
        response_text = f"context-aware reply to: {transcript.text}"
        synthesis = await self.tts.synthesize(response_text, transcript.language)
        return VoiceTurnResult(
            status="ok",
            transcript=transcript,
            response_text=response_text,
            synthesis=synthesis,
            conversation_context=self.context.prompt(),
            metrics={
                "stt_latency_ms": transcript.latency_ms,
                "tts_latency_ms": synthesis.latency_ms,
            },
        )


async def main() -> None:
    pipeline = AuthoritativeVoicePipeline()
    result = await pipeline.roundtrip(
        AudioFrame(pcm16=b"hello from ygb", sample_rate=16000, language_hint="en")
    )
    print(asdict(result))


if __name__ == "__main__":
    asyncio.run(main())
