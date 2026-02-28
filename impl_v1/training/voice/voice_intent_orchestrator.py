"""
Voice Intent Orchestrator — Central pipeline: STT → intent → safety → executor → TTS.

Responsibilities:
  - Accept transcripts from STT adapter chain
  - Parse intent via g12 extract_intent
  - Apply policy gates
  - Delegate to CommandQueue for execution
  - Return TTS response
  - Dedup via idempotency keys
"""

import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


# =============================================================================
# INTENT SCHEMA
# =============================================================================

class RiskLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class VoiceIntentSchema:
    """Deterministic intent schema for the orchestration pipeline."""
    intent_id: str
    user_id: str
    device_id: str
    command_type: str
    args: Dict[str, str]
    confidence: float
    risk_level: RiskLevel
    requires_confirmation: bool
    idempotency_key: str
    transcript_text: str
    timestamp: str
    confirmed: bool = False
    executed: bool = False
    result: Optional[str] = None
    error: Optional[str] = None


# =============================================================================
# IDEMPOTENCY
# =============================================================================

# Window for dedup: 5 minutes
DEDUP_WINDOW_S = 300
_idempotency_store: Dict[str, float] = {}


def compute_idempotency_key(user_id: str, command_text: str) -> str:
    """Compute idempotency key from user + command + 5-minute window."""
    window = int(time.time() / DEDUP_WINDOW_S)
    raw = f"{user_id}:{command_text.strip().lower()}:{window}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def is_duplicate(key: str) -> bool:
    """Check if this idempotency key was already processed."""
    now = time.time()
    # Cleanup old entries
    expired = [k for k, t in _idempotency_store.items() if now - t > DEDUP_WINDOW_S]
    for k in expired:
        del _idempotency_store[k]
    return key in _idempotency_store


def mark_processed(key: str):
    """Mark an idempotency key as processed."""
    _idempotency_store[key] = time.time()


# =============================================================================
# RISK CLASSIFICATION
# =============================================================================

_COMMAND_RISK: Dict[str, RiskLevel] = {
    "QUERY_STATUS": RiskLevel.LOW,
    "QUERY_PROGRESS": RiskLevel.LOW,
    "QUERY_GPU": RiskLevel.LOW,
    "QUERY_TRAINING": RiskLevel.LOW,
    "SET_TARGET": RiskLevel.MEDIUM,
    "SET_SCOPE": RiskLevel.MEDIUM,
    "FIND_TARGETS": RiskLevel.MEDIUM,
    "RESEARCH_QUERY": RiskLevel.MEDIUM,
    "REPORT_HELP": RiskLevel.LOW,
    "SCREEN_TAKEOVER": RiskLevel.HIGH,
    "START_TRAINING": RiskLevel.HIGH,
    "STOP_TRAINING": RiskLevel.HIGH,
    "START_SCAN": RiskLevel.HIGH,
    "STOP_SCAN": RiskLevel.MEDIUM,
    "EXPORT_REPORT": RiskLevel.MEDIUM,
    "CONFIG_CHANGE": RiskLevel.HIGH,
    "SECURITY_CHANGE": RiskLevel.CRITICAL,
    "UNKNOWN": RiskLevel.CRITICAL,
}

CONFIRMATION_REQUIRED = {RiskLevel.HIGH, RiskLevel.CRITICAL}


def classify_intent_risk(command_type: str) -> RiskLevel:
    """Classify risk level for an intent command type."""
    return _COMMAND_RISK.get(command_type, RiskLevel.CRITICAL)


# =============================================================================
# ORCHESTRATOR
# =============================================================================

