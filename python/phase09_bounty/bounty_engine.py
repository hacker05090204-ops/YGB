"""
Bounty Engine - Phase-09 Bug Bounty Policy.

Pure function for bounty eligibility evaluation.
Implements explicit decision table - no implicit logic.
"""

from python.phase09_bounty.bounty_types import BountyDecision, ScopeResult
from python.phase09_bounty.bounty_context import BountyContext, BountyDecisionResult
from python.phase09_bounty.scope_rules import check_scope


def evaluate_bounty(context: BountyContext) -> BountyDecisionResult:
    """Evaluate bounty eligibility based on context.
    
    Implements the explicit decision table:
    
    | # | Asset Scope   | Is Duplicate | In Program | Decision      | Reason                   |
    |---|---------------|--------------|------------|---------------|--------------------------|
    | 1 | OUT_OF_SCOPE  | Any          | Any        | NOT_ELIGIBLE  | Asset out of scope       |
    | 2 | IN_SCOPE      | True         | Any        | DUPLICATE     | Duplicate report         |
    | 3 | IN_SCOPE      | False        | False      | NOT_ELIGIBLE  | Reporter not in program  |
    | 4 | IN_SCOPE      | False        | True       | ELIGIBLE      | All conditions met       |
    
    Args:
        context: Bounty evaluation context
        
    Returns:
        BountyDecisionResult with decision and reason
    """
    # Step 1: Check scope
    scope_result = check_scope(context.asset_type)
    
    # Decision 1: Out of scope -> NOT_ELIGIBLE
    if scope_result == ScopeResult.OUT_OF_SCOPE:
        return BountyDecisionResult(
            context=context,
            scope_result=scope_result,
            decision=BountyDecision.NOT_ELIGIBLE,
            requires_human_review=False,
            reason="Asset out of scope"
        )
    
    # Decision 2: Duplicate -> DUPLICATE
    if context.is_duplicate:
        return BountyDecisionResult(
            context=context,
            scope_result=scope_result,
            decision=BountyDecision.DUPLICATE,
            requires_human_review=False,
            reason="Duplicate report"
        )
    
    # Decision 3: Not in program -> NOT_ELIGIBLE
    if not context.is_in_program:
        return BountyDecisionResult(
            context=context,
            scope_result=scope_result,
            decision=BountyDecision.NOT_ELIGIBLE,
            requires_human_review=False,
            reason="Reporter not in program"
        )
    
    # Decision 4: All conditions met -> ELIGIBLE
    return BountyDecisionResult(
        context=context,
        scope_result=scope_result,
        decision=BountyDecision.ELIGIBLE,
        requires_human_review=False,
        reason="All conditions met"
    )
