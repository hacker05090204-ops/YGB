"""
Phase-09 Scope Rules.

Pure functions for evaluating scope classification.

All functions are:
- Pure (no side effects)
- Deterministic (same input → same output)
- Total (handle all possible inputs)
"""
from python.phase09_bounty.bounty_types import ScopeResult
from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext


def is_asset_in_scope(asset: str, policy: BountyPolicy) -> bool:
    """Check if asset is in the policy's in-scope assets.

    Args:
        asset: Target asset to check
        policy: Policy to check against

    Returns:
        True if asset is in scope, False otherwise
    """
    return asset in policy.in_scope_assets


def is_asset_excluded(asset: str, policy: BountyPolicy) -> bool:
    """Check if asset is explicitly excluded.

    Args:
        asset: Target asset to check
        policy: Policy to check against

    Returns:
        True if asset is excluded, False otherwise
    """
    return asset in policy.excluded_assets


def is_vuln_type_accepted(vuln_type: str, policy: BountyPolicy) -> bool:
    """Check if vulnerability type is accepted.

    Args:
        vuln_type: Vulnerability type to check
        policy: Policy to check against

    Returns:
        True if vuln type is accepted, False otherwise
    """
    if not policy.accepted_vuln_types:
        return False
    return vuln_type in policy.accepted_vuln_types


def is_vuln_type_excluded(vuln_type: str, policy: BountyPolicy) -> bool:
    """Check if vulnerability type is explicitly excluded.

    Args:
        vuln_type: Vulnerability type to check
        policy: Policy to check against

    Returns:
        True if vuln type is excluded, False otherwise
    """
    return vuln_type in policy.excluded_vuln_types


def evaluate_scope(context: BountyContext) -> ScopeResult:
    """Evaluate whether submission target is in-scope.

    Decision table:
    - Policy inactive → OUT_OF_SCOPE
    - Empty asset → OUT_OF_SCOPE
    - Asset excluded → OUT_OF_SCOPE
    - Asset not in scope → OUT_OF_SCOPE
    - Vuln type excluded → OUT_OF_SCOPE
    - Vuln type not accepted → OUT_OF_SCOPE
    - All checks pass → IN_SCOPE

    Default behavior: DENY (OUT_OF_SCOPE)

    Args:
        context: Immutable submission context

    Returns:
        ScopeResult.IN_SCOPE if all conditions met
        ScopeResult.OUT_OF_SCOPE otherwise (deny-by-default)
    """
    policy = context.policy

    # Check policy is active
    if not policy.active:
        return ScopeResult.OUT_OF_SCOPE

    # Check asset is not empty
    if not context.target_asset:
        return ScopeResult.OUT_OF_SCOPE

    # Check asset is not excluded
    if is_asset_excluded(context.target_asset, policy):
        return ScopeResult.OUT_OF_SCOPE

    # Check asset is in scope
    if not is_asset_in_scope(context.target_asset, policy):
        return ScopeResult.OUT_OF_SCOPE

    # Check vuln type is not excluded
    if is_vuln_type_excluded(context.vulnerability_type, policy):
        return ScopeResult.OUT_OF_SCOPE

    # Check vuln type is accepted
    if not is_vuln_type_accepted(context.vulnerability_type, policy):
        return ScopeResult.OUT_OF_SCOPE

    # All checks passed
    return ScopeResult.IN_SCOPE
