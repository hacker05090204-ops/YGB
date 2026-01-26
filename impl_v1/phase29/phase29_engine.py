"""
impl_v1 Phase-29 Execution Loop Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-29.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT EXECUTE INSTRUCTIONS.
THIS MODULE DOES NOT RUN LOOPS.
THIS MODULE DOES NOT CONTROL EXECUTORS.

VALIDATION FUNCTIONS ONLY:
- validate_loop_state
- validate_transition
- get_allowed_transitions
- get_next_state
- is_terminal_state

INVARIANTS:
- Loop DEFINES states, never executes
- Invalid transition → REJECT
- Any ambiguity → HALT
- Terminal state cannot transition
- Default = DENY

DENY-BY-DEFAULT:
- None → DENY
- Empty → DENY
- Invalid → DENY
"""
import re
from typing import Optional, FrozenSet

from .phase29_types import (
    ExecutionLoopState,
    LoopTransition,
)
from .phase29_context import (
    ExecutionLoopContext,
    LoopTransitionResult,
)


# Regex pattern for valid loop ID: LOOP-{8+ hex chars}
_LOOP_ID_PATTERN = re.compile(r'^LOOP-[a-fA-F0-9]{8,}$')

# Regex pattern for valid executor ID: EXECUTOR-{alphanumeric}
_EXECUTOR_ID_PATTERN = re.compile(r'^EXECUTOR-[a-zA-Z0-9_-]+$')

# State transition table from governance
# Maps (current_state, transition) -> next_state
_TRANSITION_TABLE: dict[tuple[ExecutionLoopState, LoopTransition], ExecutionLoopState] = {
    # From INITIALIZED
    (ExecutionLoopState.INITIALIZED, LoopTransition.INIT): ExecutionLoopState.READY,
    (ExecutionLoopState.INITIALIZED, LoopTransition.HALT): ExecutionLoopState.HALTED,
    # From READY
    (ExecutionLoopState.READY, LoopTransition.DISPATCH): ExecutionLoopState.DISPATCHED,
    (ExecutionLoopState.READY, LoopTransition.HALT): ExecutionLoopState.HALTED,
    # From DISPATCHED
    (ExecutionLoopState.DISPATCHED, LoopTransition.RECEIVE): ExecutionLoopState.AWAITING_RESPONSE,
    (ExecutionLoopState.DISPATCHED, LoopTransition.HALT): ExecutionLoopState.HALTED,
    # From AWAITING_RESPONSE
    (ExecutionLoopState.AWAITING_RESPONSE, LoopTransition.DISPATCH): ExecutionLoopState.DISPATCHED,
    (ExecutionLoopState.AWAITING_RESPONSE, LoopTransition.HALT): ExecutionLoopState.HALTED,
    # From HALTED (terminal - only can stay HALTED)
    (ExecutionLoopState.HALTED, LoopTransition.HALT): ExecutionLoopState.HALTED,
}

# Allowed transitions per state
_ALLOWED_TRANSITIONS: dict[ExecutionLoopState, frozenset[LoopTransition]] = {
    ExecutionLoopState.INITIALIZED: frozenset({LoopTransition.INIT, LoopTransition.HALT}),
    ExecutionLoopState.READY: frozenset({LoopTransition.DISPATCH, LoopTransition.HALT}),
    ExecutionLoopState.DISPATCHED: frozenset({LoopTransition.RECEIVE, LoopTransition.HALT}),
    ExecutionLoopState.AWAITING_RESPONSE: frozenset({LoopTransition.DISPATCH, LoopTransition.HALT}),
    ExecutionLoopState.HALTED: frozenset({LoopTransition.HALT}),  # Terminal - only HALT allowed
}


def validate_loop_state(context: Optional[ExecutionLoopContext]) -> bool:
    """Validate an execution loop context.
    
    Args:
        context: ExecutionLoopContext to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Missing required fields → False
        - Invalid loop_id format → False
        - Invalid executor_id format → False
        - Invalid current_state → False
        - Negative iteration_count → False
    """
    # DENY-BY-DEFAULT: None
    if context is None:
        return False
    
    # Validate loop_id format
    if not context.loop_id or not isinstance(context.loop_id, str):
        return False
    if not _LOOP_ID_PATTERN.match(context.loop_id):
        return False
    
    # Validate current_state is ExecutionLoopState
    if not isinstance(context.current_state, ExecutionLoopState):
        return False
    
    # Validate executor_id format
    if not context.executor_id or not isinstance(context.executor_id, str):
        return False
    if not _EXECUTOR_ID_PATTERN.match(context.executor_id):
        return False
    
    # Validate envelope_hash
    if not context.envelope_hash or not isinstance(context.envelope_hash, str):
        return False
    if not context.envelope_hash.strip():
        return False
    
    # Validate created_at
    if not context.created_at or not isinstance(context.created_at, str):
        return False
    if not context.created_at.strip():
        return False
    
    # Validate iteration_count is non-negative
    if not isinstance(context.iteration_count, int):
        return False
    if context.iteration_count < 0:
        return False
    
    return True


