"""
Phase-03 Trust Boundaries
REIMPLEMENTED-2026

Defines trust boundary crossing rules and validation.
Trust boundaries control transitions between trust zones.

This module contains NO execution logic.
All boundaries are immutable.
"""

from dataclasses import dataclass
from typing import Final

from python.phase03_trust.trust_zones import TrustZone, get_trust_level
from python.phase01_core.errors import Phase01Error


# =============================================================================
# TRUST VIOLATION ERROR
# =============================================================================

@dataclass(frozen=True)
class TrustViolationError(Phase01Error):
    """
    Raised when a trust boundary violation is detected.
    
    Trust violations occur when:
    - Lower trust zone attempts to escalate to higher trust
    - External input attempts to claim system trust
    - Unauthorized zone crossing is attempted
    """
    source_zone: str = ""
    target_zone: str = ""
    
    def __str__(self) -> str:
        return f"[TRUST VIOLATION] {self.source_zone} → {self.target_zone}: {self.message}"


# =============================================================================
# TRUST BOUNDARY DATACLASS
# =============================================================================

@dataclass(frozen=True)
class TrustBoundary:
    """
    Represents a trust boundary crossing.
    
    Boundaries are frozen (immutable) after creation.
    """
    source_zone: TrustZone
    """The originating trust zone."""
    
    target_zone: TrustZone
    """The destination trust zone."""
    
    requires_validation: bool
    """Whether this crossing requires validation."""
    
    allowed: bool = True
    """Whether this crossing is allowed at all."""


# =============================================================================
# TRUST CROSSING LOGIC
# =============================================================================

def check_trust_crossing(source: TrustZone, target: TrustZone) -> TrustBoundary:
    """
    Check if a trust zone crossing is valid.
    
    Rules:
    - Same zone crossing: no validation needed
    - Higher to lower trust: no validation needed
    - Lower to higher trust: validation required, may be forbidden
    - HUMAN zone: can access any zone without validation
    - Escalation attempts: validation required, NOT allowed
    
    Args:
        source: The originating trust zone.
        target: The destination trust zone.
        
    Returns:
        TrustBoundary describing the crossing rules.
    """
    source_level = get_trust_level(source)
    target_level = get_trust_level(target)
    
    # Same zone - no validation needed
    if source == target:
        return TrustBoundary(
            source_zone=source,
            target_zone=target,
            requires_validation=False,
            allowed=True,
        )
    
    # HUMAN zone can access anything without validation
    if source == TrustZone.HUMAN:
        return TrustBoundary(
            source_zone=source,
            target_zone=target,
            requires_validation=False,
            allowed=True,
        )
    
    # Higher trust to lower trust - no validation needed
    if source_level > target_level:
        return TrustBoundary(
            source_zone=source,
            target_zone=target,
            requires_validation=False,
            allowed=True,
        )
    
    # Lower trust to higher trust - this is a potential escalation
    # Escalation attempts require validation and are NOT allowed
    return TrustBoundary(
        source_zone=source,
        target_zone=target,
        requires_validation=True,
        allowed=False,
    )
