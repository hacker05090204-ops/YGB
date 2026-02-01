"""
Phase-02 Actors Module
REIMPLEMENTED-2026

Actor definitions for the Actor & Role Model.
Actors represent entities that can perform actions in the system.

This module contains NO execution logic.
All actors are frozen and immutable.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Final, Dict


# =============================================================================
# ACTOR TYPE ENUM
# =============================================================================

class ActorType(Enum):
    """
    Types of actors in the system.
    
    Only two actor types are allowed:
    - HUMAN: The human operator with full authority
    - SYSTEM: The automated system with no autonomous authority
    """
    HUMAN = "human"
    SYSTEM = "system"


# =============================================================================
# ACTOR CLASS
# =============================================================================

@dataclass(frozen=True)
class Actor:
    """
    Represents an actor in the system.
    
    Actors are frozen (immutable) after creation.
    Attributes cannot be modified.
    """
    
    actor_id: str
    """Unique identifier for the actor."""
    
    actor_type: ActorType
    """Type of actor (HUMAN or SYSTEM)."""
    
    name: str
    """Human-readable name of the actor."""
    
    trust_level: int
    """Trust level (0-100). HUMAN=100, SYSTEM=0."""


# =============================================================================
# PREDEFINED ACTORS
# =============================================================================

HUMAN_ACTOR: Final[Actor] = Actor(
    actor_id="HUMAN",
    actor_type=ActorType.HUMAN,
    name="Human Operator",
    trust_level=100,
)
"""The HUMAN actor - has full authority and trust."""

SYSTEM_ACTOR: Final[Actor] = Actor(
    actor_id="SYSTEM",
    actor_type=ActorType.SYSTEM,
    name="System Executor",
    trust_level=0,
)
"""The SYSTEM actor - no autonomous authority."""


# =============================================================================
# ACTOR REGISTRY
# =============================================================================

class ActorRegistry:
    """
    Registry of all actors in the system.
    
    Provides access to predefined actors.
    """
    
    _actors: Dict[str, Actor] = {
        "HUMAN": HUMAN_ACTOR,
        "SYSTEM": SYSTEM_ACTOR,
    }
    
    def get_actor(self, actor_id: str) -> Actor:
        """
        Get an actor by ID.
        
        Args:
            actor_id: The unique actor identifier.
            
        Returns:
            The Actor instance.
            
        Raises:
            KeyError: If actor not found.
        """
        return self._actors[actor_id]
    
    def get_all_actors(self) -> Dict[str, Actor]:
        """
        Get all registered actors.
        
        Returns:
            Dictionary of actor_id to Actor.
        """
        return dict(self._actors)
