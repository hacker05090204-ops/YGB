"""
Phase-12 Consistency Engine.

This module provides consistency checking and replay readiness logic.

All functions are pure (no side effects).
All dataclasses are frozen=True for immutability.
"""
from dataclasses import dataclass
from typing import FrozenSet

from .evidence_types import EvidenceState
from .evidence_context import EvidenceBundle, EvidenceSource


@dataclass(frozen=True)
class ConsistencyResult:
    """Immutable consistency check result.
    
    Attributes:
        bundle_id: Bundle that was checked
        state: Resulting evidence state
        source_count: Number of sources evaluated
        matching_count: Number of matching sources
        conflict_detected: Whether conflict exists
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
    """
    bundle_id: str
    state: EvidenceState
    source_count: int
    matching_count: int
    conflict_detected: bool
    reason_code: str
    reason_description: str


@dataclass(frozen=True)
class ReplayReadiness:
    """Immutable replay readiness assessment.
    
    Attributes:
        bundle_id: Bundle that was checked
        is_replayable: Whether replay is possible
        steps_complete: Whether all steps present
        all_deterministic: Whether all steps deterministic
        has_external_deps: Whether external deps exist
        reason_code: Machine-readable reason
        reason_description: Human-readable reason
    """
    bundle_id: str
    is_replayable: bool
    steps_complete: bool
    all_deterministic: bool
    has_external_deps: bool
    reason_code: str
    reason_description: str


def sources_match(sources: FrozenSet[EvidenceSource]) -> bool:
    """Check if all sources have matching finding hashes.
    
    Args:
        sources: Frozen set of evidence sources
        
    Returns:
        True if all sources have the same finding_hash, False otherwise.
        Empty set trivially returns True.
    """
    if not sources:
        return True
    
    hashes = {s.finding_hash for s in sources}
    return len(hashes) == 1


def check_consistency(bundle: EvidenceBundle) -> ConsistencyResult:
    """Check consistency of evidence bundle.
    
    Decision table:
    | Sources | All Match | Conflict | → State | Code |
    |---------|-----------|----------|---------|------|
    | 0 | N/A | N/A | UNVERIFIED | CS-001 |
    | 1 | N/A | N/A | RAW | CS-002 |
    | 2+ | YES | NO | CONSISTENT | CS-003 |
    | 2+ | NO | YES | INCONSISTENT | CS-004 |
    
    Args:
        bundle: Evidence bundle to check
        
    Returns:
        ConsistencyResult with state and reason
    """
    source_count = len(bundle.sources)
    
    # CS-001: No sources → UNVERIFIED
    if source_count == 0:
        return ConsistencyResult(
            bundle_id=bundle.bundle_id,
            state=EvidenceState.UNVERIFIED,
            source_count=0,
            matching_count=0,
            conflict_detected=False,
            reason_code="CS-001",
            reason_description="No sources - unverified"
        )
    
    # CS-002: Single source → RAW
    if source_count == 1:
        return ConsistencyResult(
            bundle_id=bundle.bundle_id,
            state=EvidenceState.RAW,
            source_count=1,
            matching_count=1,
            conflict_detected=False,
            reason_code="CS-002",
            reason_description="Single source - raw"
        )
    
    # Multiple sources - check for match
    all_match = sources_match(bundle.sources)
    
    if all_match:
        # CS-003: All match → CONSISTENT
        return ConsistencyResult(
            bundle_id=bundle.bundle_id,
            state=EvidenceState.CONSISTENT,
            source_count=source_count,
            matching_count=source_count,
            conflict_detected=False,
            reason_code="CS-003",
            reason_description="Multi-source consistent"
        )
    else:
        # CS-004: Conflict → INCONSISTENT
        # Count matching sources (find the most common hash)
        hash_counts: dict[str, int] = {}
        for source in bundle.sources:
            h = source.finding_hash
            hash_counts[h] = hash_counts.get(h, 0) + 1
        max_matching = max(hash_counts.values()) if hash_counts else 0
        
        return ConsistencyResult(
            bundle_id=bundle.bundle_id,
            state=EvidenceState.INCONSISTENT,
            source_count=source_count,
            matching_count=max_matching,
            conflict_detected=True,
            reason_code="CS-004",
            reason_description="Multi-source inconsistent"
        )


def _has_external_deps(steps: tuple) -> bool:
    """Check if steps contain external dependency markers.
    
    Args:
        steps: Tuple of replay steps
        
    Returns:
        True if any step contains EXTERNAL marker
    """
    for step in steps:
        if "EXTERNAL" in step.upper():
            return True
    return False


def _is_deterministic(steps: tuple) -> bool:
    """Check if all steps are deterministic.
    
    Non-deterministic markers: RANDOM, TIMESTAMP, UUID, NOW
    
    Args:
        steps: Tuple of replay steps
        
    Returns:
        True if all steps are deterministic
    """
    non_deterministic_markers = ["RANDOM", "TIMESTAMP", "UUID", "NOW"]
    for step in steps:
        step_upper = step.upper()
        for marker in non_deterministic_markers:
            if marker in step_upper:
                return False
    return True


def check_replay_readiness(bundle: EvidenceBundle) -> ReplayReadiness:
    """Check if evidence bundle is replayable.
    
    Decision table:
    | Steps Present | All Deterministic | External Deps | → Replayable | Code |
    |---------------|-------------------|---------------|--------------|------|
    | NO | Any | Any | NO | RP-001 |
    | YES | NO | Any | NO | RP-002 |
    | YES | YES | YES | NO | RP-003 |
    | YES | YES | NO | YES | RP-004 |
    
    Args:
        bundle: Evidence bundle to check
        
    Returns:
        ReplayReadiness result
    """
    # RP-001: No steps or empty steps → not replayable
    if bundle.replay_steps is None or len(bundle.replay_steps) == 0:
        return ReplayReadiness(
            bundle_id=bundle.bundle_id,
            is_replayable=False,
            steps_complete=False,
            all_deterministic=False,
            has_external_deps=False,
            reason_code="RP-001",
            reason_description="No replay steps present"
        )
    
    steps = bundle.replay_steps
    has_external = _has_external_deps(steps)
    is_deterministic = _is_deterministic(steps)
    
    # RP-002: Non-deterministic steps → not replayable
    if not is_deterministic:
        return ReplayReadiness(
            bundle_id=bundle.bundle_id,
            is_replayable=False,
            steps_complete=True,
            all_deterministic=False,
            has_external_deps=has_external,
            reason_code="RP-002",
            reason_description="Non-deterministic steps"
        )
    
    # RP-003: External dependencies → not replayable
    if has_external:
        return ReplayReadiness(
            bundle_id=bundle.bundle_id,
            is_replayable=False,
            steps_complete=True,
            all_deterministic=True,
            has_external_deps=True,
            reason_code="RP-003",
            reason_description="External dependencies"
        )
    
    # RP-004: All good → replayable
    return ReplayReadiness(
        bundle_id=bundle.bundle_id,
        is_replayable=True,
        steps_complete=True,
        all_deterministic=True,
        has_external_deps=False,
        reason_code="RP-004",
        reason_description="Replay ready"
    )
