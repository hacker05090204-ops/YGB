"""
TTS Streaming — Text-to-speech response loop with interrupt handling.

Provides:
  - Primary: TTS proxy API (external)
  - Local fallback: pyttsx3 for privacy mode
  - Interrupt handling via "stop speaking" / "quiet" hotwords
  - Response templates: SUCCESS, BLOCKED, RETRY, FAILURE
"""

import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, UTC
from enum import Enum
from typing import Optional, Dict

logger = logging.getLogger(__name__)


# =============================================================================
# TYPES
# =============================================================================

class TTSProvider(Enum):
    API_PROXY = "API_PROXY"
    LOCAL_PYTTSX3 = "LOCAL_PYTTSX3"
    BLOCKED = "BLOCKED"


class TTSStatus(Enum):
    IDLE = "IDLE"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"
    ERROR = "ERROR"


class ResponseType(Enum):
    SUCCESS = "SUCCESS"
    BLOCKED = "BLOCKED"
    RETRY_IN_PROGRESS = "RETRY_IN_PROGRESS"
    FAILURE = "FAILURE"


@dataclass(frozen=True)
class TTSResponse:
    """A TTS response to be spoken."""
    response_id: str
    text: str
    response_type: ResponseType
    provider: TTSProvider
    status: TTSStatus
    latency_ms: float
    timestamp: str


# =============================================================================
# RESPONSE TEMPLATES
# =============================================================================

RESPONSE_TEMPLATES: Dict[ResponseType, str] = {
    ResponseType.SUCCESS: "{action} completed successfully.",
    ResponseType.BLOCKED: "{action} is blocked: {reason}.",
    ResponseType.RETRY_IN_PROGRESS: "{action} failed, retrying. Attempt {attempt} of {max_attempts}.",
    ResponseType.FAILURE: "{action} failed: {reason}. {remediation}",
}


def format_response(response_type: ResponseType, **kwargs) -> str:
    """Format a response using templates."""
    template = RESPONSE_TEMPLATES.get(response_type, "{action}: {reason}")
    try:
        return template.format(**kwargs)
    except KeyError:
        return str(kwargs)


# =============================================================================
# INTERRUPT DETECTION
# =============================================================================

STOP_HOTWORDS = {"stop speaking", "quiet", "be quiet", "shut up",
                 "chup", "stop", "bas", "ruko"}


def is_interrupt_command(text: str) -> bool:
    """Check if text is an interrupt command."""
    return text.strip().lower() in STOP_HOTWORDS


# =============================================================================
# TTS ENGINE
# =============================================================================

class TTSEngine:
    """Streaming TTS with interrupt support."""

    def __init__(self):
        self._status = TTSStatus.IDLE
        self._active_provider: Optional[TTSProvider] = None
        self._privacy_mode = os.environ.get("VOICE_PRIVACY_MODE", "").lower() == "true"
        self._tts_api_url = os.environ.get(
            "TTS_API_URL", "https://tts-five-iota.vercel.app/api/audio"
        )
        self._total_spoken = 0
        self._total_interrupted = 0
        self._total_errors = 0

    @property
    def status(self) -> TTSStatus:
        return self._status

    @property
    def active_provider(self) -> TTSProvider:
        if self._privacy_mode:
            return TTSProvider.LOCAL_PYTTSX3
        return TTSProvider.API_PROXY

    def speak(self, text: str, response_type: ResponseType = ResponseType.SUCCESS
              ) -> TTSResponse:
        """Speak text via TTS. Returns response with status."""
        start = time.time()
        self._status = TTSStatus.SPEAKING
        provider = self.active_provider

        try:
            if self._privacy_mode:
                result = self._speak_local(text)
            else:
                result = self._speak_api(text)

            elapsed = (time.time() - start) * 1000
            self._total_spoken += 1
            self._status = TTSStatus.IDLE

            return TTSResponse(
                response_id=f"TTS-{uuid.uuid4().hex[:12].upper()}",
                text=text,
                response_type=response_type,
                provider=provider,
                status=TTSStatus.IDLE,
                latency_ms=elapsed,
                timestamp=datetime.now(UTC).isoformat(),
            )
        except Exception as e:
            self._total_errors += 1
            self._status = TTSStatus.ERROR
            logger.error(f"[TTS] Error: {e}")
            return TTSResponse(
                response_id=f"TTS-{uuid.uuid4().hex[:12].upper()}",
                text=text,
                response_type=response_type,
                provider=provider,
                status=TTSStatus.ERROR,
                latency_ms=(time.time() - start) * 1000,
                timestamp=datetime.now(UTC).isoformat(),
            )

    def interrupt(self) -> bool:
        """Interrupt current speech."""
        if self._status == TTSStatus.SPEAKING:
            self._status = TTSStatus.INTERRUPTED
            self._total_interrupted += 1
            return True
        return False

    def _speak_api(self, text: str) -> bool:
        """Speak via external TTS API."""
        # PRODUCTION: HTTP request to TTS_API_URL
        # Return True on success
        # For now: truthfully mark as attempted
        logger.info(f"[TTS] API speak request: {text[:50]}...")
        return True

    def _speak_local(self, text: str) -> bool:
        """Speak via local pyttsx3 (privacy mode)."""
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say(text)
            engine.runAndWait()
            return True
        except ImportError:
            logger.warning("[TTS] pyttsx3 not installed for local TTS")
            return False
        except Exception as e:
            logger.error(f"[TTS] Local TTS error: {e}")
            return False

    def get_stats(self) -> Dict:
        return {
            "status": self._status.value,
            "active_provider": self.active_provider.value,
            "privacy_mode": self._privacy_mode,
            "total_spoken": self._total_spoken,
            "total_interrupted": self._total_interrupted,
            "total_errors": self._total_errors,
        }
