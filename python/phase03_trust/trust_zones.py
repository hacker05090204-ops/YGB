"""
Phase-03 Trust Zones
REIMPLEMENTED-2026

Defines trust zones in the system.
Trust zones represent different levels of trust authority.

This module contains NO execution logic.
All trust zones are immutable.
"""

from enum import Enum
from typing import Dict, Final


class TrustZone(Enum):
    """
    Trust zones in the system.
    
    Ordered from highest to lowest trust:
    - HUMAN: Absolute trust (human operator)
    - GOVERNANCE: Immutable trust (frozen governance artifacts)
    - SYSTEM: Conditional trust (authenticated system components)
    - EXTERNAL: Zero trust (untrusted external sources)
    """
    HUMAN = "human"
    GOVERNANCE = "governance"
    SYSTEM = "system"
    EXTERNAL = "external"


# =============================================================================
# TRUST LEVEL MAPPING
# =============================================================================

_TRUST_LEVELS: Final[Dict[TrustZone, int]] = {
    TrustZone.HUMAN: 100,
    TrustZone.GOVERNANCE: 80,
    TrustZone.SYSTEM: 50,
    TrustZone.EXTERNAL: 0,
}


# =============================================================================
# TRUST ZONE FUNCTIONS
# =============================================================================

def get_trust_level(zone: TrustZone) -> int:
    """
    Get the trust level for a zone.
    
    Args:
        zone: The trust zone.
        
    Returns:
        Integer trust level (0-100).
    """
    return _TRUST_LEVELS[zone]


def get_all_trust_zones() -> Dict[str, TrustZone]:
    """
    Get all defined trust zones.
    
    Returns:
        Dictionary mapping zone names to TrustZone values.
    """
    return {zone.name: zone for zone in TrustZone}
