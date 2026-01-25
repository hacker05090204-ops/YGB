"""
Phase-12 Evidence Context.

This module defines frozen dataclasses for evidence data structures.

All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EvidenceSource:
    """Immutable evidence source record.
    
    Attributes:
        source_id: Unique source identifier
        finding_hash: Hash of the finding data
        target_id: Target this evidence relates to
        evidence_type: Category of evidence
        timestamp: When evidence was collected
    """
    source_id: str
    finding_hash: str
    target_id: str
    evidence_type: str
    timestamp: str


@dataclass(frozen=True)
class EvidenceBundle:
    """Immutable bundle of evidence sources.
    
    Attributes:
        bundle_id: Unique bundle identifier
        target_id: Target this bundle relates to
        sources: Frozen set of evidence sources
        replay_steps: Optional tuple of replay steps
    """
    bundle_id: str
    target_id: str
    sources: frozenset  # frozenset[EvidenceSource]
    replay_steps: Optional[tuple] = None  # Optional[tuple[str, ...]]
