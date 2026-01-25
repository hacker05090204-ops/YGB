"""
Phase-19 Browser Capability Governance & Action Authorization.

This module provides browser capability governance.

THIS IS A POLICY LAYER ONLY.
IT DOES NOT EXECUTE BROWSERS.
IT DOES NOT INVOKE SUBPROCESSES.
IT DOES NOT MAKE NETWORK CALLS.

Exports:
    Enums:
        BrowserActionType: NAVIGATE, CLICK, READ, etc.
        ActionRiskLevel: LOW, MEDIUM, HIGH, FORBIDDEN
        CapabilityDecision: ALLOWED, DENIED, HUMAN_REQUIRED
    
    Dataclasses (all frozen=True):
        BrowserCapabilityPolicy: Policy definition
        ActionRequestContext: Request context
        CapabilityDecisionResult: Decision result
    
    Functions:
        classify_action_risk: Classify action risk
        is_action_allowed: Check if action allowed
        decide_capability: Make capability decision
        validate_action_against_policy: Validate action
"""
from .capability_types import (
    BrowserActionType,
    ActionRiskLevel,
    CapabilityDecision,
    DEFAULT_RISK_CLASSIFICATION,
    FORBIDDEN_ACTIONS,
    VALID_EXECUTION_STATES,
    TERMINAL_STATES
)
from .capability_context import (
    BrowserCapabilityPolicy,
    ActionRequestContext,
    CapabilityDecisionResult
)
from .capability_engine import (
    classify_action_risk,
    is_action_allowed,
    decide_capability,
    validate_action_against_policy
)

__all__ = [
    # Enums
    "BrowserActionType",
    "ActionRiskLevel",
    "CapabilityDecision",
    # Constants
    "DEFAULT_RISK_CLASSIFICATION",
    "FORBIDDEN_ACTIONS",
    "VALID_EXECUTION_STATES",
    "TERMINAL_STATES",
    # Dataclasses
    "BrowserCapabilityPolicy",
    "ActionRequestContext",
    "CapabilityDecisionResult",
    # Functions
    "classify_action_risk",
    "is_action_allowed",
    "decide_capability",
    "validate_action_against_policy",
]
