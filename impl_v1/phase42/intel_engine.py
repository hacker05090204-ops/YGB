# Phase-42: Target Intelligence Engine
"""Deterministic target intelligence and prioritization."""

import uuid
from datetime import datetime
from typing import Optional, List, Dict

from .intel_types import (
    TargetProfile, ScopeChange, IntelligenceResult,
    TargetPriority, TechAge, BugDensity, ScopeStatus, IntelligenceConfidence,
)


def estimate_tech_age(years: int) -> TechAge:
    """Estimate tech age category from years."""
    if years < 0:
        return TechAge.UNKNOWN
    if years >= 10:
        return TechAge.LEGACY
    if years >= 5:
        return TechAge.MATURE
    if years >= 2:
        return TechAge.MODERN
    return TechAge.RECENT


def estimate_bug_density(bugs_per_kloc: float) -> BugDensity:
    """Estimate bug density category."""
    if bugs_per_kloc < 0:
        return BugDensity.UNKNOWN
    if bugs_per_kloc > 10:
        return BugDensity.VERY_HIGH
    if bugs_per_kloc >= 5:
        return BugDensity.HIGH
    if bugs_per_kloc >= 2:
        return BugDensity.MEDIUM
    return BugDensity.LOW


def calculate_priority(
    tech_age: TechAge,
    bug_density: BugDensity,
    scope_status: ScopeStatus,
) -> TargetPriority:
    """Calculate target priority deterministically."""
    if scope_status == ScopeStatus.OUT_OF_SCOPE:
        return TargetPriority.SKIP
    
    # LEGACY + HIGH density = CRITICAL
    if tech_age == TechAge.LEGACY and bug_density in [BugDensity.VERY_HIGH, BugDensity.HIGH]:
        return TargetPriority.CRITICAL
    
    # MATURE + any high density = HIGH
    if tech_age == TechAge.MATURE and bug_density in [BugDensity.VERY_HIGH, BugDensity.HIGH]:
        return TargetPriority.HIGH
    
    # MODERN with medium density = MEDIUM
    if tech_age == TechAge.MODERN and bug_density == BugDensity.MEDIUM:
        return TargetPriority.MEDIUM
    
    # Recent with low density = LOW
    if tech_age == TechAge.RECENT and bug_density == BugDensity.LOW:
        return TargetPriority.LOW
    
    # Unknown = MEDIUM (conservative)
    return TargetPriority.MEDIUM


def create_target_profile(
    target_id: str,
    tech_years: int,
    bugs_per_kloc: float,
    scope_status: ScopeStatus,
) -> TargetProfile:
    """Create a target profile with calculated metrics."""
    tech_age = estimate_tech_age(tech_years)
    bug_density = estimate_bug_density(bugs_per_kloc)
    priority = calculate_priority(tech_age, bug_density, scope_status)
    
    confidence = IntelligenceConfidence.HIGH
    if tech_age == TechAge.UNKNOWN or bug_density == BugDensity.UNKNOWN:
        confidence = IntelligenceConfidence.LOW
    
    return TargetProfile(
        target_id=target_id,
        priority=priority,
        tech_age=tech_age,
        bug_density=bug_density,
        scope_status=scope_status,
        confidence=confidence,
        last_updated=datetime.utcnow().isoformat() + "Z",
    )


def track_scope_change(
    target_id: str,
    old_status: ScopeStatus,
    new_status: ScopeStatus,
    reason: str,
) -> ScopeChange:
    """Track a scope change."""
    return ScopeChange(
        change_id=f"SCH-{uuid.uuid4().hex[:16].upper()}",
        target_id=target_id,
        old_status=old_status,
        new_status=new_status,
        changed_at=datetime.utcnow().isoformat() + "Z",
        reason=reason,
    )


def query_intelligence(
    target_id: str,
    profiles: Dict[str, TargetProfile],
) -> IntelligenceResult:
    """Query intelligence for a target."""
    profile = profiles.get(target_id)
    
    if not profile:
        return IntelligenceResult(
            query_id=f"QRY-{uuid.uuid4().hex[:16].upper()}",
            target_id=target_id,
            profile=None,
            recommendation="No intelligence available. Proceed with caution.",
            confidence=IntelligenceConfidence.NONE,
        )
    
    if profile.scope_status == ScopeStatus.OUT_OF_SCOPE:
        return IntelligenceResult(
            query_id=f"QRY-{uuid.uuid4().hex[:16].upper()}",
            target_id=target_id,
            profile=profile,
            recommendation="OUT OF SCOPE - DO NOT TEST",
            confidence=IntelligenceConfidence.HIGH,
        )
    
    return IntelligenceResult(
        query_id=f"QRY-{uuid.uuid4().hex[:16].upper()}",
        target_id=target_id,
        profile=profile,
        recommendation=f"Priority: {profile.priority.value}",
        confidence=profile.confidence,
    )
