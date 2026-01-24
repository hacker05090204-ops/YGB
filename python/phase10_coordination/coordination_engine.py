"""
Phase-10 Coordination Engine.

Core coordination logic for work claims and de-duplication.

All functions are:
- Pure (no side effects)
- Deterministic (same input → same output)
- Total (handle all possible inputs)
"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone

from python.phase10_coordination.coordination_types import WorkClaimStatus, ClaimAction
from python.phase10_coordination.coordination_context import WorkClaimContext


@dataclass(frozen=True)
class WorkClaimResult:
    """Immutable result of a coordination operation.

    Attributes:
        request_id: ID of the original request
        target_hash: Hash of the target
        status: Resulting claim status
        granted: Whether the request was granted
        reason_code: Machine-readable reason code
        reason_description: Human-readable reason
        claim_expiry: Expiry timestamp if claim granted
        owner_id: Owner of the claim
    """

    request_id: str
    target_hash: str
    status: WorkClaimStatus
    granted: bool
    reason_code: str
    reason_description: str
    claim_expiry: Optional[str]
    owner_id: Optional[str]


def is_claim_expired(
    claim_timestamp: str,
    current_time: str,
    duration_seconds: int
) -> bool:
    """Check if a claim has expired.

    Pure deterministic comparison.

    Args:
        claim_timestamp: ISO timestamp of when claim was made
        current_time: Current ISO timestamp
        duration_seconds: Duration of claim in seconds

    Returns:
        True if claim has expired, False otherwise
    """
    try:
        claim_dt = datetime.fromisoformat(claim_timestamp.replace('Z', '+00:00'))
        current_dt = datetime.fromisoformat(current_time.replace('Z', '+00:00'))
        elapsed = (current_dt - claim_dt).total_seconds()
        return elapsed >= duration_seconds
    except (ValueError, TypeError):
        return True  # Invalid timestamps → treat as expired


def claim_target(context: WorkClaimContext) -> WorkClaimResult:
    """Attempt to claim a target for work.

    Decision precedence:
    1. Check policy is active
    2. Check if target is already claimed
    3. If claimed, check if owner is same researcher
    4. If claimed by another, check if expired
    5. Grant or deny accordingly

    Args:
        context: Immutable claim context

    Returns:
        WorkClaimResult with decision and reasoning
    """
    target_hash = context.target.target_hash
    policy = context.policy
    researcher = context.researcher_id

    # Decision 1: Check policy is active
    if not policy.active:
        return WorkClaimResult(
            request_id=context.request_id,
            target_hash=target_hash,
            status=WorkClaimStatus.DENIED,
            granted=False,
            reason_code="DN-004",
            reason_description="Policy is inactive",
            claim_expiry=None,
            owner_id=None
        )

    # Decision 2: Check if target is already claimed
    if target_hash in context.existing_claims:
        owner = context.claim_owners.get(target_hash)

        # Decision 2a: Owner is same researcher
        if owner == researcher:
            # Check if expired and reclaimable
            if context.claim_timestamps and target_hash in context.claim_timestamps:
                claim_time = context.claim_timestamps[target_hash]
                if is_claim_expired(claim_time, context.request_timestamp, policy.claim_duration_seconds):
                    # Expired, allow reclaim
                    return WorkClaimResult(
                        request_id=context.request_id,
                        target_hash=target_hash,
                        status=WorkClaimStatus.CLAIMED,
                        granted=True,
                        reason_code="CL-002",
                        reason_description="Claim granted (reclaim after expiry)",
                        claim_expiry=None,
                        owner_id=researcher
                    )

            return WorkClaimResult(
                request_id=context.request_id,
                target_hash=target_hash,
                status=WorkClaimStatus.DENIED,
                granted=False,
                reason_code="DN-001",
                reason_description="Target is already claimed by you",
                claim_expiry=None,
                owner_id=owner
            )

        # Decision 2b: Claimed by another
        # Check if expired
        if context.claim_timestamps and target_hash in context.claim_timestamps:
            claim_time = context.claim_timestamps[target_hash]
            if is_claim_expired(claim_time, context.request_timestamp, policy.claim_duration_seconds):
                # Expired, allow new claim
                return WorkClaimResult(
                    request_id=context.request_id,
                    target_hash=target_hash,
                    status=WorkClaimStatus.CLAIMED,
                    granted=True,
                    reason_code="CL-002",
                    reason_description="Claim granted (prior claim expired)",
                    claim_expiry=None,
                    owner_id=researcher
                )

        return WorkClaimResult(
            request_id=context.request_id,
            target_hash=target_hash,
            status=WorkClaimStatus.DENIED,
            granted=False,
            reason_code="DN-002",
            reason_description="Target is claimed by another researcher",
            claim_expiry=None,
            owner_id=owner
        )

    # Decision 3: Target is unclaimed, grant claim
    return WorkClaimResult(
        request_id=context.request_id,
        target_hash=target_hash,
        status=WorkClaimStatus.CLAIMED,
        granted=True,
        reason_code="CL-001",
        reason_description="Claim granted successfully",
        claim_expiry=None,
        owner_id=researcher
    )


def release_claim(context: WorkClaimContext) -> WorkClaimResult:
    """Release a claim on a target.

    Only the owner can release their claim.

    Args:
        context: Immutable claim context

    Returns:
        WorkClaimResult with decision and reasoning
    """
    target_hash = context.target.target_hash
    researcher = context.researcher_id

    # Check if target is claimed
    if target_hash not in context.existing_claims:
        return WorkClaimResult(
            request_id=context.request_id,
            target_hash=target_hash,
            status=WorkClaimStatus.DENIED,
            granted=False,
            reason_code="DN-005",
            reason_description="Nothing to release - no active claim",
            claim_expiry=None,
            owner_id=None
        )

    # Check if researcher is the owner
    owner = context.claim_owners.get(target_hash)
    if owner != researcher:
        return WorkClaimResult(
            request_id=context.request_id,
            target_hash=target_hash,
            status=WorkClaimStatus.DENIED,
            granted=False,
            reason_code="DN-006",
            reason_description="Cannot release - not your claim",
            claim_expiry=None,
            owner_id=owner
        )

    # Release granted
    return WorkClaimResult(
        request_id=context.request_id,
        target_hash=target_hash,
        status=WorkClaimStatus.RELEASED,
        granted=True,
        reason_code="RL-001",
        reason_description="Claim released successfully",
        claim_expiry=None,
        owner_id=None
    )


def check_claim_status(
    target_hash: str,
    existing_claims: frozenset[str],
    claim_timestamps: dict[str, str],
    current_time: str,
    policy_duration: int
) -> WorkClaimStatus:
    """Check current claim status of a target.

    Args:
        target_hash: Hash of target to check
        existing_claims: Set of claimed target hashes
        claim_timestamps: Mapping of target_hash -> timestamp
        current_time: Current ISO timestamp
        policy_duration: Claim duration in seconds

    Returns:
        Current WorkClaimStatus
    """
    if target_hash not in existing_claims:
        return WorkClaimStatus.UNCLAIMED

    if target_hash in claim_timestamps:
        claim_time = claim_timestamps[target_hash]
        if is_claim_expired(claim_time, current_time, policy_duration):
            return WorkClaimStatus.EXPIRED

    return WorkClaimStatus.CLAIMED
