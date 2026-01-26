"""
impl_v1 Phase-30 Response Engine.

NON-AUTHORITATIVE MIRROR of governance Phase-30.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE DOES NOT EXECUTE RESPONSES.
THIS MODULE DOES NOT MODIFY STATE.

VALIDATION FUNCTIONS ONLY:
- validate_executor_response
- normalize_response
- evaluate_response_trust
- decide_response_outcome

INVARIANTS:
- Executor output is DATA, not truth
- Confidence never reaches 1.0 without human
- TIMEOUT → FAILURE → REJECT
- PARTIAL → ESCALATE
- Unknown → REJECT

DENY-BY-DEFAULT:
- None → REJECT
- Empty → REJECT
- Invalid → REJECT
"""
import re
from typing import Optional

from .phase30_types import (
    ExecutorResponseType,
    ResponseDecision,
)
from .phase30_context import (
    ExecutorRawResponse,
    NormalizedExecutionResult,
)


# Regex pattern for valid response ID: RESPONSE-{8+ hex chars}
_RESPONSE_ID_PATTERN = re.compile(r'^RESPONSE-[a-fA-F0-9]{8,}$')

# Regex pattern for valid result ID: RESULT-{8+ hex chars}
_RESULT_ID_PATTERN = re.compile(r'^RESULT-[a-fA-F0-9]{8,}$')

# Regex pattern for valid executor ID: EXECUTOR-{alphanumeric}
_EXECUTOR_ID_PATTERN = re.compile(r'^EXECUTOR-[a-zA-Z0-9_-]+$')

# Decision table from governance
_DECISION_TABLE: dict[ExecutorResponseType, tuple[ResponseDecision, float]] = {
    ExecutorResponseType.SUCCESS: (ResponseDecision.ACCEPT, 0.85),
    ExecutorResponseType.FAILURE: (ResponseDecision.REJECT, 0.30),
    ExecutorResponseType.TIMEOUT: (ResponseDecision.REJECT, 0.20),
    ExecutorResponseType.PARTIAL: (ResponseDecision.ESCALATE, 0.50),
    ExecutorResponseType.MALFORMED: (ResponseDecision.REJECT, 0.10),
}


def validate_executor_response(response: Optional[ExecutorRawResponse]) -> bool:
    """Validate an executor raw response.
    
    Args:
        response: ExecutorRawResponse to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Missing required fields → False
        - Invalid response_id format → False
        - Invalid executor_id format → False
        - Invalid response_type → False
        - Negative elapsed_ms → False
    """
    # DENY-BY-DEFAULT: None
    if response is None:
        return False
    
    # Validate response_id format
    if not response.response_id or not isinstance(response.response_id, str):
        return False
    if not _RESPONSE_ID_PATTERN.match(response.response_id):
        return False
    
    # Validate executor_id format
    if not response.executor_id or not isinstance(response.executor_id, str):
        return False
    if not _EXECUTOR_ID_PATTERN.match(response.executor_id):
        return False
    
    # Validate response_type is ExecutorResponseType
    if not isinstance(response.response_type, ExecutorResponseType):
        return False
    
    # Validate raw_data is bytes
    if not isinstance(response.raw_data, bytes):
        return False
    
    # Validate timestamp
    if not response.timestamp or not isinstance(response.timestamp, str):
        return False
    if not response.timestamp.strip():
        return False
    
    # Validate elapsed_ms is non-negative
    if not isinstance(response.elapsed_ms, int):
        return False
    if response.elapsed_ms < 0:
        return False
    
    return True


