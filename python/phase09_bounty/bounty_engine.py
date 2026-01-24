"""
Phase-09 Bounty Engine.

Core decision engine for bounty eligibility.

All functions are:
- Pure (no side effects)
- Deterministic (same input → same output)
- Total (handle all possible inputs)

All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass
from typing import Optional

from python.phase09_bounty.bounty_types import ScopeResult, BountyDecision
from python.phase09_bounty.bounty_context import BountyContext
from python.phase09_bounty.scope_rules import evaluate_scope


@dataclass(frozen=True)
class DuplicateCheckResult:
    """Immutable result of duplicate detection.

    Attributes:
        is_duplicate: Whether submission is a duplicate
        matching_submission_hash: Hash of matching prior submission
        match_reason: Reason for match (if duplicate)
    """

    is_duplicate: bool
    matching_submission_hash: Optional[str]
    match_reason: Optional[str]


@dataclass(frozen=True)
class BountyDecisionResult:
    """Immutable result of a bounty eligibility decision.

    Attributes:
        submission_id: ID of the submission
        scope_result: Result of scope evaluation
        is_duplicate: Whether submission is duplicate
        decision: Final eligibility decision
        reason_code: Machine-readable reason code
        reason_description: Human-readable reason
        requires_human_review: Whether human review is needed
        review_reason: Reason for human review (if needed)
    """

    submission_id: str
    scope_result: ScopeResult
    is_duplicate: bool
    decision: BountyDecision
    reason_code: str
    reason_description: str
    requires_human_review: bool
    review_reason: Optional[str]


def check_duplicate(context: BountyContext) -> DuplicateCheckResult:
    """Check if submission is a duplicate of prior submissions.

    A submission is a duplicate if its root_cause_hash matches
    any hash in prior_submission_hashes.

    Args:
        context: Immutable submission context

    Returns:
        DuplicateCheckResult with duplicate status and match info
    """
    root_hash = context.root_cause_hash
    prior_hashes = context.prior_submission_hashes

    if root_hash in prior_hashes:
        return DuplicateCheckResult(
            is_duplicate=True,
            matching_submission_hash=root_hash,
            match_reason="Exact root cause hash match"
        )

    return DuplicateCheckResult(
        is_duplicate=False,
        matching_submission_hash=None,
        match_reason=None
    )


def requires_review(context: BountyContext) -> tuple[bool, Optional[str]]:
    """Determine if submission requires human review.

    NEEDS_REVIEW triggers:
    - NR-001: Scope ambiguity (not implemented - requires partial matching)
    - NR-002: Novel vulnerability type (not implemented - requires ML)
    - NR-003: Partial duplicate overlap (not implemented)
    - NR-004: Researcher dispute (not in context)
    - NR-005: Policy edge case (not implementable generically)
    - NR-006: High severity claim (not in context)
    - NR-007: Multiple vulnerabilities (not in context)
    - NR-008: Unknown condition (catch-all)

    For this implementation, we use explicit rules:
    - Clear IN_SCOPE/OUT_OF_SCOPE → no review needed
    - Clear DUPLICATE → no review needed
    - Clear ELIGIBLE → no review needed

    Args:
        context: Immutable submission context

    Returns:
        (True, reason) if human review required
        (False, None) if auto-decision allowed
    """
    # Evaluate scope
    scope = evaluate_scope(context)

    # Clear out of scope → no review
    if scope == ScopeResult.OUT_OF_SCOPE:
        return (False, None)

    # Check duplicate
    dup_result = check_duplicate(context)
    if dup_result.is_duplicate:
        return (False, None)

    # Clear eligible case → no review
    # Scope is IN_SCOPE here (only other possibility after OUT_OF_SCOPE check)
    policy = context.policy
    # If POC required and missing, clear decision (NOT_ELIGIBLE)
    if policy.require_proof_of_concept and not context.has_proof_of_concept:
        return (False, None)
    # Otherwise clear eligible
    return (False, None)


def make_decision(context: BountyContext) -> BountyDecisionResult:
    """Make final eligibility decision for submission.

    Decision precedence:
    1. Check scope (OUT_OF_SCOPE → NOT_ELIGIBLE)
    2. Check duplicate (is_duplicate → DUPLICATE)
    3. Check POC requirement (missing → NOT_ELIGIBLE)
    4. All checks pass → ELIGIBLE

    Default: NOT_ELIGIBLE (deny-by-default)

    Args:
        context: Immutable submission context

    Returns:
        BountyDecisionResult with decision and reasoning
    """
    # Check human review first
    needs_review, review_reason = requires_review(context)

    # Evaluate scope
    scope_result = evaluate_scope(context)

    # Decision 1: OUT_OF_SCOPE → NOT_ELIGIBLE
    if scope_result == ScopeResult.OUT_OF_SCOPE:
        return BountyDecisionResult(
            submission_id=context.submission_id,
            scope_result=scope_result,
            is_duplicate=False,
            decision=BountyDecision.NOT_ELIGIBLE,
            reason_code="NE-001",
            reason_description="Target is out of scope",
            requires_human_review=False,
            review_reason=None
        )

    # Decision 2: Check duplicate
    dup_result = check_duplicate(context)
    if dup_result.is_duplicate:
        return BountyDecisionResult(
            submission_id=context.submission_id,
            scope_result=scope_result,
            is_duplicate=True,
            decision=BountyDecision.DUPLICATE,
            reason_code="DU-001",
            reason_description="Duplicate of prior submission",
            requires_human_review=False,
            review_reason=None
        )

    # Decision 3: Check POC requirement
    policy = context.policy
    if policy.require_proof_of_concept and not context.has_proof_of_concept:
        return BountyDecisionResult(
            submission_id=context.submission_id,
            scope_result=scope_result,
            is_duplicate=False,
            decision=BountyDecision.NOT_ELIGIBLE,
            reason_code="NE-004",
            reason_description="Missing required proof of concept",
            requires_human_review=False,
            review_reason=None
        )

    # Decision 4: All checks passed → ELIGIBLE
    return BountyDecisionResult(
        submission_id=context.submission_id,
        scope_result=scope_result,
        is_duplicate=False,
        decision=BountyDecision.ELIGIBLE,
        reason_code="EL-001",
        reason_description="All eligibility conditions met",
        requires_human_review=needs_review,
        review_reason=review_reason
    )