def validate_transition(
    context: Optional[ExecutionLoopContext],
    transition: Optional[LoopTransition]
) -> LoopTransitionResult:
    """Validate a transition from current context state.
    
    Args:
        context: Current loop context
        transition: Proposed transition
        
    Returns:
        LoopTransitionResult with validation outcome
        
    Rules:
        - DENY-BY-DEFAULT
        - None context → Invalid (HALT)
        - Invalid context → Invalid (HALT)
        - None transition → Invalid (HALT)
        - Non-LoopTransition → Invalid (HALT)
        - Invalid transition from state → Invalid (HALT)
        - Terminal state (HALTED) can only HALT
    """
    # DENY-BY-DEFAULT: None context
    if context is None:
        return LoopTransitionResult(
            transition=LoopTransition.HALT,
            from_state=ExecutionLoopState.HALTED,
            to_state=ExecutionLoopState.HALTED,
            is_valid=False,
            reason="Context is None - defaulting to HALT"
        )
    
    # DENY-BY-DEFAULT: Invalid context
    if not validate_loop_state(context):
        return LoopTransitionResult(
            transition=LoopTransition.HALT,
            from_state=ExecutionLoopState.HALTED,
            to_state=ExecutionLoopState.HALTED,
            is_valid=False,
            reason="Context is invalid - defaulting to HALT"
        )
    
    # DENY-BY-DEFAULT: None transition
    if transition is None:
        return LoopTransitionResult(
            transition=LoopTransition.HALT,
            from_state=context.current_state,
            to_state=ExecutionLoopState.HALTED,
            is_valid=False,
            reason="Transition is None - defaulting to HALT"
        )
    
    # DENY-BY-DEFAULT: Non-LoopTransition
    if not isinstance(transition, LoopTransition):
        return LoopTransitionResult(
            transition=LoopTransition.HALT,
            from_state=context.current_state,
            to_state=ExecutionLoopState.HALTED,
            is_valid=False,
            reason="Invalid transition type - defaulting to HALT"
        )
    
    # Look up transition in table
    key = (context.current_state, transition)
    next_state = _TRANSITION_TABLE.get(key)
    
    if next_state is None:
        # Invalid transition - HALT
        return LoopTransitionResult(
            transition=transition,
            from_state=context.current_state,
            to_state=ExecutionLoopState.HALTED,
            is_valid=False,
            reason=f"Transition {transition.name} not allowed from {context.current_state.name}"
        )
    
    # Valid transition
    return LoopTransitionResult(
        transition=transition,
        from_state=context.current_state,
        to_state=next_state,
        is_valid=True,
        reason=f"Valid transition: {context.current_state.name} -> {next_state.name}"
    )


def get_allowed_transitions(
    state: Optional[ExecutionLoopState]
) -> FrozenSet[LoopTransition]:
    """Get allowed transitions from a given state.
    
    Args:
        state: Current execution loop state
        
    Returns:
        FrozenSet of allowed transitions, empty if invalid
        
    Rules:
        - DENY-BY-DEFAULT
        - None → empty frozenset
        - Non-ExecutionLoopState → empty frozenset
        - Valid state → allowed transitions
    """
    # DENY-BY-DEFAULT: None
    if state is None:
        return frozenset()
    
    # DENY-BY-DEFAULT: Non-ExecutionLoopState
    if not isinstance(state, ExecutionLoopState):
        return frozenset()
    
    return _ALLOWED_TRANSITIONS.get(state, frozenset())


def get_next_state(
    current_state: Optional[ExecutionLoopState],
    transition: Optional[LoopTransition]
) -> ExecutionLoopState:
    """Get next state for a transition.
    
    Args:
        current_state: Current loop state
        transition: Proposed transition
        
    Returns:
        Next state, or HALTED if invalid
        
    Rules:
        - DENY-BY-DEFAULT
        - None current_state → HALTED
        - Non-ExecutionLoopState → HALTED
        - None transition → HALTED
        - Non-LoopTransition → HALTED
        - Invalid transition → HALTED
        - Valid transition → next state
    """
    # DENY-BY-DEFAULT: None current_state
    if current_state is None:
        return ExecutionLoopState.HALTED
    
    # DENY-BY-DEFAULT: Non-ExecutionLoopState
    if not isinstance(current_state, ExecutionLoopState):
        return ExecutionLoopState.HALTED
    
    # DENY-BY-DEFAULT: None transition
    if transition is None:
        return ExecutionLoopState.HALTED
    
    # DENY-BY-DEFAULT: Non-LoopTransition
    if not isinstance(transition, LoopTransition):
        return ExecutionLoopState.HALTED
    
    # Look up next state
    key = (current_state, transition)
    return _TRANSITION_TABLE.get(key, ExecutionLoopState.HALTED)


def is_terminal_state(state: Optional[ExecutionLoopState]) -> bool:
    """Check if a state is terminal (HALTED).
    
    Args:
        state: State to check
        
    Returns:
        True if terminal, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT (means NOT terminal for None/invalid)
        - None → False
        - Non-ExecutionLoopState → False
        - HALTED → True
        - Any other state → False
    """
    # DENY-BY-DEFAULT: None
    if state is None:
        return False
    
    # DENY-BY-DEFAULT: Non-ExecutionLoopState
    if not isinstance(state, ExecutionLoopState):
        return False
    
    return state == ExecutionLoopState.HALTED