def normalize_response(
    response: Optional[ExecutorRawResponse],
    result_id: str
) -> Optional[NormalizedExecutionResult]:
    """Normalize an executor response to a result.
    
    Args:
        response: ExecutorRawResponse to normalize
        result_id: ID for the resulting NormalizedExecutionResult
        
    Returns:
        NormalizedExecutionResult if valid, None otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None response → None
        - Invalid response → None
        - Invalid result_id → None
        - Uses decision table from governance
    """
    # DENY-BY-DEFAULT: None response
    if response is None:
        return None
    
    # DENY-BY-DEFAULT: Invalid response
    if not validate_executor_response(response):
        return None
    
    # DENY-BY-DEFAULT: Invalid result_id
    if not result_id or not isinstance(result_id, str):
        return None
    if not _RESULT_ID_PATTERN.match(result_id):
        return None
    
    # Get decision and confidence from table
    decision, confidence = _DECISION_TABLE.get(
        response.response_type,
        (ResponseDecision.REJECT, 0.10)  # Unknown defaults to REJECT
    )
    
    # Determine if human review is required
    requires_human = decision == ResponseDecision.ESCALATE
    
    # Build reason based on response type
    reason = _build_reason(response.response_type, decision)
    
    return NormalizedExecutionResult(
        result_id=result_id,
        response_id=response.response_id,
        response_type=response.response_type,
        decision=decision,
        confidence=confidence,
        reason=reason,
        requires_human=requires_human
    )


def _build_reason(
    response_type: ExecutorResponseType,
    decision: ResponseDecision
) -> str:
    """Build human-readable reason for decision.
    
    This is a PURE internal function.
    """
    reasons = {
        ExecutorResponseType.SUCCESS: "Executor completed successfully",
        ExecutorResponseType.FAILURE: "Executor reported failure",
        ExecutorResponseType.TIMEOUT: "Executor timed out - treating as failure",
        ExecutorResponseType.PARTIAL: "Executor returned partial result - requires human review",
        ExecutorResponseType.MALFORMED: "Executor returned malformed data",
    }
    return reasons.get(response_type, "Unknown response type")


def evaluate_response_trust(
    result: Optional[NormalizedExecutionResult]
) -> float:
    """Evaluate trust level for a normalized result.
    
    Args:
        result: NormalizedExecutionResult to evaluate
        
    Returns:
        Trust score (0.0 to < 1.0, NEVER 1.0 without human)
        
    Rules:
        - DENY-BY-DEFAULT
        - None → 0.0
        - Invalid result → 0.0
        - Confidence is never 1.0 without human confirmation
        - Trust = min(confidence, 0.99)
    """
    # DENY-BY-DEFAULT: None
    if result is None:
        return 0.0
    
    # DENY-BY-DEFAULT: Invalid result_id
    if not result.result_id or not isinstance(result.result_id, str):
        return 0.0
    if not _RESULT_ID_PATTERN.match(result.result_id):
        return 0.0
    
    # DENY-BY-DEFAULT: Invalid response_type
    if not isinstance(result.response_type, ExecutorResponseType):
        return 0.0
    
    # DENY-BY-DEFAULT: Invalid decision
    if not isinstance(result.decision, ResponseDecision):
        return 0.0
    
    # Confidence is NEVER 1.0 without human confirmation
    # Return min(confidence, 0.99) to enforce this invariant
    if not isinstance(result.confidence, (int, float)):
        return 0.0
    
    return min(float(result.confidence), 0.99)


def decide_response_outcome(
    response: Optional[ExecutorRawResponse]
) -> ResponseDecision:
    """Decide outcome for an executor response.
    
    Args:
        response: ExecutorRawResponse to decide on
        
    Returns:
        ResponseDecision for this response
        
    Rules:
        - DENY-BY-DEFAULT → REJECT
        - None → REJECT
        - Invalid → REJECT
        - SUCCESS → ACCEPT
        - FAILURE → REJECT
        - TIMEOUT → REJECT
        - PARTIAL → ESCALATE
        - MALFORMED → REJECT
        - Unknown → REJECT
    """
    # DENY-BY-DEFAULT: None → REJECT
    if response is None:
        return ResponseDecision.REJECT
    
    # DENY-BY-DEFAULT: Invalid → REJECT
    if not validate_executor_response(response):
        return ResponseDecision.REJECT
    
    # Get decision from table
    decision, _ = _DECISION_TABLE.get(
        response.response_type,
        (ResponseDecision.REJECT, 0.10)  # Unknown defaults to REJECT
    )
    
    return decision
