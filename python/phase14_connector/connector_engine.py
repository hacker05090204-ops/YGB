"""
Phase-14 Connector Engine.

This module provides READ-ONLY mapping logic.

All functions are pure (no side effects).
All values are pass-through (no modification).
Phase-14 has ZERO AUTHORITY - it cannot approve or modify anything.
"""
from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
from python.phase13_handoff.handoff_types import ReadinessState, HumanPresence
from python.phase13_handoff.readiness_engine import HandoffDecision
from .connector_context import ConnectorInput, ConnectorOutput, ConnectorResult


def validate_input(input: ConnectorInput) -> bool:
    """Validate input contract. No authority.
    
    Args:
        input: ConnectorInput to validate
        
    Returns:
        True if valid, False otherwise
    """
    # Empty bug_id is invalid
    if not input.bug_id:
        return False
    
    # Empty target_id is invalid
    if not input.target_id:
        return False
    
    # Empty timestamp is invalid
    if not input.timestamp:
        return False
    
    return True


def map_handoff_to_output(
    input: ConnectorInput,
    decision: HandoffDecision
) -> ConnectorOutput:
    """Map Phase-13 decision to output. READ-ONLY.
    
    This function ONLY maps values - it has NO authority to change them.
    All values are passed through EXACTLY as received.
    
    Args:
        input: ConnectorInput with request details
        decision: HandoffDecision from Phase-13
        
    Returns:
        ConnectorOutput with all values passed through
    """
    # READ-ONLY pass-through mapping
    # Phase-14 has ZERO AUTHORITY - all values are exactly as received
    return ConnectorOutput(
        bug_id=input.bug_id,
        target_id=input.target_id,
        confidence=ConfidenceLevel.LOW,  # Default, would come from Phase-12
        evidence_state=EvidenceState.UNVERIFIED,  # Default, would come from Phase-12
        readiness=decision.readiness,  # PASS-THROUGH
        human_presence=decision.human_presence,  # PASS-THROUGH
        can_proceed=decision.can_proceed,  # PASS-THROUGH - CANNOT CHANGE
        is_blocked=decision.is_blocked,  # PASS-THROUGH - CANNOT CHANGE
        blockers=decision.blockers,  # PASS-THROUGH
        reason_code=decision.reason_code,  # PASS-THROUGH
        reason_description=decision.reason_description  # PASS-THROUGH
    )


def propagate_blocking(decision: HandoffDecision) -> bool:
    """Check if blocking propagates. Pass-through only.
    
    If the decision is blocked, the output MUST be blocked.
    Phase-14 CANNOT change blocking to non-blocking.
    
    Args:
        decision: HandoffDecision from Phase-13
        
    Returns:
        True if blocked, False otherwise
    """
    # PASS-THROUGH ONLY - no authority to change
    return decision.is_blocked


def create_default_output(input: ConnectorInput) -> ConnectorOutput:
    """Create default blocked output when no decision available.
    
    Deny-by-default: If no decision, output is blocked.
    
    Args:
        input: ConnectorInput
        
    Returns:
        ConnectorOutput with blocked state
    """
    return ConnectorOutput(
        bug_id=input.bug_id,
        target_id=input.target_id,
        confidence=ConfidenceLevel.LOW,
        evidence_state=EvidenceState.UNVERIFIED,
        readiness=ReadinessState.NOT_READY,
        human_presence=HumanPresence.BLOCKING,
        can_proceed=False,  # Deny-by-default
        is_blocked=True,  # Deny-by-default
        blockers=("NO_DECISION",),
        reason_code="CN-001",
        reason_description="No decision provided - denied by default"
    )


def create_result(
    input: ConnectorInput,
    output: ConnectorOutput,
    success: bool,
    error_code: str = None,
    error_description: str = None
) -> ConnectorResult:
    """Create result container. No modification.
    
    Args:
        input: Original input
        output: Connector output
        success: Whether pipeline succeeded
        error_code: Error code if failed
        error_description: Error description if failed
        
    Returns:
        ConnectorResult with all values
    """
    return ConnectorResult(
        input=input,
        output=output,
        success=success,
        error_code=error_code,
        error_description=error_description
    )
