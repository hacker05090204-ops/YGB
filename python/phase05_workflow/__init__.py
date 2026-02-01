"""
Phase-05: Workflow State Model
REIMPLEMENTED-2026

Pure workflow state machine for controlling action lifecycle.
No execution logic - state transitions only.

Exports:
    - WorkflowState: Enum of workflow states
    - StateTransition: Enum of valid transitions
    - TransitionRequest: Frozen dataclass for transition requests
    - TransitionResponse: Frozen dataclass for transition responses
    - attempt_transition: Pure function to attempt state transitions
    - is_terminal_state: Check if a state is terminal
    - requires_human: Check if a transition requires HUMAN actor
"""

from python.phase05_workflow.states import WorkflowState, is_terminal_state
from python.phase05_workflow.transitions import StateTransition, requires_human
from python.phase05_workflow.state_machine import (
    TransitionRequest,
    TransitionResponse,
    attempt_transition,
)

__all__ = [
    "WorkflowState",
    "StateTransition",
    "TransitionRequest",
    "TransitionResponse",
    "attempt_transition",
    "is_terminal_state",
    "requires_human",
]
