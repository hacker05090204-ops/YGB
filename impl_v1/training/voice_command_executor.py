"""
Voice Command Executor — Jarvis-like command execution pipeline.

SAFE POLICY:
  - LOW risk commands → execute directly
  - MEDIUM risk commands → execute with audit logging
  - HIGH risk commands → require explicit human confirmation
  - CRITICAL risk commands → require governance token + human session

NO BYPASS of existing autonomy/governance restrictions.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Callable, Tuple
from datetime import datetime, UTC
import uuid
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================

class CommandRisk(Enum):
    """Risk level for voice commands."""
    LOW = "LOW"           # Status queries, read-only actions
    MEDIUM = "MEDIUM"     # Configuration changes, non-destructive writes
    HIGH = "HIGH"         # Training actions, data modifications
    CRITICAL = "CRITICAL" # Security changes, governance overrides (BLOCKED)


class CommandStatus(Enum):
    """Execution status for voice commands."""
    QUEUED = "QUEUED"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"


class ActionType(Enum):
    """Types of actions that can be performed."""
    STATUS_QUERY = "STATUS_QUERY"
    TRAINING_STATUS = "TRAINING_STATUS"
    LIST_DEVICES = "LIST_DEVICES"
    START_SCAN = "START_SCAN"
    STOP_SCAN = "STOP_SCAN"
    START_TRAINING = "START_TRAINING"
    STOP_TRAINING = "STOP_TRAINING"
    EXPORT_REPORT = "EXPORT_REPORT"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    SECURITY_CHANGE = "SECURITY_CHANGE"
    UNKNOWN = "UNKNOWN"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class VoiceCommand:
    """A single voice command in the execution pipeline."""
    command_id: str
    raw_text: str
    parsed_action: ActionType
    risk_level: CommandRisk
    status: CommandStatus
    created_at: str
    updated_at: str
    retries: int = 0
    max_retries: int = 3
    result: Optional[str] = None
    error: Optional[str] = None
    confirmed_by: Optional[str] = None
    governance_token: Optional[str] = None
    execution_time_ms: Optional[float] = None
    audit_hash: Optional[str] = None


@dataclass
class ExecutionResult:
    """Result of executing a voice command."""
    command_id: str
    success: bool
    status: CommandStatus
    result: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0


@dataclass
class CommandAuditEntry:
    """Audit trail entry for a command."""
    entry_id: str
    command_id: str
    action: str
    timestamp: str
    actor: str
    detail: str


# =============================================================================
# RISK CLASSIFICATION
# =============================================================================

_ACTION_RISK_MAP: Dict[ActionType, CommandRisk] = {
    ActionType.STATUS_QUERY: CommandRisk.LOW,
    ActionType.TRAINING_STATUS: CommandRisk.LOW,
    ActionType.LIST_DEVICES: CommandRisk.LOW,
    ActionType.EXPORT_REPORT: CommandRisk.LOW,
    ActionType.START_SCAN: CommandRisk.MEDIUM,
    ActionType.STOP_SCAN: CommandRisk.MEDIUM,
    ActionType.START_TRAINING: CommandRisk.HIGH,
    ActionType.STOP_TRAINING: CommandRisk.HIGH,
    ActionType.CONFIG_CHANGE: CommandRisk.HIGH,
    ActionType.SECURITY_CHANGE: CommandRisk.CRITICAL,
    ActionType.UNKNOWN: CommandRisk.CRITICAL,
}


def classify_risk(action: ActionType) -> CommandRisk:
    """Classify the risk level of an action."""
    return _ACTION_RISK_MAP.get(action, CommandRisk.CRITICAL)


# =============================================================================
# COMMAND PARSER
# =============================================================================

_KEYWORD_MAP: Dict[str, ActionType] = {
    "status": ActionType.STATUS_QUERY,
    "training status": ActionType.TRAINING_STATUS,
    "list devices": ActionType.LIST_DEVICES,
    "show devices": ActionType.LIST_DEVICES,
    "start scan": ActionType.START_SCAN,
    "stop scan": ActionType.STOP_SCAN,
    "start training": ActionType.START_TRAINING,
    "stop training": ActionType.STOP_TRAINING,
    "export report": ActionType.EXPORT_REPORT,
    "generate report": ActionType.EXPORT_REPORT,
}


def parse_voice_text(text: str) -> ActionType:
    """Parse raw voice text into an action type."""
    text_lower = text.lower().strip()
    # Match longest keyword first
    for keyword in sorted(_KEYWORD_MAP.keys(), key=len, reverse=True):
        if keyword in text_lower:
            return _KEYWORD_MAP[keyword]
    return ActionType.UNKNOWN


# =============================================================================
# COMMAND QUEUE
# =============================================================================

class CommandQueue:
    """
    Persistent command queue with execution status tracking.

    Provides:
    - FIFO ordering
    - Status tracking per command
    - Retry support
    - Audit trail
    """

    def __init__(self):
        self._queue: List[VoiceCommand] = []
        self._history: List[VoiceCommand] = []
        self._audit: List[CommandAuditEntry] = []
        self._handlers: Dict[ActionType, Callable] = {}

    def register_handler(self, action: ActionType, handler: Callable):
        """Register a handler for an action type."""
        self._handlers[action] = handler

    def submit(self, raw_text: str) -> VoiceCommand:
        """
        Submit a voice command to the queue.

        Parses the command, classifies risk, and either:
        - Queues for direct execution (LOW/MEDIUM risk)
        - Queues for confirmation (HIGH risk)
        - Rejects immediately (CRITICAL risk without governance token)
        """
        now = datetime.now(UTC).isoformat()
        action = parse_voice_text(raw_text)
        risk = classify_risk(action)

        cmd = VoiceCommand(
            command_id=f"CMD-{uuid.uuid4().hex[:16].upper()}",
            raw_text=raw_text,
            parsed_action=action,
            risk_level=risk,
            status=CommandStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )

        # CRITICAL risk → reject without governance token
        if risk == CommandRisk.CRITICAL:
            cmd.status = CommandStatus.REJECTED
            cmd.error = "CRITICAL risk commands require governance token"
            self._audit_log(cmd, "REJECTED", "system", "Critical risk auto-rejected")
            self._history.append(cmd)
            return cmd

        # HIGH risk → require confirmation
        if risk == CommandRisk.HIGH:
            cmd.status = CommandStatus.AWAITING_CONFIRMATION
            self._audit_log(cmd, "QUEUED_FOR_CONFIRMATION", "system", "High risk requires confirmation")

        # LOW/MEDIUM → queued for direct execution
        self._queue.append(cmd)
        self._audit_log(cmd, "SUBMITTED", "system", f"Risk: {risk.value}")
        return cmd

    def confirm(self, command_id: str, confirmer_id: str) -> Optional[VoiceCommand]:
        """Confirm a HIGH-risk command for execution."""
        cmd = self._find_in_queue(command_id)
        if not cmd:
            return None
        if cmd.status != CommandStatus.AWAITING_CONFIRMATION:
            return cmd

        cmd.status = CommandStatus.QUEUED
        cmd.confirmed_by = confirmer_id
        cmd.updated_at = datetime.now(UTC).isoformat()
        self._audit_log(cmd, "CONFIRMED", confirmer_id, "Human confirmation received")
        return cmd

    def reject(self, command_id: str, rejector_id: str, reason: str = "") -> Optional[VoiceCommand]:
        """Reject a command."""
        cmd = self._find_in_queue(command_id)
        if not cmd:
            return None
        cmd.status = CommandStatus.REJECTED
        cmd.error = reason or "Rejected by human"
        cmd.updated_at = datetime.now(UTC).isoformat()
        self._queue.remove(cmd)
        self._history.append(cmd)
        self._audit_log(cmd, "REJECTED", rejector_id, reason)
        return cmd

    def execute_next(self) -> Optional[ExecutionResult]:
        """Execute the next ready command in the queue."""
        cmd = self._next_ready()
        if not cmd:
            return None

        # Don't execute unconfirmed HIGH-risk commands
        if cmd.risk_level == CommandRisk.HIGH and not cmd.confirmed_by:
            return None

        cmd.status = CommandStatus.EXECUTING
        cmd.updated_at = datetime.now(UTC).isoformat()
        self._audit_log(cmd, "EXECUTING", "system", f"Action: {cmd.parsed_action.value}")

        import time
        start = time.monotonic()

        try:
            handler = self._handlers.get(cmd.parsed_action)
            if handler:
                result_text = handler(cmd)
            else:
                result_text = f"Action {cmd.parsed_action.value} acknowledged (no handler registered)"

            elapsed = (time.monotonic() - start) * 1000

            cmd.status = CommandStatus.COMPLETED
            cmd.result = str(result_text) if result_text else "OK"
            cmd.execution_time_ms = elapsed
            cmd.audit_hash = self._compute_audit_hash(cmd)
            cmd.updated_at = datetime.now(UTC).isoformat()

            self._queue.remove(cmd)
            self._history.append(cmd)
            self._audit_log(cmd, "COMPLETED", "system", f"Result: {cmd.result[:100]}")

            return ExecutionResult(
                command_id=cmd.command_id,
                success=True,
                status=CommandStatus.COMPLETED,
                result=cmd.result,
                execution_time_ms=elapsed,
            )

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            cmd.retries += 1

            if cmd.retries >= cmd.max_retries:
                cmd.status = CommandStatus.FAILED
                cmd.error = str(e)
                cmd.execution_time_ms = elapsed
                cmd.updated_at = datetime.now(UTC).isoformat()
                self._queue.remove(cmd)
                self._history.append(cmd)
                self._audit_log(cmd, "FAILED", "system", f"Error after {cmd.retries} retries: {e}")

                return ExecutionResult(
                    command_id=cmd.command_id,
                    success=False,
                    status=CommandStatus.FAILED,
                    error=str(e),
                    execution_time_ms=elapsed,
                )
            else:
                cmd.status = CommandStatus.QUEUED
                cmd.updated_at = datetime.now(UTC).isoformat()
                self._audit_log(cmd, "RETRY", "system", f"Retry {cmd.retries}/{cmd.max_retries}: {e}")
                return ExecutionResult(
                    command_id=cmd.command_id,
                    success=False,
                    status=CommandStatus.QUEUED,
                    error=f"Retrying ({cmd.retries}/{cmd.max_retries}): {e}",
                    execution_time_ms=elapsed,
                )

    def get_queue(self) -> List[VoiceCommand]:
        """Get current queue contents."""
        return list(self._queue)

    def get_history(self) -> List[VoiceCommand]:
        """Get execution history."""
        return list(self._history)

    def get_audit_trail(self) -> List[CommandAuditEntry]:
        """Get full audit trail."""
        return list(self._audit)

    def get_status(self, command_id: str) -> Optional[VoiceCommand]:
        """Get status of a specific command."""
        cmd = self._find_in_queue(command_id)
        if cmd:
            return cmd
        for h in self._history:
            if h.command_id == command_id:
                return h
        return None

    def pending_count(self) -> int:
        """Count of commands waiting for execution or confirmation."""
        return len(self._queue)

    def _find_in_queue(self, command_id: str) -> Optional[VoiceCommand]:
        for cmd in self._queue:
            if cmd.command_id == command_id:
                return cmd
        return None

    def _next_ready(self) -> Optional[VoiceCommand]:
        for cmd in self._queue:
            if cmd.status == CommandStatus.QUEUED:
                return cmd
        return None

    def _audit_log(self, cmd: VoiceCommand, action: str, actor: str, detail: str):
        entry = CommandAuditEntry(
            entry_id=f"AUD-{uuid.uuid4().hex[:12].upper()}",
            command_id=cmd.command_id,
            action=action,
            timestamp=datetime.now(UTC).isoformat(),
            actor=actor,
            detail=detail,
        )
        self._audit.append(entry)

    @staticmethod
    def _compute_audit_hash(cmd: VoiceCommand) -> str:
        content = f"{cmd.command_id}:{cmd.raw_text}:{cmd.parsed_action.value}:{cmd.result}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]


# =============================================================================
# GOVERNANCE GUARDS
# =============================================================================

def can_voice_execute_directly() -> Tuple[bool, str]:
    """Check if voice can execute commands directly.
    Returns (False, reason) — voice NEVER bypasses governance."""
    return False, "Voice commands are routed through CommandQueue with risk classification"


def can_voice_bypass_confirmation() -> Tuple[bool, str]:
    """Check if voice can bypass confirmation for HIGH-risk commands.
    ALWAYS returns False."""
    return False, "HIGH-risk commands always require human confirmation"
