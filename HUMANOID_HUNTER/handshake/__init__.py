"""
Phase-28 Executor Handshake & Runtime Contract Validation.

This module provides executor handshake governance.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE BROWSERS.
IT DOES NOT INVOKE SUBPROCESSES.
IT DOES NOT MAKE NETWORK CALLS.

CORE PRINCIPLES:
- Handshake proves eligibility
- It never grants authority
- Executors never gain authority
- Any ambiguity → REJECT

Exports:
    Enums (CLOSED):
        ExecutorIdentityStatus: UNKNOWN, REGISTERED, REVOKED
        HandshakeDecision: ACCEPT, REJECT
    
    Dataclasses (all frozen=True):
        ExecutorIdentity: Executor identity
        HandshakeContext: Handshake context
        HandshakeResult: Handshake result
    
    Functions (pure, deterministic):
        validate_executor_identity: Validate identity
        validate_instruction_binding: Validate binding
        decide_handshake: Make handshake decision
"""
from .handshake_types import (
    ExecutorIdentityStatus,
    HandshakeDecision
)
from .handshake_context import (
    ExecutorIdentity,
    HandshakeContext,
    HandshakeResult
)
from .handshake_engine import (
    validate_executor_identity,
    validate_instruction_binding,
    decide_handshake
)

__all__ = [
    # Enums
    "ExecutorIdentityStatus",
    "HandshakeDecision",
    # Dataclasses
    "ExecutorIdentity",
    "HandshakeContext",
    "HandshakeResult",
    # Functions
    "validate_executor_identity",
    "validate_instruction_binding",
    "decide_handshake",
]
