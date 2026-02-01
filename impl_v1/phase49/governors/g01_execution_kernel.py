# G01: Execution Kernel
"""
Deterministic state machine for execution control.

CRITICAL RULES:
- DENY is terminal (no recovery)
- Human approval MANDATORY for EXECUTING state
- All transitions logged
- No auto-resume after STOPPED
"""

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import List, Optional
import uuid


class ExecutionState(Enum):
    """CLOSED ENUM - 6 states"""
    IDLE = "IDLE"
    PLANNED = "PLANNED"
    SIMULATED = "SIMULATED"
    AWAIT_HUMAN = "AWAIT_HUMAN"
    EXECUTING = "EXECUTING"
    STOPPED = "STOPPED"


class ExecutionTransition(Enum):
    """CLOSED ENUM - 7 transitions"""
    PLAN = "PLAN"
    SIMULATE = "SIMULATE"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    HUMAN_APPROVE = "HUMAN_APPROVE"
    HUMAN_DENY = "HUMAN_DENY"
    COMPLETE = "COMPLETE"
    ABORT = "ABORT"


class TransitionResult(Enum):
    """CLOSED ENUM - 3 results"""
    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    INVALID = "INVALID"


@dataclass(frozen=True)
class ExecutionAuditEntry:
    """Immutable audit log entry."""
    entry_id: str
    from_state: ExecutionState
    to_state: ExecutionState
    transition: ExecutionTransition
    actor_id: str
    timestamp: str
    reason: str


@dataclass(frozen=True)
class TransitionOutcome:
    """Result of a state transition attempt."""
    result: TransitionResult
    from_state: ExecutionState
    to_state: ExecutionState
    reason: str


# Valid state transitions
VALID_TRANSITIONS = {
    (ExecutionState.IDLE, ExecutionTransition.PLAN): ExecutionState.PLANNED,
    (ExecutionState.PLANNED, ExecutionTransition.SIMULATE): ExecutionState.SIMULATED,
    (ExecutionState.SIMULATED, ExecutionTransition.REQUEST_APPROVAL): ExecutionState.AWAIT_HUMAN,
    (ExecutionState.AWAIT_HUMAN, ExecutionTransition.HUMAN_APPROVE): ExecutionState.EXECUTING,
    (ExecutionState.AWAIT_HUMAN, ExecutionTransition.HUMAN_DENY): ExecutionState.STOPPED,
    (ExecutionState.EXECUTING, ExecutionTransition.COMPLETE): ExecutionState.STOPPED,
    (ExecutionState.EXECUTING, ExecutionTransition.ABORT): ExecutionState.STOPPED,
    # Allow abort from any non-terminal state
    (ExecutionState.IDLE, ExecutionTransition.ABORT): ExecutionState.STOPPED,
    (ExecutionState.PLANNED, ExecutionTransition.ABORT): ExecutionState.STOPPED,
    (ExecutionState.SIMULATED, ExecutionTransition.ABORT): ExecutionState.STOPPED,
    (ExecutionState.AWAIT_HUMAN, ExecutionTransition.ABORT): ExecutionState.STOPPED,
}


class ExecutionKernel:
    """
    Execution state machine with mandatory human approval.
    
    INVARIANTS:
    - STOPPED is terminal
    - EXECUTING requires human approval
    - All transitions are logged
    """
    
    def __init__(self, session_id: Optional[str] = None):
        self._session_id = session_id or f"SESS-{uuid.uuid4().hex[:16].upper()}"
        self._state = ExecutionState.IDLE
        self._audit_log: List[ExecutionAuditEntry] = []
        self._human_approved = False
        self._deny_reason: Optional[str] = None
    
    @property
    def session_id(self) -> str:
        return self._session_id
    
    @property
    def state(self) -> ExecutionState:
        return self._state
    
    @property
    def is_terminal(self) -> bool:
        return self._state == ExecutionState.STOPPED
    
    @property
    def human_approved(self) -> bool:
        return self._human_approved
    
    @property
    def deny_reason(self) -> Optional[str]:
        return self._deny_reason
    
    def get_audit_log(self) -> List[ExecutionAuditEntry]:
        return list(self._audit_log)
    
    def transition(
        self,
        transition: ExecutionTransition,
        actor_id: str,
        reason: str = "",
    ) -> TransitionOutcome:
        """
        Attempt a state transition.
        
        Returns TransitionOutcome with result.
        """
        # Terminal state check
        if self.is_terminal:
            return TransitionOutcome(
                result=TransitionResult.DENIED,
                from_state=self._state,
                to_state=self._state,
                reason="Cannot transition from terminal STOPPED state",
            )
        
        # Check valid transition
        key = (self._state, transition)
        if key not in VALID_TRANSITIONS:
            return TransitionOutcome(
                result=TransitionResult.INVALID,
                from_state=self._state,
                to_state=self._state,
                reason=f"Invalid transition {transition.value} from {self._state.value}",
            )
        
        new_state = VALID_TRANSITIONS[key]
        
        # Special handling for HUMAN_DENY
        if transition == ExecutionTransition.HUMAN_DENY:
            self._deny_reason = reason
        
        # Track human approval
        if transition == ExecutionTransition.HUMAN_APPROVE:
            self._human_approved = True
        
        # Log transition
        entry = ExecutionAuditEntry(
            entry_id=f"AUD-{uuid.uuid4().hex[:16].upper()}",
            from_state=self._state,
            to_state=new_state,
            transition=transition,
            actor_id=actor_id,
            timestamp=datetime.now(UTC).isoformat(),
            reason=reason,
        )
        self._audit_log.append(entry)
        
        # Update state
        old_state = self._state
        self._state = new_state
        
        return TransitionOutcome(
            result=TransitionResult.SUCCESS,
            from_state=old_state,
            to_state=new_state,
            reason=reason,
        )
    
    def can_execute(self) -> bool:
        """Check if execution is allowed."""
        return self._state == ExecutionState.EXECUTING and self._human_approved


def create_execution_kernel(session_id: Optional[str] = None) -> ExecutionKernel:
    """Factory function to create an execution kernel."""
    return ExecutionKernel(session_id)
