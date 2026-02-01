# G04: Voice Proxy
"""
TTS voice output integration using proxy API.

STRICT RULE: Voice is OUTPUT ONLY.
Voice CANNOT:
- Execute
- Click
- Submit
- Escalate

Voice CAN:
- Explain decisions
- Report progress
- Ask confirmations
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import uuid
from datetime import datetime, UTC


class VoiceOutputType(Enum):
    """CLOSED ENUM - 5 output types"""
    EXPLANATION = "EXPLANATION"
    PROGRESS = "PROGRESS"
    CONFIRMATION_REQUEST = "CONFIRMATION_REQUEST"
    SUMMARY = "SUMMARY"
    ALERT = "ALERT"


class VoiceOutputStatus(Enum):
    """CLOSED ENUM - 4 statuses"""
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    RATE_LIMITED = "RATE_LIMITED"


@dataclass(frozen=True)
class VoiceOutputRequest:
    """Request for voice output."""
    request_id: str
    output_type: VoiceOutputType
    text: str
    language: str
    priority: int  # 1-10, higher = more urgent


@dataclass(frozen=True)
class VoiceOutputResult:
    """Result of voice output attempt."""
    request_id: str
    status: VoiceOutputStatus
    audio_url: Optional[str]
    error_message: Optional[str]
    timestamp: str


# TTS Proxy endpoint
TTS_PROXY_URL = "https://tts-five-iota.vercel.app/api/audio"

# Rate limiting
MAX_REQUESTS_PER_MINUTE = 30
_request_count = 0
_last_reset: Optional[datetime] = None


def reset_rate_limit():
    """Reset rate limit counter (for testing)."""
    global _request_count, _last_reset
    _request_count = 0
    _last_reset = None


def check_rate_limit() -> bool:
    """Check if rate limit allows request."""
    global _request_count, _last_reset
    
    now = datetime.now(UTC)
    
    if _last_reset is None:
        _last_reset = now
        _request_count = 0
    
    # Reset if minute passed
    if (now - _last_reset).total_seconds() >= 60:
        _last_reset = now
        _request_count = 0
    
    return _request_count < MAX_REQUESTS_PER_MINUTE


def create_voice_request(
    text: str,
    output_type: VoiceOutputType = VoiceOutputType.EXPLANATION,
    language: str = "en",
    priority: int = 5,
) -> VoiceOutputRequest:
    """Create a voice output request."""
    return VoiceOutputRequest(
        request_id=f"VOI-{uuid.uuid4().hex[:16].upper()}",
        output_type=output_type,
        text=text,
        language=language,
        priority=priority,
    )


def build_tts_url(request: VoiceOutputRequest) -> str:
    """Build TTS API URL for request."""
    from urllib.parse import quote
    
    text_encoded = quote(request.text[:500])  # Limit text length
    return f"{TTS_PROXY_URL}?text={text_encoded}&lang={request.language}"


def process_voice_request(request: VoiceOutputRequest) -> VoiceOutputResult:
    """
    Process a voice output request.
    
    NOTE: This is a mock implementation for governance testing.
    Real implementation would make HTTP request to TTS proxy.
    """
    global _request_count
    
    # Check rate limit
    if not check_rate_limit():
        return VoiceOutputResult(
            request_id=request.request_id,
            status=VoiceOutputStatus.RATE_LIMITED,
            audio_url=None,
            error_message="Rate limit exceeded",
            timestamp=datetime.now(UTC).isoformat(),
        )
    
    # Validate request
    if not request.text.strip():
        return VoiceOutputResult(
            request_id=request.request_id,
            status=VoiceOutputStatus.FAILED,
            audio_url=None,
            error_message="Empty text not allowed",
            timestamp=datetime.now(UTC).isoformat(),
        )
    
    # Build URL (mock - doesn't actually call API)
    audio_url = build_tts_url(request)
    
    # Increment counter
    _request_count += 1
    
    return VoiceOutputResult(
        request_id=request.request_id,
        status=VoiceOutputStatus.DELIVERED,
        audio_url=audio_url,
        error_message=None,
        timestamp=datetime.now(UTC).isoformat(),
    )