class VoiceIntentOrchestrator:
    """Central voice orchestration pipeline.

    Flow: transcript → intent parse → risk classify → policy check →
          confirmation gate → execute → TTS response
    """

    def __init__(self):
        self._intents: Dict[str, VoiceIntentSchema] = {}
        self._processed_count = 0
        self._blocked_count = 0
        self._confirmed_count = 0
        self._rejected_count = 0

    def process_transcript(self, text: str, user_id: str,
                            device_id: str, confidence: float = 0.8
                            ) -> VoiceIntentSchema:
        """Process a transcript into an intent schema.

        Does NOT execute — just classifies and gates.
        Execution happens via confirm() for high-risk, or auto for low-risk.
        """
        # Parse intent
        try:
            from impl_v1.phase49.governors.g12_voice_input import extract_intent
            voice_intent = extract_intent(text)
            command_type = voice_intent.intent_type.value
        except Exception as e:
            logger.warning(f"[VOICE] Intent parse failed: {e}")
            command_type = "UNKNOWN"

        # Classify risk
        risk = classify_intent_risk(command_type)

        # Compute idempotency key
        idem_key = compute_idempotency_key(user_id, text)

        # Check dedup
        if is_duplicate(idem_key):
            logger.info(f"[VOICE] Duplicate command detected: {idem_key}")
            return VoiceIntentSchema(
                intent_id=f"INT-{uuid.uuid4().hex[:12].upper()}",
                user_id=user_id,
                device_id=device_id,
                command_type=command_type,
                args={},
                confidence=confidence,
                risk_level=risk,
                requires_confirmation=risk in CONFIRMATION_REQUIRED,
                idempotency_key=idem_key,
                transcript_text=text,
                timestamp=datetime.now(UTC).isoformat(),
                error="DUPLICATE: Command already processed in this window",
            )

        intent = VoiceIntentSchema(
            intent_id=f"INT-{uuid.uuid4().hex[:12].upper()}",
            user_id=user_id,
            device_id=device_id,
            command_type=command_type,
            args={},
            confidence=confidence,
            risk_level=risk,
            requires_confirmation=risk in CONFIRMATION_REQUIRED,
            idempotency_key=idem_key,
            transcript_text=text,
            timestamp=datetime.now(UTC).isoformat(),
        )

        self._intents[intent.intent_id] = intent
        self._processed_count += 1
        mark_processed(idem_key)

        return intent

    def confirm_intent(self, intent_id: str, confirmer_id: str) -> bool:
        """Confirm a high-risk intent for execution."""
        intent = self._intents.get(intent_id)
        if not intent:
            return False
        if not intent.requires_confirmation:
            return False
        if intent.confirmed:
            return False

        intent.confirmed = True
        self._confirmed_count += 1
        mark_processed(intent.idempotency_key)
        logger.info(f"[VOICE] Intent {intent_id} confirmed by {confirmer_id}")
        return True

    def reject_intent(self, intent_id: str, reason: str = "") -> bool:
        """Reject an intent."""
        intent = self._intents.get(intent_id)
        if not intent:
            return False
        intent.error = f"REJECTED: {reason}" if reason else "REJECTED"
        self._rejected_count += 1
        mark_processed(intent.idempotency_key)
        return True

    def is_ready_to_execute(self, intent_id: str) -> bool:
        """Check if an intent is ready to execute."""
        intent = self._intents.get(intent_id)
        if not intent:
            return False
        if intent.executed:
            return False
        if intent.error:
            return False
        if intent.requires_confirmation and not intent.confirmed:
            return False
        return True

    def mark_executed(self, intent_id: str, result: str):
        """Mark intent as executed with result."""
        intent = self._intents.get(intent_id)
        if intent:
            intent.executed = True
            intent.result = result
            mark_processed(intent.idempotency_key)

    def get_stats(self) -> Dict[str, int]:
        return {
            "processed": self._processed_count,
            "blocked": self._blocked_count,
            "confirmed": self._confirmed_count,
            "rejected": self._rejected_count,
            "pending_confirmation": sum(
                1 for i in self._intents.values()
                if i.requires_confirmation and not i.confirmed and not i.error
            ),
        }

    def clear(self):
        """Clear all state (for testing)."""
        self._intents.clear()
        self._processed_count = 0
        self._blocked_count = 0
        self._confirmed_count = 0
        self._rejected_count = 0
        _idempotency_store.clear()
