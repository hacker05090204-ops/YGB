"""
Phase-13 Human Readiness, Safety Gate & Browser Handoff Governance.

This module provides backend governance logic for:
- Bug readiness assessment
- Human presence requirements
- Handoff decision making

This is a PURE BACKEND module - NO browser, NO execution.

Exports:
    Enums:
        ReadinessState: Readiness for browser (NOT_READY, REVIEW_REQUIRED, READY_FOR_BROWSER)
        HumanPresence: Human presence level (REQUIRED, OPTIONAL, BLOCKING)
        BugSeverity: Bug severity (CRITICAL, HIGH, MEDIUM, LOW)
        TargetType: Target type (PRODUCTION, STAGING, DEVELOPMENT, SANDBOX)
    
    Dataclasses (all frozen=True):
        HandoffContext: Context for handoff decision
        HandoffDecision: Result of handoff decision
    
    Functions:
        check_readiness: Check if bug is ready for browser
        determine_human_presence: Determine human presence requirement
        is_blocked: Check if handoff is blocked
        make_handoff_decision: Make complete handoff decision
"""
from .handoff_types import (
    ReadinessState,
    HumanPresence,
    BugSeverity,
    TargetType
)
from .handoff_context import HandoffContext
from .readiness_engine import (
    HandoffDecision,
    check_readiness,
    determine_human_presence,
    is_blocked,
    make_handoff_decision
)

__all__ = [
    # Enums
    "ReadinessState",
    "HumanPresence",
    "BugSeverity",
    "TargetType",
    # Dataclasses
    "HandoffContext",
    "HandoffDecision",
    # Functions
    "check_readiness",
    "determine_human_presence",
    "is_blocked",
    "make_handoff_decision",
]
