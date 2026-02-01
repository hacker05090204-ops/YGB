"""
Phase-21 Sandbox Engine.

This module provides sandbox & fault isolation functions.

All functions are pure (no side effects).
All decisions are deny-by-default.

EXECUTION MAY FAIL.
THE SYSTEM MUST NEVER.
"""
from .sandbox_types import (
    ExecutionFaultType,
    SandboxDecision,
    RetryPolicy,
    FAULT_RETRY_POLICY,
    RETRYABLE_FAULTS
)
from .sandbox_context import (
    SandboxContext,
    FaultReport,
    SandboxDecisionResult
)


def classify_fault(fault_type: ExecutionFaultType) -> RetryPolicy:
    """Classify fault and return retry policy.
    
    Args:
        fault_type: The fault type
        
    Returns:
        RetryPolicy for the fault
    """
    return FAULT_RETRY_POLICY.get(fault_type, RetryPolicy.NO_RETRY)


def is_retry_allowed(context: SandboxContext) -> bool:
    """Check if retry is allowed.
    
    Args:
        context: Sandbox context
        
    Returns:
        True if retry is allowed
    """
    return context.attempt_number < context.max_retries


def enforce_retry_limit(context: SandboxContext) -> bool:
    """Enforce retry limit.
    
    Args:
        context: Sandbox context
        
    Returns:
        True if within limit, False if at or over limit
    """
    return context.attempt_number < context.max_retries


def decide_sandbox_outcome(
    fault: FaultReport,
    context: SandboxContext
) -> SandboxDecisionResult:
    """Decide sandbox outcome for a fault.
    
    Args:
        fault: Fault report
        context: Sandbox context
        
    Returns:
        SandboxDecisionResult
    """
    fault_type = fault.fault_type
    retry_policy = classify_fault(fault_type)
    
    # SECURITY_VIOLATION → always TERMINATE
    if fault_type == ExecutionFaultType.SECURITY_VIOLATION:
        return SandboxDecisionResult(
            decision=SandboxDecision.TERMINATE,
            retry_policy=RetryPolicy.NO_RETRY,
            reason_code="SBX-001",
            reason_description="SECURITY_VIOLATION: immediate termination"
        )
    
    # RESOURCE_EXHAUSTED → ESCALATE
    if fault_type == ExecutionFaultType.RESOURCE_EXHAUSTED:
        return SandboxDecisionResult(
            decision=SandboxDecision.ESCALATE,
            retry_policy=RetryPolicy.HUMAN_DECISION,
            reason_code="SBX-002",
            reason_description="RESOURCE_EXHAUSTED: human decision required"
        )
    
    # PARTIAL / INVALID_RESPONSE → TERMINATE
    if fault_type in (ExecutionFaultType.PARTIAL, ExecutionFaultType.INVALID_RESPONSE):
        return SandboxDecisionResult(
            decision=SandboxDecision.TERMINATE,
            retry_policy=RetryPolicy.NO_RETRY,
            reason_code="SBX-003",
            reason_description=f"{fault_type.name}: not retryable"
        )
    
    # CRASH / TIMEOUT → RETRY if within limit
    # Note: All ExecutionFaultType values are covered above
    # This is the only remaining case (retryable faults)
    if is_retry_allowed(context):
        return SandboxDecisionResult(
            decision=SandboxDecision.RETRY,
            retry_policy=retry_policy,
            reason_code="SBX-OK",
            reason_description=f"{fault_type.name}: retry allowed (attempt {context.attempt_number}/{context.max_retries})"
        )
    return SandboxDecisionResult(
        decision=SandboxDecision.TERMINATE,
        retry_policy=RetryPolicy.NO_RETRY,
        reason_code="SBX-004",
        reason_description=f"{fault_type.name}: max retries reached"
    )
