"""
Phase-16 Execution Boundary & Browser Invocation Authority.

This module provides execution permission decisions.

THIS IS A PERMISSION LAYER ONLY.
IT DOES NOT EXECUTE BROWSERS.
IT DOES NOT CALL SUBPROCESSES.
IT DOES NOT MAKE NETWORK CALLS.

Exports:
    Enums:
        ExecutionPermission: ALLOWED, DENIED
    
    Dataclasses (all frozen=True):
        ExecutionContext: Context for permission decision
        ExecutionDecision: Final decision
    
    Constants:
        VALID_READINESS_STATES: Valid readiness state values
        HUMAN_PRESENCE_VALUES: Valid human presence values
    
    Functions:
        check_handoff_signals: Check Phase-13 signals
        check_contract_signals: Check Phase-15 signals
        check_human_present: Check human presence
        decide_execution: Make final decision
"""
from .execution_types import (
    ExecutionPermission,
    VALID_READINESS_STATES,
    HUMAN_PRESENCE_VALUES
)
from .execution_context import ExecutionContext, ExecutionDecision
from .execution_engine import (
    check_handoff_signals,
    check_contract_signals,
    check_human_present,
    decide_execution
)

__all__ = [
    # Enums
    "ExecutionPermission",
    # Dataclasses
    "ExecutionContext",
    "ExecutionDecision",
    # Constants
    "VALID_READINESS_STATES",
    "HUMAN_PRESENCE_VALUES",
    # Functions
    "check_handoff_signals",
    "check_contract_signals",
    "check_human_present",
    "decide_execution",
]
