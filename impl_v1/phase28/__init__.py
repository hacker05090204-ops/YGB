"""
impl_v1 Phase-28 Handshake Validation Mirror.

NON-AUTHORITATIVE MIRROR of governance Phase-28.
Contains ONLY data structures and validation logic.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT PERFORM HANDSHAKES.
THIS MODULE DOES NOT GRANT AUTHORITY.

CLOSED ENUMS:
- ExecutorIdentityStatus: 4 members
- HandshakeDecision: 2 members

FROZEN DATACLASSES:
- HandshakeContext: 6 fields
- HandshakeResult: 5 fields

ENGINE FUNCTIONS (VALIDATION ONLY):
- validate_executor_identity
- validate_envelope_hash
- validate_handshake_context
- decide_handshake
- is_handshake_valid

HANDSHAKE PROVES ELIGIBILITY.
IT NEVER GRANTS AUTHORITY.
"""
from .phase28_types import (
    ExecutorIdentityStatus,
    HandshakeDecision,
)
from .phase28_context import (
    HandshakeContext,
    HandshakeResult,
)
from .phase28_engine import (
    validate_executor_identity,
    validate_envelope_hash,
    validate_handshake_context,
    decide_handshake,
    is_handshake_valid,
)

__all__ = [
    # Types
    "ExecutorIdentityStatus",
    "HandshakeDecision",
    # Context
    "HandshakeContext",
    "HandshakeResult",
    # Engine
    "validate_executor_identity",
    "validate_envelope_hash",
    "validate_handshake_context",
    "decide_handshake",
    "is_handshake_valid",
]
