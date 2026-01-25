"""
Phase-16 Execution Engine.

This module provides execution permission decision logic.

All functions are pure (no side effects).
All decisions are deny-by-default.

THIS IS A PERMISSION LAYER ONLY.
IT DOES NOT EXECUTE ANYTHING.
"""
from typing import Optional

from .execution_types import ExecutionPermission, VALID_READINESS_STATES
from .execution_context import ExecutionContext, ExecutionDecision


def check_handoff_signals(context: ExecutionContext) -> bool:
    """Check Phase-13 signals. Returns True if all pass.
    
    Args:
        context: ExecutionContext with handoff signals
        
    Returns:
        True if all handoff signals pass, False otherwise
    """
    # Check readiness state
    if context.handoff_readiness == "NOT_READY":
        return False
    
    # Check can_proceed
    if not context.handoff_can_proceed:
        return False
    
    # Check is_blocked
    if context.handoff_is_blocked:
        return False
    
    return True


def check_contract_signals(context: ExecutionContext) -> bool:
    """Check Phase-15 signals. Returns True if valid.
    
    Args:
        context: ExecutionContext with contract signals
        
    Returns:
        True if contract is valid, False otherwise
    """
    return context.contract_is_valid


def check_human_present(context: ExecutionContext) -> bool:
    """Check human presence requirements.
    
    Args:
        context: ExecutionContext
        
    Returns:
        True if human presence requirements are met
    """
    human_presence = context.handoff_human_presence
    
    # BLOCKING always blocks
    if human_presence == "BLOCKING":
        return False
    
    # REQUIRED needs human present
    if human_presence == "REQUIRED":
        return context.human_present
    
    # OPTIONAL doesn't need human
    return True


def decide_execution(context: Optional[ExecutionContext]) -> ExecutionDecision:
    """Make final execution decision. Deny-by-default.
    
    This is a PERMISSION layer only. It does NOT execute anything.
    
    Args:
        context: ExecutionContext (may be None)
        
    Returns:
        ExecutionDecision with ALLOWED or DENIED
    """
    # Null context → DENIED
    if context is None:
        return ExecutionDecision(
            permission=ExecutionPermission.DENIED,
            is_allowed=False,
            reason_code="EX-000",
            reason_description="Null context provided",
            context=None
        )
    
    # Check readiness state
    readiness = context.handoff_readiness
    
    # Unknown readiness → DENIED
    if readiness not in VALID_READINESS_STATES:
        return ExecutionDecision(
            permission=ExecutionPermission.DENIED,
            is_allowed=False,
            reason_code="EX-009",
            reason_description=f"Unknown readiness state: {readiness}",
            context=context
        )
    
    # NOT_READY → DENIED (no override)
    if readiness == "NOT_READY":
        return ExecutionDecision(
            permission=ExecutionPermission.DENIED,
            is_allowed=False,
            reason_code="EX-001",
            reason_description="Readiness state is NOT_READY",
            context=context
        )
    
    # REVIEW_REQUIRED → needs human override
    if readiness == "REVIEW_REQUIRED" and not context.human_override:
        return ExecutionDecision(
            permission=ExecutionPermission.DENIED,
            is_allowed=False,
            reason_code="EX-002",
            reason_description="Review required but no human override",
            context=context
        )
    
    # Check can_proceed
    if not context.handoff_can_proceed:
        return ExecutionDecision(
            permission=ExecutionPermission.DENIED,
            is_allowed=False,
            reason_code="EX-003",
            reason_description="Handoff can_proceed is False",
            context=context
        )
    
    # Check is_blocked
    if context.handoff_is_blocked:
        return ExecutionDecision(
            permission=ExecutionPermission.DENIED,
            is_allowed=False,
            reason_code="EX-004",
            reason_description="Handoff is_blocked is True",
            context=context
        )
    
    # Check human presence
    if not check_human_present(context):
        if context.handoff_human_presence == "BLOCKING":
            return ExecutionDecision(
                permission=ExecutionPermission.DENIED,
                is_allowed=False,
                reason_code="EX-006",
                reason_description="Human presence is BLOCKING",
                context=context
            )
        else:
            return ExecutionDecision(
                permission=ExecutionPermission.DENIED,
                is_allowed=False,
                reason_code="EX-005",
                reason_description="Human required but not present",
                context=context
            )
    
    # Check contract
    if not context.contract_is_valid:
        return ExecutionDecision(
            permission=ExecutionPermission.DENIED,
            is_allowed=False,
            reason_code="EX-007",
            reason_description="Contract is not valid",
            context=context
        )
    
    # All checks passed → ALLOWED
    return ExecutionDecision(
        permission=ExecutionPermission.ALLOWED,
        is_allowed=True,
        reason_code="EX-OK",
        reason_description="All conditions satisfied, execution permitted",
        context=context
    )
