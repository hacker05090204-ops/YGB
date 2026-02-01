"""
Phase-30 Executor Response Governance & Result Normalization.

This module provides executor response governance.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE BROWSERS.
IT DOES NOT INVOKE SUBPROCESSES.
IT DOES NOT MAKE NETWORK CALLS.

CORE PRINCIPLES:
- Executor output is DATA, not truth
- Governance decides, not executors
- Confidence is never 1.0 without human confirmation
- Humans remain authority

Exports:
    Enums (CLOSED):
        ExecutorResponseType: SUCCESS, FAILURE, TIMEOUT, PARTIAL, MALFORMED
        ResponseDecision: ACCEPT, REJECT, ESCALATE
    
    Dataclasses (all frozen=True):
        ExecutorRawResponse: Raw executor response
        NormalizedExecutionResult: Normalized result with decision
    
    Functions (pure, deterministic):
        normalize_executor_response: Normalize response
        evaluate_response_trust: Evaluate trust level
        decide_response_outcome: Decide outcome
"""
from .response_types import (
    ExecutorResponseType,
    ResponseDecision
)
from .response_context import (
    ExecutorRawResponse,
    NormalizedExecutionResult
)
from .response_engine import (
    normalize_executor_response,
    evaluate_response_trust,
    decide_response_outcome
)

__all__ = [
    # Enums
    "ExecutorResponseType",
    "ResponseDecision",
    # Dataclasses
    "ExecutorRawResponse",
    "NormalizedExecutionResult",
    # Functions
    "normalize_executor_response",
    "evaluate_response_trust",
    "decide_response_outcome",
]
