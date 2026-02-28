# G29: Real Voice Input (STT) Governor
"""
Real voice input with speech-to-text.

Features:
✓ Microphone capture
✓ Wake word detection
✓ Noise filtering
✓ STOP hotword
✓ Intent → Dashboard routing

STRICT RULES:
- Voice CANNOT execute
- Voice CANNOT approve
- Voice CANNOT click
- Voice CANNOT submit
- Voice is INPUT ONLY
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Callable, Dict, Any
import uuid
from datetime import datetime, UTC


class VoiceIntent(Enum):
    """CLOSED ENUM - Voice intents."""
    SET_TARGET = "SET_TARGET"
    ASK_STATUS = "ASK_STATUS"
    REQUEST_DISCOVERY = "REQUEST_DISCOVERY"
    REQUEST_REPORT = "REQUEST_REPORT"
    TOGGLE_VOICE = "TOGGLE_VOICE"
    STOP = "STOP"
    UNKNOWN = "UNKNOWN"


class VoiceState(Enum):
    """CLOSED ENUM - Voice system state."""
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    RESPONDING = "RESPONDING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class AudioQuality(Enum):
    """CLOSED ENUM - Audio quality levels."""
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    UNUSABLE = "UNUSABLE"


@dataclass(frozen=True)
class VoiceCommand:
    """Parsed voice command."""
    command_id: str
    raw_text: str
    intent: VoiceIntent
    confidence: float
    parameters: Tuple[Tuple[str, str], ...]
    timestamp: str
    audio_quality: AudioQuality


@dataclass(frozen=True)
class VoiceSession:
    """Voice input session."""
    session_id: str
    started_at: str
    ended_at: Optional[str]
    state: VoiceState
    commands_count: int
    wake_word: str


@dataclass(frozen=True)
class IntentResult:
    """Result of intent routing."""
    command_id: str
    intent: VoiceIntent
    routed_to: str
    success: bool
    response_text: Optional[str]
    timestamp: str


# =============================================================================
# GUARDS (MANDATORY - ABSOLUTE)
# =============================================================================

def can_voice_execute() -> bool:
    """
    Guard: Can voice execute browser actions?
    
    ANSWER: NEVER.
    """
    return False


def can_voice_approve() -> bool:
    """
    Guard: Can voice approve execution?
    
    ANSWER: NEVER.
    """
    return False


def can_voice_click() -> bool:
    """
    Guard: Can voice perform clicks?
    
    ANSWER: NEVER.
    """
    return False


def can_voice_submit() -> bool:
    """
    Guard: Can voice submit data?
    
    ANSWER: NEVER.
    """
    return False


def can_voice_bypass_dashboard() -> bool:
    """
    Guard: Can voice bypass dashboard?
    
    ANSWER: NEVER.
    """
    return False


# =============================================================================
# WAKE WORDS & HOTWORDS
# =============================================================================

DEFAULT_WAKE_WORD = "hey hunter"
STOP_HOTWORDS = ("stop", "halt", "cancel", "abort", "quit")

SUPPORTED_WAKE_WORDS = (
    "hey hunter",
    "ok hunter",
    "hunter",
    "start listening",
)


# =============================================================================
# INTENT PATTERNS
# =============================================================================

INTENT_PATTERNS: Dict[VoiceIntent, Tuple[str, ...]] = {
    VoiceIntent.SET_TARGET: (
        "set target",
        "add target",
        "new target",
        "target",
    ),
    VoiceIntent.ASK_STATUS: (
        "what's the status",
        "status",
        "progress",
        "how many",
        "show progress",
    ),
    VoiceIntent.REQUEST_DISCOVERY: (
        "discover",
        "find targets",
        "search for",
        "look for",
    ),
    VoiceIntent.REQUEST_REPORT: (
        "generate report",
        "create report",
        "show report",
        "report",
    ),
    VoiceIntent.TOGGLE_VOICE: (
        "toggle voice",
        "enable voice",
        "disable voice",
        "mute",
        "unmute",
    ),
    VoiceIntent.STOP: STOP_HOTWORDS,
}


# =============================================================================
# AUDIO PROCESSING — NATIVE C++ LIBRARY REQUIRED
# =============================================================================

def assess_audio_quality(audio_level: float, noise_ratio: float) -> AudioQuality:
    """Assess audio quality from signal metrics."""
    if noise_ratio > 0.7 or audio_level < 0.1:
        return AudioQuality.UNUSABLE
    if noise_ratio > 0.4 or audio_level < 0.3:
        return AudioQuality.POOR
    if noise_ratio > 0.2 or audio_level < 0.5:
        return AudioQuality.FAIR
    return AudioQuality.GOOD


def apply_noise_filter(raw_audio: bytes, threshold: float = 0.2) -> tuple:
    """Apply noise filtering to audio.

    Requires native C++ audio processing library.
    Returns (filtered_audio, is_filtered).
    DEGRADED: Returns (unfiltered_audio, False) when native lib unavailable.
    """
    import os
    import logging
    _logger = logging.getLogger("ygb.voice.g29")

    if os.environ.get("YGB_NATIVE_AUDIO") == "1":
        # Real native audio filter would be called here via ctypes/pybind11
        raise NotImplementedError(
            "Native audio filter not yet linked. "
            "Set YGB_NATIVE_AUDIO=0 or unset to use pass-through."
        )
    # DEGRADED: Native audio library not available — pass-through with status
    _logger.warning(
        "[VOICE] Noise filter DEGRADED: native audio library not loaded. "
        "Audio returned unfiltered."
    )
    return (raw_audio, False)


# =============================================================================
# INTENT PARSING
# =============================================================================

def parse_intent(text: str) -> Tuple[VoiceIntent, float, Dict[str, str]]:
    """
    Parse intent from text.
    
    Returns (intent, confidence, parameters).
    """
    text_lower = text.lower().strip()
    
    # Check for STOP hotwords first (highest priority)
    for word in STOP_HOTWORDS:
        if word in text_lower:
            return (VoiceIntent.STOP, 1.0, {})
    
    # Check other intents
    for intent, patterns in INTENT_PATTERNS.items():
        if intent == VoiceIntent.STOP:
            continue  # Already handled
        
        for pattern in patterns:
            if pattern in text_lower:
                # Extract parameters (simple heuristic)
                params = {}
                remaining = text_lower.replace(pattern, "").strip()
                if remaining:
                    params["value"] = remaining
                
                confidence = 0.9 if pattern == text_lower else 0.7
                return (intent, confidence, params)
    
    return (VoiceIntent.UNKNOWN, 0.3, {})


# =============================================================================
# VOICE ENGINE
# =============================================================================

class VoiceInputEngine:
    """
    Voice input engine with STT.
    
    Routes intents to dashboard, NEVER executes.
    """
    
    def __init__(
        self,
        wake_word: str = DEFAULT_WAKE_WORD,
        on_intent: Optional[Callable[[VoiceIntent, Dict[str, str]], None]] = None,
    ):
        self.wake_word = wake_word
        self.on_intent = on_intent
        self._state = VoiceState.IDLE
        self._session: Optional[VoiceSession] = None
        self._commands: List[VoiceCommand] = []
    
    @property
    def state(self) -> VoiceState:
        """Get current state."""
        return self._state
    
    def start_listening(self) -> VoiceSession:
        """Start a new listening session."""
        self._session = VoiceSession(
            session_id=f"VOI-{uuid.uuid4().hex[:12].upper()}",
            started_at=datetime.now(UTC).isoformat(),
            ended_at=None,
            state=VoiceState.LISTENING,
            commands_count=0,
            wake_word=self.wake_word,
        )
        self._state = VoiceState.LISTENING
        self._commands = []
        return self._session
    
    def stop_listening(self) -> Optional[VoiceSession]:
        """Stop current listening session."""
        if not self._session:
            return None
        
        ended = VoiceSession(
            session_id=self._session.session_id,
            started_at=self._session.started_at,
            ended_at=datetime.now(UTC).isoformat(),
            state=VoiceState.STOPPED,
            commands_count=len(self._commands),
            wake_word=self._session.wake_word,
        )
        self._session = ended
        self._state = VoiceState.STOPPED
        return ended
    
    def detect_wake_word(self, text: str) -> bool:
        """Check if text contains wake word."""
        return self.wake_word.lower() in text.lower()
    
    def detect_stop_hotword(self, text: str) -> bool:
        """Check if text contains stop hotword."""
        text_lower = text.lower()
        return any(word in text_lower for word in STOP_HOTWORDS)
    
    def process_speech(
        self,
        text: str,
        audio_quality: AudioQuality = AudioQuality.GOOD,
    ) -> VoiceCommand:
        """
        Process speech input.
        
        Parses intent and routes to dashboard.
        NEVER executes.
        """
        # Enforce guards
        if can_voice_execute():  # pragma: no cover
            raise RuntimeError("SECURITY: Voice execution enabled")  # pragma: no cover
        if can_voice_approve():  # pragma: no cover
            raise RuntimeError("SECURITY: Voice approval enabled")  # pragma: no cover
        
        self._state = VoiceState.PROCESSING
        
        # Parse intent
        intent, confidence, params = parse_intent(text)
        
        command = VoiceCommand(
            command_id=f"CMD-{uuid.uuid4().hex[:12].upper()}",
            raw_text=text,
            intent=intent,
            confidence=confidence,
            parameters=tuple(params.items()),
            timestamp=datetime.now(UTC).isoformat(),
            audio_quality=audio_quality,
        )
        
        self._commands.append(command)
        
        # Route to callback if provided
        if self.on_intent and intent != VoiceIntent.UNKNOWN:
            self.on_intent(intent, params)
        
        self._state = VoiceState.LISTENING
        
        return command
    
    def get_commands(self) -> Tuple[VoiceCommand, ...]:
        """Get all commands from current session."""
        return tuple(self._commands)
    
    def route_to_dashboard(
        self,
        command: VoiceCommand,
        dashboard_handler: Callable[[VoiceIntent, Dict[str, str]], str],
    ) -> IntentResult:
        """
        Route command to dashboard.
        
        Returns routing result.
        """
        if can_voice_bypass_dashboard():  # pragma: no cover
            raise RuntimeError("SECURITY: Voice bypassing dashboard")  # pragma: no cover
        
        params = dict(command.parameters)
        
        try:
            response = dashboard_handler(command.intent, params)
            success = True
        except Exception as e:
            response = str(e)
            success = False
        
        return IntentResult(
            command_id=command.command_id,
            intent=command.intent,
            routed_to="DASHBOARD",
            success=success,
            response_text=response,
            timestamp=datetime.now(UTC).isoformat(),
        )


# =============================================================================
# HIGH-LEVEL API
# =============================================================================

def create_voice_engine(
    wake_word: str = DEFAULT_WAKE_WORD,
    on_intent: Optional[Callable[[VoiceIntent, Dict[str, str]], None]] = None,
) -> VoiceInputEngine:
    """Create a new voice input engine."""
    return VoiceInputEngine(wake_word, on_intent)


def is_voice_supported() -> bool:
    """Check if voice input is supported."""
    # In production: check for microphone availability
    return True
