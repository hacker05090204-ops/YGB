"""
Phase-10: Target Coordination & De-Duplication Authority.

This module provides pure backend logic for work coordination.

NO browser logic. NO execution logic. NO network access.
All dataclasses are frozen. All functions are pure.

Exports:
    - WorkClaimStatus: Enum for claim status
    - ClaimAction: Enum for claim actions
    - TargetID: Immutable target identifier
    - CoordinationPolicy: Immutable policy definition
    - WorkClaimContext: Immutable context for operations
    - WorkClaimResult: Immutable result of operations
    - create_target_id: Create target with hash
    - claim_target: Claim a target
    - release_claim: Release a claim
    - is_claim_expired: Check expiry
    - check_claim_status: Check status
"""
from python.phase10_coordination.coordination_types import (
    WorkClaimStatus,
    ClaimAction,
)
from python.phase10_coordination.coordination_context import (
    TargetID,
    CoordinationPolicy,
    WorkClaimContext,
    create_target_id,
)
from python.phase10_coordination.coordination_engine import (
    WorkClaimResult,
    claim_target,
    release_claim,
    is_claim_expired,
    check_claim_status,
)

__all__ = [
    "WorkClaimStatus",
    "ClaimAction",
    "TargetID",
    "CoordinationPolicy",
    "WorkClaimContext",
    "WorkClaimResult",
    "create_target_id",
    "claim_target",
    "release_claim",
    "is_claim_expired",
    "check_claim_status",
]
