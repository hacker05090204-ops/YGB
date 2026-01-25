"""
Phase-19 Capability Context.

This module defines frozen dataclasses for capability governance.

All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass
from typing import Optional

from .capability_types import BrowserActionType, ActionRiskLevel, CapabilityDecision


@dataclass(frozen=True)
class BrowserCapabilityPolicy:
    """Browser capability policy. Frozen.
    
    Attributes:
        policy_id: Unique policy ID
        allowed_actions: Set of allowed action types
        risk_overrides: Custom risk levels (tuple of tuples)
        require_evidence: Whether evidence is required
        max_actions_per_execution: Max actions per execution
    """
    policy_id: str
    allowed_actions: frozenset  # frozenset of BrowserActionType
    risk_overrides: tuple = ()
    require_evidence: bool = True
    max_actions_per_execution: int = 100


@dataclass(frozen=True)
class ActionRequestContext:
    """Action request context. Frozen.
    
    Attributes:
        execution_id: Execution ID from Phase-18
        action_type: Requested action type
        request_timestamp: ISO timestamp
        execution_state: Current execution state
        action_count: Actions performed so far
    """
    execution_id: str
    action_type: BrowserActionType
    request_timestamp: str
    execution_state: str
    action_count: int = 0


@dataclass(frozen=True)
class CapabilityDecisionResult:
    """Capability decision result. Frozen.
    
    Attributes:
        decision: ALLOWED, DENIED, HUMAN_REQUIRED
        reason_code: Machine-readable code
        reason_description: Human-readable description
        action_type: The action type
        risk_level: Determined risk level
    """
    decision: CapabilityDecision
    reason_code: str
    reason_description: str
    action_type: BrowserActionType
    risk_level: ActionRiskLevel
