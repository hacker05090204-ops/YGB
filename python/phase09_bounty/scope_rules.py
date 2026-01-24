"""
Scope Rules - Phase-09 Bug Bounty Policy.

Pure function for scope determination with deny-by-default behavior.
"""

from python.phase09_bounty.bounty_types import AssetType, ScopeResult


# Explicit in-scope asset types - frozen set for immutability
IN_SCOPE_ASSETS: frozenset = frozenset({
    AssetType.WEB_APP,
    AssetType.API,
    AssetType.MOBILE,
})


def check_scope(asset_type: AssetType) -> ScopeResult:
    """Check if asset type is in scope.
    
    Uses deny-by-default: any asset not explicitly in IN_SCOPE_ASSETS
    returns OUT_OF_SCOPE.
    
    Decision Table:
        WEB_APP       -> IN_SCOPE
        API           -> IN_SCOPE
        MOBILE        -> IN_SCOPE
        INFRASTRUCTURE -> OUT_OF_SCOPE
        OUT_OF_PROGRAM -> OUT_OF_SCOPE
        UNKNOWN       -> OUT_OF_SCOPE (deny-by-default)
    
    Args:
        asset_type: The type of asset to check
        
    Returns:
        ScopeResult.IN_SCOPE if asset is in scope
        ScopeResult.OUT_OF_SCOPE otherwise (deny-by-default)
    """
    if asset_type in IN_SCOPE_ASSETS:
        return ScopeResult.IN_SCOPE
    return ScopeResult.OUT_OF_SCOPE
