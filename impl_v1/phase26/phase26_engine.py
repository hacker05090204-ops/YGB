"""
impl_v1 Phase-26 Execution Readiness Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-26.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT START EXECUTION.
THIS MODULE ONLY EVALUATES READINESS.

VALIDATION FUNCTIONS ONLY:
- validate_readiness_context
- evaluate_readiness
- get_readiness_status
- get_blockers
- is_execution_ready

INVARIANTS:
- READY requires ALL conditions true
- Any missing condition → NOT_READY
- Any violation → BLOCKED
- Default = BLOCKED

DENY-BY-DEFAULT:
- None → BLOCKED
- Invalid → BLOCKED
"""
from typing import Optional, Tuple

from .phase26_types import ReadinessStatus, ReadinessBlocker
from .phase26_context import (
    ExecutionReadinessContext,
    ReadinessResult,
)


def validate_readiness_context(
    context: Optional[ExecutionReadinessContext]
) -> bool:
    """Validate an execution readiness context.
    
    Args:
        context: ExecutionReadinessContext to validate
        
    Returns:
        True if valid structure, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Non-bool fields → False
    """
    # DENY-BY-DEFAULT: None
    if context is None:
        return False
    
    # Validate all fields are bools
    if not isinstance(context.authorization_ok, bool):
        return False
    if not isinstance(context.intent_bound, bool):
        return False
    if not isinstance(context.handshake_valid, bool):
        return False
    if not isinstance(context.observation_valid, bool):
        return False
    if not isinstance(context.human_decision_final, bool):
        return False
    
    return True


def evaluate_readiness(
    context: Optional[ExecutionReadinessContext],
    timestamp: str = ""
) -> ReadinessResult:
    """Evaluate execution readiness based on context.
    
    Args:
        context: ExecutionReadinessContext to evaluate
        timestamp: Timestamp of evaluation (ISO-8601)
        
    Returns:
        ReadinessResult with evaluation outcome
        
    Rules:
        - DENY-BY-DEFAULT → BLOCKED
        - None context → BLOCKED
        - Invalid context → BLOCKED
        - Any condition False → NOT_READY with blockers
        - All conditions True → READY
    """
    # DENY-BY-DEFAULT: None context
    if context is None:
        return ReadinessResult(
            status=ReadinessStatus.BLOCKED,
            blockers=(
                ReadinessBlocker.MISSING_AUTHORIZATION,
                ReadinessBlocker.MISSING_INTENT,
                ReadinessBlocker.HANDSHAKE_FAILED,
                ReadinessBlocker.OBSERVATION_INVALID,
                ReadinessBlocker.HUMAN_DECISION_PENDING,
            ),
            evaluated_at=timestamp
        )
    
    # DENY-BY-DEFAULT: Invalid context
    if not validate_readiness_context(context):
        return ReadinessResult(
            status=ReadinessStatus.BLOCKED,
            blockers=(
                ReadinessBlocker.MISSING_AUTHORIZATION,
                ReadinessBlocker.MISSING_INTENT,
                ReadinessBlocker.HANDSHAKE_FAILED,
                ReadinessBlocker.OBSERVATION_INVALID,
                ReadinessBlocker.HUMAN_DECISION_PENDING,
            ),
            evaluated_at=timestamp
        )
    
    # Collect blockers
    blockers: list[ReadinessBlocker] = []
    
    if not context.authorization_ok:
        blockers.append(ReadinessBlocker.MISSING_AUTHORIZATION)
    
    if not context.intent_bound:
        blockers.append(ReadinessBlocker.MISSING_INTENT)
    
    if not context.handshake_valid:
        blockers.append(ReadinessBlocker.HANDSHAKE_FAILED)
    
    if not context.observation_valid:
        blockers.append(ReadinessBlocker.OBSERVATION_INVALID)
    
    if not context.human_decision_final:
        blockers.append(ReadinessBlocker.HUMAN_DECISION_PENDING)
    
    # Determine status
    if blockers:
        return ReadinessResult(
            status=ReadinessStatus.NOT_READY,
            blockers=tuple(blockers),
            evaluated_at=timestamp
        )
    
    # All conditions met → READY
    return ReadinessResult(
        status=ReadinessStatus.READY,
        blockers=(),
        evaluated_at=timestamp
    )


def get_readiness_status(
    result: Optional[ReadinessResult]
) -> ReadinessStatus:
    """Get readiness status from result.
    
    Args:
        result: ReadinessResult to check
        
    Returns:
        ReadinessStatus
        
    Rules:
        - DENY-BY-DEFAULT → BLOCKED
        - None → BLOCKED
        - Invalid status type → BLOCKED
        - Valid result → result's status
    """
    # DENY-BY-DEFAULT: None
    if result is None:
        return ReadinessStatus.BLOCKED
    
    # DENY-BY-DEFAULT: Invalid status type
    if not isinstance(result.status, ReadinessStatus):
        return ReadinessStatus.BLOCKED
    
    return result.status


def get_blockers(
    result: Optional[ReadinessResult]
) -> Tuple[ReadinessBlocker, ...]:
    """Get blockers from readiness result.
    
    Args:
        result: ReadinessResult to check
        
    Returns:
        Tuple of blockers (all blockers if invalid)
        
    Rules:
        - DENY-BY-DEFAULT → all blockers
        - None → all blockers
        - Invalid blockers type → all blockers
        - Valid result → result's blockers
    """
    all_blockers = (
        ReadinessBlocker.MISSING_AUTHORIZATION,
        ReadinessBlocker.MISSING_INTENT,
        ReadinessBlocker.HANDSHAKE_FAILED,
        ReadinessBlocker.OBSERVATION_INVALID,
        ReadinessBlocker.HUMAN_DECISION_PENDING,
    )
    
    # DENY-BY-DEFAULT: None
    if result is None:
        return all_blockers
    
    # DENY-BY-DEFAULT: Invalid blockers type
    if not isinstance(result.blockers, tuple):
        return all_blockers
    
    # Validate all items are ReadinessBlocker
    for blocker in result.blockers:
        if not isinstance(blocker, ReadinessBlocker):
            return all_blockers
    
    return result.blockers


def is_execution_ready(result: Optional[ReadinessResult]) -> bool:
    """Check if execution is ready.
    
    Args:
        result: ReadinessResult to check
        
    Returns:
        True only if READY, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - NOT_READY → False
        - BLOCKED → False
        - READY → True
    """
    # DENY-BY-DEFAULT: None
    if result is None:
        return False
    
    # DENY-BY-DEFAULT: Invalid status type
    if not isinstance(result.status, ReadinessStatus):
        return False
    
    return result.status == ReadinessStatus.READY
