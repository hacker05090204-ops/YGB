"""
Phase-22 Native Engine.

This module provides native runtime isolation functions.

All functions are pure (no side effects).
All decisions are deny-by-default.

NATIVE CODE MAY RUN.
NATIVE CODE MAY FAIL.
NATIVE CODE MAY LIE.
GOVERNANCE NEVER DOES.
"""
from .native_types import (
    NativeProcessState,
    NativeExitReason,
    IsolationDecision,
    TERMINAL_STATES,
    INVALID_STATES
)
from .native_context import (
    NativeExecutionContext,
    NativeExecutionResult,
    IsolationDecisionResult
)


def classify_native_exit(
    exit_code: int,
    process_state: NativeProcessState
) -> NativeExitReason:
    """Classify native exit reason.
    
    Args:
        exit_code: OS exit code
        process_state: Native process state
        
    Returns:
        NativeExitReason
    """
    # PENDING / RUNNING → UNKNOWN
    if process_state in INVALID_STATES:
        return NativeExitReason.UNKNOWN
    
    # CRASHED → CRASH
    if process_state == NativeProcessState.CRASHED:
        return NativeExitReason.CRASH
    
    # TIMED_OUT → TIMEOUT
    if process_state == NativeProcessState.TIMED_OUT:
        return NativeExitReason.TIMEOUT
    
    # KILLED → KILLED
    if process_state == NativeProcessState.KILLED:
        return NativeExitReason.KILLED
    
    # EXITED → check exit code
    # All enum values are covered above, this is the only remaining case
    if exit_code == 0:
        return NativeExitReason.NORMAL
    return NativeExitReason.ERROR


def is_native_result_valid(result: NativeExecutionResult) -> bool:
    """Check if native result is valid.
    
    Args:
        result: Native execution result
        
    Returns:
        True if result is from a terminal state
    """
    return result.process_state in TERMINAL_STATES


def evaluate_isolation_result(result: NativeExecutionResult) -> IsolationDecision:
    """Evaluate result and return isolation decision.
    
    Args:
        result: Native execution result
        
    Returns:
        IsolationDecision
    """
    # Invalid states → REJECT
    if result.process_state in INVALID_STATES:
        return IsolationDecision.REJECT
    
    # KILLED → QUARANTINE
    if result.process_state == NativeProcessState.KILLED:
        return IsolationDecision.QUARANTINE
    
    # CRASHED / TIMED_OUT → REJECT
    if result.process_state in (NativeProcessState.CRASHED, NativeProcessState.TIMED_OUT):
        return IsolationDecision.REJECT
    
    # EXITED with exit_reason
    if result.process_state == NativeProcessState.EXITED:
        # ERROR exit → REJECT
        if result.exit_reason == NativeExitReason.ERROR:
            return IsolationDecision.REJECT
        # NORMAL exit but no evidence → REJECT
        if result.exit_reason == NativeExitReason.NORMAL:
            if not result.evidence_hash:
                return IsolationDecision.REJECT
            return IsolationDecision.ACCEPT
        # All enum values are covered, default to REJECT
        return IsolationDecision.REJECT


def decide_native_outcome(
    result: NativeExecutionResult,
    context: NativeExecutionContext
) -> IsolationDecisionResult:
    """Decide native outcome.
    
    Args:
        result: Native execution result
        context: Native execution context
        
    Returns:
        IsolationDecisionResult
    """
    # Invalid states → REJECT
    if result.process_state in INVALID_STATES:
        return IsolationDecisionResult(
            decision=IsolationDecision.REJECT,
            reason_code="NAT-001",
            reason_description=f"Invalid state: {result.process_state.name}"
        )
    
    # KILLED → QUARANTINE
    if result.process_state == NativeProcessState.KILLED:
        return IsolationDecisionResult(
            decision=IsolationDecision.QUARANTINE,
            reason_code="NAT-002",
            reason_description="Process was KILLED: needs investigation"
        )
    
    # CRASHED → REJECT
    if result.process_state == NativeProcessState.CRASHED:
        return IsolationDecisionResult(
            decision=IsolationDecision.REJECT,
            reason_code="NAT-003",
            reason_description=f"Process CRASHED (exit code {result.exit_code})"
        )
    
    # TIMED_OUT → REJECT
    if result.process_state == NativeProcessState.TIMED_OUT:
        return IsolationDecisionResult(
            decision=IsolationDecision.REJECT,
            reason_code="NAT-004",
            reason_description=f"Process TIMED_OUT after {result.duration_ms}ms"
        )
    
    # EXITED
    if result.process_state == NativeProcessState.EXITED:
        # ERROR exit → REJECT
        if result.exit_reason == NativeExitReason.ERROR:
            return IsolationDecisionResult(
                decision=IsolationDecision.REJECT,
                reason_code="NAT-005",
                reason_description=f"Process exited with ERROR (code {result.exit_code})"
            )
        # NORMAL exit, check evidence
        if result.exit_reason == NativeExitReason.NORMAL:
            if not result.evidence_hash:
                return IsolationDecisionResult(
                    decision=IsolationDecision.REJECT,
                    reason_code="NAT-006",
                    reason_description="NORMAL exit without evidence_hash"
                )
            return IsolationDecisionResult(
                decision=IsolationDecision.ACCEPT,
                reason_code="NAT-OK",
                reason_description="NORMAL exit with valid evidence"
            )
        # EXITED with non-NORMAL/ERROR reason
        return IsolationDecisionResult(
            decision=IsolationDecision.REJECT,
            reason_code="NAT-007",
            reason_description=f"EXITED with unexpected reason: {result.exit_reason.name}"
        )

    # All 6 process states handled: PENDING, RUNNING (INVALID_STATES), KILLED, CRASHED, TIMED_OUT, EXITED
    # This point is unreachable but kept for static analysis
    raise AssertionError("Unreachable: all NativeProcessState values handled")  # pragma: no cover
