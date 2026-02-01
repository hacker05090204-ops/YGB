"""
Phase-09: Bug Bounty Policy, Scope & Eligibility Logic.

This module provides pure backend logic for bug bounty eligibility decisions.

NO browser logic. NO execution logic. NO network access.
All dataclasses are frozen. All functions are pure.

Exports:
    - ScopeResult: Enum for scope classification
    - BountyDecision: Enum for eligibility decisions
    - BountyPolicy: Immutable policy definition
    - BountyContext: Immutable submission context
    - DuplicateCheckResult: Immutable duplicate check result
    - BountyDecisionResult: Immutable decision result
    - evaluate_scope: Evaluate scope classification
    - check_duplicate: Check for duplicates
    - requires_review: Check if human review needed
    - make_decision: Make eligibility decision
"""
from python.phase09_bounty.bounty_types import ScopeResult, BountyDecision
from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
from python.phase09_bounty.bounty_engine import (
    DuplicateCheckResult,
    BountyDecisionResult,
    check_duplicate,
    requires_review,
    make_decision,
)
from python.phase09_bounty.scope_rules import evaluate_scope

__all__ = [
    "ScopeResult",
    "BountyDecision",
    "BountyPolicy",
    "BountyContext",
    "DuplicateCheckResult",
    "BountyDecisionResult",
    "evaluate_scope",
    "check_duplicate",
    "requires_review",
    "make_decision",
]
