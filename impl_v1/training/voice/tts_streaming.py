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
    audio_url: Optional[str] = None


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

    def probe_provider(self) -> Dict:
        """Probe the active provider truthfully."""
        if self._privacy_mode:
            try:
                import pyttsx3  # type: ignore

                return {
                    "provider": TTSProvider.LOCAL_PYTTSX3.value,
                    "reachable": True,
                    "reason": "pyttsx3 available",
                }
            except ImportError:
                return {
                    "provider": TTSProvider.LOCAL_PYTTSX3.value,
                    "reachable": False,
                    "reason": "pyttsx3 not installed",
                }
            except Exception as exc:
                return {
                    "provider": TTSProvider.LOCAL_PYTTSX3.value,
                    "reachable": False,
                    "reason": f"local_tts_probe_failed:{type(exc).__name__}",
                }

        try:
            from impl_v1.phase49.governors.g04_voice_proxy import (
                VoiceOutputType,
                build_tts_url,
                create_voice_request,
            )
            import os
            import urllib.request

            request = create_voice_request(
                text="voice proxy health",
                output_type=VoiceOutputType.PROGRESS,
                language="en",
                priority=1,
            )
            probe_url = build_tts_url(request)
            if os.environ.get("YGB_TEST_MODE", "").lower() == "true":
                return {
                    "provider": TTSProvider.API_PROXY.value,
                    "reachable": True,
                    "reason": "test_mode",
                    "audio_url": probe_url,
                }

            req = urllib.request.Request(probe_url, method="GET")
            req.add_header("User-Agent", "YGB-VoiceHealth/1.0")
            with urllib.request.urlopen(req, timeout=3) as resp:
                reachable = resp.status == 200
            return {
                "provider": TTSProvider.API_PROXY.value,
                "reachable": reachable,
                "reason": "HTTP_200" if reachable else f"HTTP_{resp.status}",
                "audio_url": probe_url,
            }
        except Exception as exc:
            return {
                "provider": TTSProvider.API_PROXY.value,
                "reachable": False,
                "reason": f"proxy_probe_failed:{type(exc).__name__}",
            }

    def speak(self, text: str, response_type: ResponseType = ResponseType.SUCCESS
              ) -> TTSResponse:
        """Speak text via TTS. Returns response with status."""
        start = time.time()
        self._status = TTSStatus.SPEAKING
        provider = self.active_provider
        audio_url = None

        try:
            if self._privacy_mode:
                delivered = self._speak_local(text)
            else:
                delivered, audio_url = self._speak_api(text, response_type)

            if not delivered:
                self._total_errors += 1
                self._status = TTSStatus.ERROR
                return TTSResponse(
                    response_id=f"TTS-{uuid.uuid4().hex[:12].upper()}",
                    text=text,
                    response_type=response_type,
                    provider=provider,
                    status=TTSStatus.ERROR,
                    latency_ms=(time.time() - start) * 1000,
                    timestamp=datetime.now(UTC).isoformat(),
                    audio_url=audio_url,
                )

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
                audio_url=audio_url,
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
                audio_url=audio_url,
            )

    def interrupt(self) -> bool:
        """Interrupt current speech."""
        if self._status == TTSStatus.SPEAKING:
            self._status = TTSStatus.INTERRUPTED
            self._total_interrupted += 1
            return True
        return False

    def _speak_api(self, text: str, response_type: ResponseType) -> tuple[bool, Optional[str]]:
        """Speak via the real TTS proxy governor."""
        from impl_v1.phase49.governors.g04_voice_proxy import (
            VoiceOutputType,
            create_voice_request,
            process_voice_request,
            reset_rate_limit,
        )

        if os.environ.get("YGB_TEST_MODE", "").lower() == "true":
            reset_rate_limit()

        output_type = {
            ResponseType.SUCCESS: VoiceOutputType.EXPLANATION,
            ResponseType.BLOCKED: VoiceOutputType.ALERT,
            ResponseType.RETRY_IN_PROGRESS: VoiceOutputType.PROGRESS,
            ResponseType.FAILURE: VoiceOutputType.ALERT,
        }.get(response_type, VoiceOutputType.EXPLANATION)

        result = process_voice_request(
            create_voice_request(
                text=text,
                output_type=output_type,
                language="en",
                priority=5,
            )
        )
        if result.status.value == "DELIVERED":
            logger.info(f"[TTS] Proxy delivered audio for: {text[:50]}...")
            return True, result.audio_url

        logger.warning("[TTS] Proxy delivery failed: %s", result.error_message or result.status.value)
        return False, result.audio_url

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
            "provider_health": self.probe_provider(),
        }
