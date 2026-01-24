"""
Phase-09: Bug Bounty Policy, Scope & Eligibility Logic.

This module provides governance-only logic for bug bounty programs:
- Scope determination (in-scope vs out-of-scope)
- Eligibility evaluation
- Duplicate detection
- Human review flagging

CONSTRAINTS:
- No execution logic
- No browser automation
- No network access
- No scoring algorithms
- All dataclasses frozen
- All enums closed
- Deny-by-default everywhere
"""

from python.phase09_bounty.bounty_types import BountyDecision, ScopeResult, AssetType
from python.phase09_bounty.bounty_context import BountyContext, BountyDecisionResult
from python.phase09_bounty.scope_rules import check_scope
from python.phase09_bounty.bounty_engine import evaluate_bounty

__all__ = [
    # Enums
    'BountyDecision',
    'ScopeResult',
    'AssetType',
    # Dataclasses
    'BountyContext',
    'BountyDecisionResult',
    # Functions
    'check_scope',
    'evaluate_bounty',
]
