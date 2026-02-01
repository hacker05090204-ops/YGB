"""
Phase-10 Coordination Context.

Defines immutable dataclasses for coordination and target identity.
"""
from dataclasses import dataclass
from typing import Optional
import hashlib

from python.phase10_coordination.coordination_types import ClaimAction


@dataclass(frozen=True)
class TargetID:
    """Immutable target identifier.

    Uniquely identifies a bug bounty target.

    Attributes:
        program_id: Bounty program identifier
        asset_id: Target asset (domain, endpoint, etc.)
        vulnerability_class: Type of vulnerability being tested
        target_hash: SHA-256 hash of above attributes
    """

    program_id: str
    asset_id: str
    vulnerability_class: str
    target_hash: str


@dataclass(frozen=True)
class CoordinationPolicy:
    """Immutable coordination policy definition.

    Defines claim duration and rules.

    Attributes:
        policy_id: Unique policy identifier
        claim_duration_seconds: How long a claim lasts
        allow_reclaim_after_expiry: Whether expired claims can be reclaimed
        active: Whether the policy is currently active
    """

    policy_id: str
    claim_duration_seconds: int
    allow_reclaim_after_expiry: bool
    active: bool


@dataclass(frozen=True)
class WorkClaimContext:
    """Immutable context for coordination operations.

    Contains all information for claim decisions.

    Attributes:
        request_id: Unique request identifier
        target: Target being claimed
        researcher_id: Researcher making the request
        action: Type of action being requested
        request_timestamp: ISO timestamp of request
        policy: Coordination policy to apply
        existing_claims: Set of currently claimed target hashes
        claim_owners: Mapping of target_hash -> owner_id
        claim_timestamps: Mapping of target_hash -> claim_timestamp (optional)
    """

    request_id: str
    target: TargetID
    researcher_id: str
    action: ClaimAction
    request_timestamp: str
    policy: CoordinationPolicy
    existing_claims: frozenset[str]
    claim_owners: dict[str, str]
    claim_timestamps: Optional[dict[str, str]] = None


def create_target_id(
    program_id: str,
    asset_id: str,
    vulnerability_class: str
) -> TargetID:
    """Create a unique target identifier with computed hash.

    Args:
        program_id: Bounty program identifier
        asset_id: Target asset identifier
        vulnerability_class: Type of vulnerability

    Returns:
        TargetID with SHA-256 hash of inputs
    """
    # Compute deterministic hash
    combined = f"{program_id}|{asset_id}|{vulnerability_class}"
    target_hash = hashlib.sha256(combined.encode()).hexdigest()

    return TargetID(
        program_id=program_id,
        asset_id=asset_id,
        vulnerability_class=vulnerability_class,
        target_hash=target_hash
    )
