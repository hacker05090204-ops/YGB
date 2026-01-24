"""
Bounty Context - Phase-09 Bug Bounty Policy.

Defines frozen dataclasses for bounty evaluation:
- BountyContext: Input context for evaluation
- BountyDecisionResult: Output of evaluation

All dataclasses are FROZEN (immutable).
"""

from dataclasses import dataclass

from python.phase09_bounty.bounty_types import AssetType, ScopeResult, BountyDecision


@dataclass(frozen=True)
class BountyContext:
    """Immutable context for bounty evaluation.
    
    Attributes:
        report_id: Unique report identifier
        asset_type: Type of asset being reported
        vulnerability_type: Classification of vulnerability
        is_duplicate: Whether this is a duplicate report
        is_in_program: Whether reporter is in the program
    """
    report_id: str
    asset_type: AssetType
    vulnerability_type: str
    is_duplicate: bool
    is_in_program: bool


@dataclass(frozen=True)
class BountyDecisionResult:
    """Immutable result of bounty evaluation.
    
    Attributes:
        context: Original evaluation context
        scope_result: Result of scope determination
        decision: Final bounty decision
        requires_human_review: Whether human review is needed
        reason: Human-readable reason for decision
    """
    context: BountyContext
    scope_result: ScopeResult
    decision: BountyDecision
    requires_human_review: bool
    reason: str
