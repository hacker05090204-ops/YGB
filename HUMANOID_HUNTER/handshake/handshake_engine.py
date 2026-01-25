"""
Phase-28 Handshake Engine.

This module provides handshake validation functions.

All functions are pure (no side effects).
All decisions are deny-by-default.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.

CORE RULES:
- Handshake proves eligibility
- It never grants authority
- Executors never gain authority
- Any ambiguity → REJECT
"""
from typing import Optional

from .handshake_types import ExecutorIdentityStatus, HandshakeDecision
from .handshake_context import (
    ExecutorIdentity,
    HandshakeContext,
    HandshakeResult
)


def validate_executor_identity(identity: ExecutorIdentity) -> bool:
    """Validate executor identity.
    
    Args:
        identity: ExecutorIdentity to validate
        
    Returns:
        True if identity is valid, False otherwise
        
    Rules:
        - REGISTERED → valid
        - UNKNOWN → invalid
        - REVOKED → invalid
    """
    return identity.trust_status == ExecutorIdentityStatus.REGISTERED


def validate_instruction_binding(
    context: HandshakeContext,
    expected_hash: str
) -> bool:
    """Validate instruction envelope binding.
    
    Args:
        context: HandshakeContext with envelope hash
        expected_hash: Expected envelope hash
        
    Returns:
        True if hashes match, False otherwise
    """
    return context.instruction_envelope_hash == expected_hash


def decide_handshake(
    context: Optional[HandshakeContext],
    expected_envelope_hash: str
) -> HandshakeResult:
    """Make handshake decision.
    
    Args:
        context: HandshakeContext
        expected_envelope_hash: Expected envelope hash
        
    Returns:
        HandshakeResult with decision and reason
        
    Rules:
        1. None context → REJECT
        2. Invalid identity → REJECT
        3. Hash mismatch → REJECT
        4. All checks pass → ACCEPT
        
    DENY-BY-DEFAULT: Any unclear condition → REJECT
    """
    # 1. None context → REJECT
    if context is None:
        return HandshakeResult(
            decision=HandshakeDecision.REJECT,
            reason="Context is None"
        )
    
    # 2. Validate identity
    if not validate_executor_identity(context.executor_identity):
        return HandshakeResult(
            decision=HandshakeDecision.REJECT,
            reason=f"Identity not valid (status: {context.executor_identity.trust_status.name})"
        )
    
    # 3. Validate instruction binding
    if not validate_instruction_binding(context, expected_envelope_hash):
        return HandshakeResult(
            decision=HandshakeDecision.REJECT,
            reason="Envelope hash mismatch"
        )
    
    # 4. All checks passed → ACCEPT
    return HandshakeResult(
        decision=HandshakeDecision.ACCEPT,
        reason="Handshake validated"
    )
