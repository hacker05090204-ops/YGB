"""
State Machine - Phase-05 Workflow State Model
REIMPLEMENTED-2026

Defines transition logic with explicit transition table.
Pure functions only - no side effects, no execution logic.
"""

from dataclasses import dataclass
from typing import Optional, Tuple, FrozenSet

from python.phase02_actors.actors import ActorType
from python.phase05_workflow.states import WorkflowState, is_terminal_state
from python.phase05_workflow.transitions import StateTransition, requires_human


@dataclass(frozen=True)
class TransitionRequest:
    """
    Immutable request for a state transition.
    
    Attributes:
        current_state: The current workflow state
        transition: The requested transition
        actor_type: The type of actor requesting the transition
    """
    current_state: WorkflowState
    transition: StateTransition
    actor_type: ActorType


@dataclass(frozen=True)
class TransitionResponse:
    """
    Immutable response to a transition request.
    
    Attributes:
        request: The original transition request
        allowed: Whether the transition is allowed
        new_state: The new state if transition is allowed, None otherwise
        reason: Human-readable explanation
    """
    request: TransitionRequest
    allowed: bool
    new_state: Optional[WorkflowState]
    reason: str


# Explicit transition table: (from_state, transition) -> to_state
# Only transitions in this table are valid
# HUMAN-only transitions are marked with requires_human() check
_TRANSITION_TABLE: dict[Tuple[WorkflowState, StateTransition], WorkflowState] = {
    # INIT transitions
    (WorkflowState.INIT, StateTransition.VALIDATE): WorkflowState.VALIDATED,
    (WorkflowState.INIT, StateTransition.ABORT): WorkflowState.ABORTED,
    
    # VALIDATED transitions
    (WorkflowState.VALIDATED, StateTransition.ESCALATE): WorkflowState.ESCALATED,
    (WorkflowState.VALIDATED, StateTransition.COMPLETE): WorkflowState.COMPLETED,
    (WorkflowState.VALIDATED, StateTransition.ABORT): WorkflowState.ABORTED,
    
    # ESCALATED transitions
    (WorkflowState.ESCALATED, StateTransition.APPROVE): WorkflowState.APPROVED,
    (WorkflowState.ESCALATED, StateTransition.REJECT): WorkflowState.REJECTED,
    (WorkflowState.ESCALATED, StateTransition.ABORT): WorkflowState.ABORTED,
    
    # APPROVED transitions
    (WorkflowState.APPROVED, StateTransition.COMPLETE): WorkflowState.COMPLETED,
    (WorkflowState.APPROVED, StateTransition.ABORT): WorkflowState.ABORTED,
}

# Transitions that require HUMAN even when the base transition allows SYSTEM
# (e.g., COMPLETE from VALIDATED requires HUMAN)
_CONTEXT_HUMAN_REQUIRED: FrozenSet[Tuple[WorkflowState, StateTransition]] = frozenset({
    (WorkflowState.VALIDATED, StateTransition.COMPLETE),
})


def attempt_transition(request: TransitionRequest) -> TransitionResponse:
    """
    Attempt a state transition based on explicit rules.
    
    Rules:
        1. Terminal states deny all transitions
        2. HUMAN can perform any valid transition in the table
        3. SYSTEM cannot perform APPROVE, REJECT, or ABORT
        4. SYSTEM cannot COMPLETE from VALIDATED (needs HUMAN)
        5. Unknown transitions are DENIED (deny-by-default)
    
    Args:
        request: The transition request
        
    Returns:
        TransitionResponse indicating if transition is allowed
    """
    current_state = request.current_state
    transition = request.transition
    actor_type = request.actor_type
    
    # Rule 1: Terminal states deny all transitions
    if is_terminal_state(current_state):
        return TransitionResponse(
            request=request,
            allowed=False,
            new_state=None,
            reason=f"Terminal state {current_state.name} does not allow transitions",
        )
    
    # Rule 5: Check if transition exists in table (deny-by-default)
    transition_key = (current_state, transition)
    if transition_key not in _TRANSITION_TABLE:
        return TransitionResponse(
            request=request,
            allowed=False,
            new_state=None,
            reason=f"Transition {transition.name} not valid from state {current_state.name}",
        )
    
    # Rule 3: SYSTEM cannot perform HUMAN-only transitions
    if actor_type == ActorType.SYSTEM and requires_human(transition):
        return TransitionResponse(
            request=request,
            allowed=False,
            new_state=None,
            reason=f"SYSTEM cannot perform {transition.name} - requires HUMAN",
        )
    
    # Rule 4: Context-specific HUMAN requirements
    if actor_type == ActorType.SYSTEM and transition_key in _CONTEXT_HUMAN_REQUIRED:
        return TransitionResponse(
            request=request,
            allowed=False,
            new_state=None,
            reason=f"SYSTEM cannot {transition.name} from {current_state.name} - requires HUMAN",
        )
    
    # Rule 2: Transition is allowed
    new_state = _TRANSITION_TABLE[transition_key]
    return TransitionResponse(
        request=request,
        allowed=True,
        new_state=new_state,
        reason=f"Transition {transition.name} allowed: {current_state.name} -> {new_state.name}",
    )
