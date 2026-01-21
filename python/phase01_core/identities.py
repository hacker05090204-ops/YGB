"""
Phase-01 Core Identities
REIMPLEMENTED-2026

Identity model defining HUMAN and SYSTEM actors.
HUMAN is the sole authoritative actor.
SYSTEM is a non-authoritative executor.

This module contains NO execution logic.
All identities are frozen and immutable.
"""

from dataclasses import dataclass
from typing import Final, Dict


# =============================================================================
# IDENTITY CLASS
# =============================================================================

@dataclass(frozen=True)
class Identity:
    """
    Represents an actor identity in the system.
    
    Identities are frozen (immutable) after creation.
    Attributes cannot be modified.
    """
    
    name: str
    """Unique name of the identity."""
    
    is_authoritative: bool
    """Whether this identity has authoritative decision power."""
    
    can_initiate: bool
    """Whether this identity can initiate actions."""
    
    can_confirm: bool
    """Whether this identity can confirm mutations."""
    
    can_be_overridden: bool
    """Whether this identity's decisions can be overridden."""
    
    authority_level: int
    """Numeric authority level. Higher = more authority."""


# =============================================================================
# IDENTITY INSTANCES
# =============================================================================

HUMAN: Final[Identity] = Identity(
    name="HUMAN",
    is_authoritative=True,
    can_initiate=True,
    can_confirm=True,
    can_be_overridden=False,
    authority_level=100,
)
"""
HUMAN identity - the sole authoritative actor.

HUMAN has absolute authority over all system decisions.
HUMAN cannot be overridden by any other actor.
HUMAN is the only actor that can initiate and confirm actions.
"""

SYSTEM: Final[Identity] = Identity(
    name="SYSTEM",
    is_authoritative=False,
    can_initiate=False,
    can_confirm=False,
    can_be_overridden=True,
    authority_level=0,
)
"""
SYSTEM identity - a non-authoritative executor.

SYSTEM has no authority to make decisions.
SYSTEM can only execute what HUMAN initiates.
SYSTEM can be overridden by HUMAN at any time.
"""


# =============================================================================
# IDENTITY HELPER FUNCTIONS
# =============================================================================

def get_all_identities() -> Dict[str, Identity]:
    """
    Get all defined identities as a dictionary.
    
    Returns:
        Dictionary mapping identity names to Identity instances.
    """
    return {
        'HUMAN': HUMAN,
        'SYSTEM': SYSTEM,
    }
