"""
Phase-30 Response Engine.

This module provides executor response governance functions.

All functions are pure (no side effects).
All decisions are deny-by-default.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.

CORE RULES:
- Executor output is DATA, not truth
- Governance decides, not executors
- Confidence is never 1.0 without human confirmation
"""
from .response_types import ExecutorResponseType, ResponseDecision
from .response_context import ExecutorRawResponse, NormalizedExecutionResult


# Confidence scores by response type (all < 1.0)
_CONFIDENCE_SCORES = {
    ExecutorResponseType.SUCCESS: 0.85,    # High but not certain
    ExecutorResponseType.FAILURE: 0.30,    # Low confidence 
    ExecutorResponseType.TIMEOUT: 0.20,    # Very low
    ExecutorResponseType.PARTIAL: 0.50,    # Medium
    ExecutorResponseType.MALFORMED: 0.10,  # Almost none
}


def decide_response_outcome(
    response_type: ExecutorResponseType
) -> ResponseDecision:
    """Decide response outcome based on type.
    
    Args:
        response_type: The ExecutorResponseType
        
    Returns:
        ResponseDecision: ACCEPT, REJECT, or ESCALATE
        
    Rules:
        - SUCCESS → ACCEPT (but confidence < 1.0)
        - FAILURE → REJECT
        - TIMEOUT → REJECT (treated as FAILURE)
        - PARTIAL → ESCALATE (needs human)
        - MALFORMED → REJECT
    """
    if response_type == ExecutorResponseType.SUCCESS:
        return ResponseDecision.ACCEPT
    
    if response_type == ExecutorResponseType.PARTIAL:
        return ResponseDecision.ESCALATE
    
    # FAILURE, TIMEOUT, MALFORMED → REJECT
    return ResponseDecision.REJECT


def evaluate_response_trust(
    response_type: ExecutorResponseType
) -> float:
    """Evaluate trust level for response type.
    
    Args:
        response_type: The ExecutorResponseType
        
    Returns:
        float: Confidence score 0.0 <= x < 1.0
        
    Rules:
        - Executor cannot self-report SUCCESS as truth
        - Confidence is derived from governance rules only
        - Confidence is ALWAYS < 1.0
    """
    return _CONFIDENCE_SCORES.get(response_type, 0.0)


def normalize_executor_response(
    raw: ExecutorRawResponse,
    expected_hash: str
) -> NormalizedExecutionResult:
    """Normalize an executor response.
    
    Args:
        raw: ExecutorRawResponse from executor
        expected_hash: Expected instruction hash
        
    Returns:
        NormalizedExecutionResult with decision, reason, confidence
        
    Rules:
        - Missing executor_id → MALFORMED → REJECT
        - Missing instruction_hash → MALFORMED → REJECT
        - Hash mismatch → REJECT
        - Never parse raw_payload
    """
    # Check for malformed: empty executor_id
    if not raw.executor_id or not raw.executor_id.strip():
        return NormalizedExecutionResult(
            decision=ResponseDecision.REJECT,
            reason="MALFORMED: Missing or empty executor_id",
            confidence_score=0.0
        )
    
    # Check for malformed: empty instruction_hash
    if not raw.instruction_hash or not raw.instruction_hash.strip():
        return NormalizedExecutionResult(
            decision=ResponseDecision.REJECT,
            reason="MALFORMED: Missing or empty instruction_hash",
            confidence_score=0.0
        )
    
    # Check for instruction hash mismatch
    if raw.instruction_hash != expected_hash:
        return NormalizedExecutionResult(
            decision=ResponseDecision.REJECT,
            reason=f"Instruction hash mismatch: expected {expected_hash}, got {raw.instruction_hash}",
            confidence_score=0.0
        )
    
    # Check for MALFORMED response type
    if raw.reported_status == ExecutorResponseType.MALFORMED:
        return NormalizedExecutionResult(
            decision=ResponseDecision.REJECT,
            reason="Executor reported MALFORMED response",
            confidence_score=evaluate_response_trust(raw.reported_status)
        )
    
    # Normal processing
    decision = decide_response_outcome(raw.reported_status)
    confidence = evaluate_response_trust(raw.reported_status)
    
    # Generate reason based on response type
    reason_map = {
        ExecutorResponseType.SUCCESS: "Executor reported success (requires verification)",
        ExecutorResponseType.FAILURE: "Executor reported failure",
        ExecutorResponseType.TIMEOUT: "Executor timed out",
        ExecutorResponseType.PARTIAL: "Executor reported partial completion - escalating to human",
        ExecutorResponseType.MALFORMED: "Executor response is malformed",
    }
    
    reason = reason_map.get(raw.reported_status, "Unknown response type")
    
    return NormalizedExecutionResult(
        decision=decision,
        reason=reason,
        confidence_score=confidence
    )
