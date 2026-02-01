"""
Phase-09 Bounty Context.

Defines immutable dataclasses for bounty policy and submission context.

All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BountyPolicy:
    """Immutable bounty program policy definition.

    Defines what is in-scope and out-of-scope for a bounty program.

    Attributes:
        policy_id: Unique policy identifier
        policy_name: Human-readable policy name
        in_scope_assets: Set of assets within scope
        excluded_assets: Set of explicitly excluded assets
        accepted_vuln_types: Set of accepted vulnerability types
        excluded_vuln_types: Set of explicitly excluded vuln types
        active: Whether the policy is currently active
        require_proof_of_concept: Whether POC is required
    """

    policy_id: str
    policy_name: str
    in_scope_assets: frozenset[str]
    excluded_assets: frozenset[str]
    accepted_vuln_types: frozenset[str]
    excluded_vuln_types: frozenset[str]
    active: bool
    require_proof_of_concept: bool


@dataclass(frozen=True)
class BountyContext:
    """Immutable context for evaluating a bounty submission.

    Contains all information needed to make an eligibility decision.

    Attributes:
        submission_id: Unique submission identifier
        target_asset: Target domain/asset being reported
        vulnerability_type: Type of vulnerability reported
        affected_parameter: Specific parameter affected (optional)
        root_cause_hash: Hash identifying the root cause
        researcher_id: Identifier of the researcher
        submission_timestamp: ISO timestamp of submission
        has_proof_of_concept: Whether POC was provided
        policy: The bounty policy to evaluate against
        prior_submission_hashes: Hashes of prior submissions for duplicate check
    """

    submission_id: str
    target_asset: str
    vulnerability_type: str
    affected_parameter: Optional[str]
    root_cause_hash: str
    researcher_id: str
    submission_timestamp: str
    has_proof_of_concept: bool
    policy: BountyPolicy
    prior_submission_hashes: frozenset[str]
