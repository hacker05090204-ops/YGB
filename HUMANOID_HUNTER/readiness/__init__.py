"""
Phase-26 Execution Readiness & Pre-Execution Gatekeeping.

This module provides execution readiness governance.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE BROWSERS.
IT DOES NOT INVOKE SUBPROCESSES.
IT DOES NOT MAKE NETWORK CALLS.

CORE PRINCIPLES:
- Readiness decides IF execution may occur
- Execution never decides readiness
- Missing dependency → BLOCK
- Any ambiguity → BLOCK

Exports:
    Enums (CLOSED):
        ExecutionReadinessState: READY, NOT_READY
        ReadinessDecision: ALLOW, BLOCK
    
    Dataclasses (all frozen=True):
        ReadinessContext: Readiness context
        ReadinessResult: Readiness result
    
    Functions (pure, deterministic):
        validate_readiness_inputs: Validate all inputs
        evaluate_execution_readiness: Evaluate readiness
        decide_readiness: Make final decision
"""
from .readiness_types import (
    ExecutionReadinessState,
    ReadinessDecision
)
from .readiness_context import (
    ReadinessContext,
    ReadinessResult
)
from .readiness_engine import (
    validate_readiness_inputs,
    evaluate_execution_readiness,
    decide_readiness
)

__all__ = [
    # Enums
    "ExecutionReadinessState",
    "ReadinessDecision",
    # Dataclasses
    "ReadinessContext",
    "ReadinessResult",
    # Functions
    "validate_readiness_inputs",
    "evaluate_execution_readiness",
    "decide_readiness",
]
