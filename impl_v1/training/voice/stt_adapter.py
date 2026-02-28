"""
STT Adapter Chain — Resilient Speech-to-Text with circuit breaker.

Provider chain (reordered per constraints):
  1. Primary: Local Conformer-CTC model (in-project, no external deps)
  2. Degraded: Browser WebSpeech API (via WebSocket relay)
  3. Optional: Whisper API (only with WHISPER_API_KEY)
  4. Optional: Google STT (only with GOOGLE_STT_CREDENTIALS)

HARD CONSTRAINTS:
  - No whisper.cpp
  - No WHISPER_API_KEY or GOOGLE_STT_CREDENTIALS required for core path
  - STT must be own in-project model service
"""

import hashlib
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Optional, List, Dict, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# TYPES
# =============================================================================

class STTProvider(Enum):
    """Available STT providers."""
    LOCAL_CONFORMER = "LOCAL_CONFORMER"
    WHISPER = "WHISPER"
    GOOGLE_STT = "GOOGLE_STT"
    BROWSER_WEBSPEECH = "BROWSER_WEBSPEECH"


class STTStatus(Enum):
    """Provider status."""
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"


@dataclass(frozen=True)
class TranscriptResult:
    """Result of a transcription attempt."""
    transcript_id: str
    text: str
    confidence: float
    provider: STTProvider
    latency_ms: float
    timestamp: str
    is_partial: bool = False
    language: str = "en"
    word_timestamps: tuple = ()


@dataclass(frozen=True)
class STTHealthReport:
    """Health report for the STT subsystem."""
    active_provider: STTProvider
    provider_status: Dict[str, str]
    total_transcriptions: int
    avg_confidence: float
    avg_latency_ms: float
    circuit_breaker_state: Dict[str, str]
    timestamp: str


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================

