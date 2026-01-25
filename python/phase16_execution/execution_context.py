"""
Phase-16 Execution Context.

This module defines frozen dataclasses for execution permission.

All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass
from typing import Optional

from .execution_types import ExecutionPermission


@dataclass(frozen=True)
class ExecutionContext:
    """Context for execution permission decision.
    
    All fields are immutable after creation.
    
    Attributes:
        bug_id: Bug identifier
        target_id: Target identifier
        handoff_readiness: From Phase-13 (ReadinessState value)
        handoff_can_proceed: From Phase-13 (bool)
        handoff_is_blocked: From Phase-13 (bool)
        handoff_human_presence: From Phase-13 (HumanPresence value)
        contract_is_valid: From Phase-15 (bool)
        human_present: Whether human is present
        decision_timestamp: ISO timestamp of decision
        human_override: Whether human override requested
    """
    bug_id: str
    target_id: str
    handoff_readiness: str
    handoff_can_proceed: bool
    handoff_is_blocked: bool
    handoff_human_presence: str
    contract_is_valid: bool
    human_present: bool
    decision_timestamp: str
    human_override: bool = False


@dataclass(frozen=True)
class ExecutionDecision:
    """Immutable execution decision.
    
    Attributes:
        permission: ALLOWED or DENIED
        is_allowed: True if allowed
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
        context: Original context (may be None for null input)
    """
    permission: ExecutionPermission
    is_allowed: bool
    reason_code: str
    reason_description: str
    context: Optional[ExecutionContext] = None
