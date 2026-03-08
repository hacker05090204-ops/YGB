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
import re
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
    route_mode: str = "SECURITY"
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
    "OBJECTIVE_STATUS": RiskLevel.LOW,
    "SET_OBJECTIVE": RiskLevel.MEDIUM,
    "COMPLETE_OBJECTIVE": RiskLevel.LOW,
    "LAUNCH_APP": RiskLevel.HIGH,
    "OPEN_APP": RiskLevel.HIGH,
    "OPEN_URL": RiskLevel.HIGH,
    "RUN_APPROVED_TASK": RiskLevel.HIGH,
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


def _parse_host_action_transcript(
    text: str,
    context_args: Dict[str, str],
) -> Optional[tuple[str, Dict[str, str], str]]:
    """Parse bounded host-action intents when a signed session is present."""
    host_session_id = context_args.get("host_session_id", "").strip()
    if not host_session_id:
        return None

    text_clean = text.strip()
    text_lower = text_clean.lower()

    try:
        from backend.governance.host_action_governor import HostActionGovernor
    except Exception as exc:
        logger.warning("[VOICE] Host action governor unavailable: %s", exc)
        return None

    url_match = re.search(
        r"^(?:open|launch)\s+(https?://\S+)(?:\s+in\s+([a-z0-9 ._-]+))?$",
        text_lower,
        re.IGNORECASE,
    )
    if url_match:
        app_name = (url_match.group(2) or "msedge").strip()
        return (
            "OPEN_URL",
            {
                "url": url_match.group(1).strip(),
                "app": app_name,
                "host_session_id": host_session_id,
            },
            "HOST_ACTION",
        )

    task_match = re.search(
        r"^(?:run|start)\s+(.+)$",
        text_clean,
        re.IGNORECASE,
    )
    if task_match:
        task_name = task_match.group(1).strip()
        canonical_task = HostActionGovernor.canonicalize_task_name(task_name)
        if canonical_task:
            return (
                "RUN_APPROVED_TASK",
                {
                    "task": canonical_task,
                    "host_session_id": host_session_id,
                },
                "HOST_ACTION",
            )

    app_match = re.search(
        r"^(?:open|launch|start)\s+(.+)$",
        text_clean,
        re.IGNORECASE,
    )
    if app_match:
        app_name = app_match.group(1).strip()
        canonical_app = HostActionGovernor.canonicalize_app_name(app_name)
        if canonical_app:
            return (
                "LAUNCH_APP",
                {
                    "app": canonical_app,
                    "host_session_id": host_session_id,
                },
                "HOST_ACTION",
            )

    return None


def _parse_focus_transcript(text: str) -> Optional[tuple[str, Dict[str, str], str]]:
    """Parse explicit focus/objective commands for sticky single-task mode."""
    text_clean = text.strip()
    text_lower = text_clean.lower()

    if re.search(
        r"^(?:what(?:'s| is)\s+(?:the\s+)?)?(?:current\s+)?(?:focus|objective)(?:\s+status)?\??$",
        text_lower,
    ):
        return ("OBJECTIVE_STATUS", {}, "ASSISTANT")

    if re.search(
        r"^(?:i\s+)?(?:completed|finished|done\s+with)\s+(?:the\s+)?(?:project|objective|task)\b",
        text_lower,
    ) or re.search(
        r"^(?:mark|set)\s+(?:the\s+)?(?:project|objective|task)\s+as\s+complete\b",
        text_lower,
    ):
        return (
            "COMPLETE_OBJECTIVE",
            {"summary": text_clean},
            "ASSISTANT",
        )

    focus_match = re.search(
        r"^(?:focus\s+on|work\s+on|set\s+(?:the\s+)?objective\s+to|current\s+objective\s+is)\s+(.+)$",
        text_clean,
        re.IGNORECASE,
    )
    if focus_match:
        return (
            "SET_OBJECTIVE",
            {"title": focus_match.group(1).strip()},
            "ASSISTANT",
        )

    return None


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

    def process_transcript(
        self,
        text: str,
        user_id: str,
        device_id: str,
        confidence: float = 0.8,
        context_args: Optional[Dict[str, str]] = None,
    ) -> VoiceIntentSchema:
        """Process a transcript into an intent schema.

        Does NOT execute — just classifies and gates.
        Execution happens via confirm() for high-risk, or auto for low-risk.
        """
        # Parse intent
        args: Dict[str, str] = dict(context_args or {})
        route_mode = "SECURITY"
        parse_error: Optional[str] = None
        try:
            from impl_v1.phase49.governors.g12_voice_input import extract_intent
            voice_intent = extract_intent(text)
            if voice_intent.status.value == "PARSED":
                command_type = voice_intent.intent_type.value
                if voice_intent.extracted_value:
                    if command_type == "SET_TARGET":
                        args["target"] = voice_intent.extracted_value
                    elif command_type == "SET_SCOPE":
                        args["scope"] = voice_intent.extracted_value
                    else:
                        args["value"] = voice_intent.extracted_value
            else:
                command_type = "UNKNOWN"
                parse_error = voice_intent.block_reason or "Unable to parse intent"
        except Exception as e:
            logger.warning(f"[VOICE] Intent parse failed: {e}")
            command_type = "UNKNOWN"
            parse_error = "Intent parser unavailable"

        focus_action = _parse_focus_transcript(text)
        if focus_action is not None:
            command_type, focus_args, route_mode = focus_action
            args = {**args, **focus_args}
            parse_error = None

        host_action = _parse_host_action_transcript(text, args)
        if host_action is not None:
            command_type, host_args, route_mode = host_action
            args = {**args, **host_args}
            parse_error = None

        # Research/chat fallback: use the isolated research router for
        # non-operational questions that the security parser does not handle.
        if command_type == "UNKNOWN":
            try:
                from backend.assistant.query_router import QueryRouter, VoiceMode

                route = QueryRouter().classify(text)
                route_mode = route.mode.value
                if route.mode == VoiceMode.RESEARCH:
                    command_type = "RESEARCH_QUERY"
                    args["query"] = text.strip()
                    parse_error = None
            except Exception as e:
                logger.warning(f"[VOICE] Query router fallback failed: {e}")
        elif route_mode not in {"HOST_ACTION", "ASSISTANT"}:
            route_mode = "SECURITY"

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
                args=args,
                confidence=confidence,
                risk_level=risk,
                requires_confirmation=risk in CONFIRMATION_REQUIRED,
                idempotency_key=idem_key,
                transcript_text=text,
                timestamp=datetime.now(UTC).isoformat(),
                route_mode=route_mode,
                error="DUPLICATE: Command already processed in this window",
            )

        intent = VoiceIntentSchema(
            intent_id=f"INT-{uuid.uuid4().hex[:12].upper()}",
            user_id=user_id,
            device_id=device_id,
            command_type=command_type,
            args=args,
            confidence=confidence,
            risk_level=risk,
            requires_confirmation=risk in CONFIRMATION_REQUIRED,
            idempotency_key=idem_key,
            transcript_text=text,
            timestamp=datetime.now(UTC).isoformat(),
            route_mode=route_mode,
            error=parse_error,
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

    def get_intent(self, intent_id: str) -> Optional[VoiceIntentSchema]:
        """Fetch an intent by ID."""
        return self._intents.get(intent_id)

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

    def mark_failed(self, intent_id: str, error: str):
        """Mark intent as failed/blocked without deleting its audit trail."""
        intent = self._intents.get(intent_id)
        if intent:
            intent.error = error
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