class CircuitBreaker:
    """Circuit breaker for STT providers.

    Opens after `failure_threshold` consecutive failures.
    Half-opens after `recovery_timeout_s` seconds to test recovery.
    """

    def __init__(self, name: str, failure_threshold: int = 3,
                 recovery_timeout_s: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self._consecutive_failures = 0
        self._state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._last_failure_time: Optional[float] = None

    @property
    def state(self) -> str:
        if self._state == "OPEN" and self._last_failure_time:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.recovery_timeout_s:
                self._state = "HALF_OPEN"
        return self._state

    @property
    def is_available(self) -> bool:
        return self.state in ("CLOSED", "HALF_OPEN")

    def record_success(self):
        self._consecutive_failures = 0
        self._state = "CLOSED"

    def record_failure(self):
        self._consecutive_failures += 1
        self._last_failure_time = time.time()
        if self._consecutive_failures >= self.failure_threshold:
            self._state = "OPEN"
            logger.warning(
                f"[STT] Circuit breaker OPEN for {self.name} "
                f"after {self._consecutive_failures} failures"
            )

    def reset(self):
        self._consecutive_failures = 0
        self._state = "CLOSED"
        self._last_failure_time = None


# =============================================================================
# STT ADAPTERS
# =============================================================================

class BaseSTTAdapter:
    """Base class for STT adapters."""

    provider: STTProvider = STTProvider.LOCAL_CONFORMER
    timeout_s: float = 5.0

    def __init__(self):
        self.circuit_breaker = CircuitBreaker(self.provider.value)

    def transcribe(self, audio_bytes: bytes) -> Optional[TranscriptResult]:
        """Transcribe audio bytes. Returns None on failure."""
        raise NotImplementedError

    def is_available(self) -> bool:
        return self.circuit_breaker.is_available

    def get_status(self) -> str:
        return self.circuit_breaker.state


class LocalConformerSTTAdapter(BaseSTTAdapter):
    """Primary: In-project Conformer-CTC model.

    No external API dependency. Reports DEGRADED if model untrained.
    """

    provider = STTProvider.LOCAL_CONFORMER

    def __init__(self):
        super().__init__()
        self._service = None
        self._init_attempted = False

    def _ensure_service(self):
        if self._service is None and not self._init_attempted:
            self._init_attempted = True
            try:
                from impl_v1.training.voice.stt_model import get_local_stt_service
                self._service = get_local_stt_service()
            except Exception as e:
                logger.warning(f"[STT] Local Conformer init failed: {e}")
                self._service = None

    def transcribe(self, audio_bytes: bytes) -> Optional[TranscriptResult]:
        if not self.circuit_breaker.is_available:
            return None

        self._ensure_service()
        if self._service is None:
            self.circuit_breaker.record_failure()
            return None

        start = time.time()
        try:
            result = self._service.transcribe(audio_bytes)
            elapsed = (time.time() - start) * 1000

            if result.text or result.confidence > 0:
                self.circuit_breaker.record_success()
                return TranscriptResult(
                    transcript_id=f"TR-{uuid.uuid4().hex[:12].upper()}",
                    text=result.text,
                    confidence=result.confidence,
                    provider=self.provider,
                    latency_ms=elapsed,
                    timestamp=datetime.now(UTC).isoformat(),
                    language="en",
                )
            else:
                # Model returned empty — likely untrained
                self.circuit_breaker.record_failure()
                return None

        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.warning(f"[STT] Local Conformer failed: {e}")
            return None

    def get_status(self) -> str:
        self._ensure_service()
        if self._service and self._service._model_loaded:
            return "CLOSED"  # Available
        return "DEGRADED"


class WhisperSTTAdapter(BaseSTTAdapter):
    """TEST_ONLY: Whisper API — NOT for production core path.

    Only loaded when YGB_VOICE_TEST_MODE=true.
    Production uses LocalConformerSTTAdapter exclusively.
    """

    TEST_ONLY = True

    provider = STTProvider.WHISPER

    def __init__(self):
        super().__init__()
        self._api_key = os.environ.get("WHISPER_API_KEY", "")
        self._endpoint = os.environ.get(
            "WHISPER_API_ENDPOINT",
            "https://api.openai.com/v1/audio/transcriptions"
        )

    def transcribe(self, audio_bytes: bytes) -> Optional[TranscriptResult]:
        if not self.circuit_breaker.is_available:
            return None

        start = time.time()
        try:
            if not self._api_key:
                raise ConnectionError("WHISPER_API_KEY not configured")

            # PRODUCTION: HTTP POST to Whisper API with audio_bytes
            raise ConnectionError("Whisper API call not yet wired")

        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.warning(f"[STT] Whisper failed: {e}")
            return None

    def is_available(self) -> bool:
        """Only available if API key is configured."""
        return bool(self._api_key) and self.circuit_breaker.is_available


class GoogleSTTAdapter(BaseSTTAdapter):
    """TEST_ONLY: Google Cloud STT — NOT for production core path.

    Only loaded when YGB_VOICE_TEST_MODE=true.
    Production uses LocalConformerSTTAdapter exclusively.
    """

    TEST_ONLY = True

    provider = STTProvider.GOOGLE_STT

    def __init__(self):
        super().__init__()
        self._credentials = os.environ.get("GOOGLE_STT_CREDENTIALS", "")

    def transcribe(self, audio_bytes: bytes) -> Optional[TranscriptResult]:
        if not self.circuit_breaker.is_available:
            return None

        start = time.time()
        try:
            if not self._credentials:
                raise ConnectionError("GOOGLE_STT_CREDENTIALS not configured")

            raise ConnectionError("Google STT call not yet wired")

        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.warning(f"[STT] Google STT failed: {e}")
            return None

    def is_available(self) -> bool:
        """Only available if credentials are configured."""
        return bool(self._credentials) and self.circuit_breaker.is_available


class BrowserWebSpeechAdapter(BaseSTTAdapter):
    """Degraded fallback: Browser WebSpeech API relay via WebSocket."""

    provider = STTProvider.BROWSER_WEBSPEECH

    def __init__(self):
        super().__init__()
        self._relay_active = False

    def transcribe(self, audio_bytes: bytes) -> Optional[TranscriptResult]:
        """Browser STT doesn't use audio bytes — it receives transcripts via WS relay."""
        return None

    def create_transcript_from_relay(self, text: str,
                                      confidence: float = 0.7) -> TranscriptResult:
        """Create transcript from browser WebSpeech relay data."""
        return TranscriptResult(
            transcript_id=f"TR-{uuid.uuid4().hex[:12].upper()}",
            text=text,
            confidence=confidence,
            provider=STTProvider.BROWSER_WEBSPEECH,
            latency_ms=0.0,
            timestamp=datetime.now(UTC).isoformat(),
            language="en",
        )

    def is_available(self) -> bool:
        return True  # Always available as degraded fallback


# =============================================================================
# STT ADAPTER CHAIN
# =============================================================================

class STTAdapterChain:
    """Resilient STT with automatic failover.

    Production chain (default):
      1. Local Conformer-CTC (in-project, no external deps)
      2. Browser WebSpeech (degraded fallback)

    Test-only chain (YGB_VOICE_TEST_MODE=true):
      Also includes Whisper API and Google STT adapters.

    HARD CONSTRAINT: No WHISPER_API_KEY or GOOGLE_STT_CREDENTIALS
    required for production core path.
    """

    def __init__(self):
        # Production: local-only providers
        self._adapters: List[BaseSTTAdapter] = [
            LocalConformerSTTAdapter(),
            BrowserWebSpeechAdapter(),
        ]
        # Test mode: also include external API adapters
        _test_mode = os.environ.get("YGB_VOICE_TEST_MODE", "").lower() == "true"
        if _test_mode:
            self._adapters.append(WhisperSTTAdapter())
            self._adapters.append(GoogleSTTAdapter())
            logger.info("[STT] TEST_MODE: Whisper + Google adapters loaded")
        else:
            logger.info("[STT] Production mode: local-only STT chain")

        self._test_mode = _test_mode
        self._total_transcriptions = 0
        self._total_confidence = 0.0
        self._total_latency_ms = 0.0
        self._active_provider: Optional[STTProvider] = None

    @property
    def active_provider(self) -> Optional[STTProvider]:
        for adapter in self._adapters:
            if adapter.is_available():
                return adapter.provider
        return None

    def transcribe(self, audio_bytes: bytes) -> Optional[TranscriptResult]:
        """Try each provider in order until one succeeds."""
        for adapter in self._adapters:
            if not adapter.is_available():
                continue

            result = adapter.transcribe(audio_bytes)
            if result:
                adapter.circuit_breaker.record_success()
                self._active_provider = adapter.provider
                self._total_transcriptions += 1
                self._total_confidence += result.confidence
                self._total_latency_ms += result.latency_ms
                return result

        logger.error("[STT] All providers failed")
        return None

    def submit_browser_transcript(self, text: str,
                                   confidence: float = 0.7) -> TranscriptResult:
        """Accept transcript from browser WebSpeech relay."""
        browser = self._adapters[1]  # BrowserWebSpeechAdapter is second
        assert isinstance(browser, BrowserWebSpeechAdapter)
        result = browser.create_transcript_from_relay(text, confidence)
        self._active_provider = STTProvider.BROWSER_WEBSPEECH
        self._total_transcriptions += 1
        self._total_confidence += result.confidence
        self._total_latency_ms += result.latency_ms
        return result

    def get_health(self) -> STTHealthReport:
        avg_conf = (self._total_confidence / self._total_transcriptions
                    if self._total_transcriptions > 0 else 0.0)
        avg_lat = (self._total_latency_ms / self._total_transcriptions
                   if self._total_transcriptions > 0 else 0.0)

        return STTHealthReport(
            active_provider=self.active_provider or STTProvider.BROWSER_WEBSPEECH,
            provider_status={
                a.provider.value: a.get_status() for a in self._adapters
            },
            total_transcriptions=self._total_transcriptions,
            avg_confidence=round(avg_conf, 3),
            avg_latency_ms=round(avg_lat, 1),
            circuit_breaker_state={
                a.provider.value: a.circuit_breaker.state for a in self._adapters
            },
            timestamp=datetime.now(UTC).isoformat(),
        )

    def reset_all(self):
        """Reset all circuit breakers (for testing)."""
        for adapter in self._adapters:
            adapter.circuit_breaker.reset()
        self._total_transcriptions = 0
        self._total_confidence = 0.0
        self._total_latency_ms = 0.0


# =============================================================================
# MODULE-LEVEL HELPERS
# =============================================================================

_chain = STTAdapterChain()


def get_stt_chain() -> STTAdapterChain:
    return _chain


def get_stt_status() -> dict:
    """Get STT subsystem status for health endpoints."""
    health = _chain.get_health()
    local_adapter = _chain._adapters[0] if _chain._adapters else None
    local_status = local_adapter.get_status() if local_adapter else "BLOCKED"

    return {
        "stt_status": "STT_READY" if local_status == "CLOSED" else "DEGRADED",
        "active_provider": health.active_provider.value,
        "local_only": not _chain._test_mode,
        "external_deps": [],  # No external deps in production
        "provider_status": health.provider_status,
        "total_transcriptions": health.total_transcriptions,
        "avg_confidence": health.avg_confidence,
        "circuit_breaker_state": health.circuit_breaker_state,
        "no_whisper_dependency": True,
        "no_google_stt_dependency": True,
        "timestamp": health.timestamp,
    }
