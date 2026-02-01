"""
Phase-02 Roles Module
REIMPLEMENTED-2026

Role definitions for the Actor & Role Model.
Roles define what permissions an actor type has.

This module contains NO execution logic.
All roles are immutable.
"""

from enum import Enum
from typing import FrozenSet

from python.phase02_actors.actors import ActorType
from python.phase02_actors.permissions import Permission


# =============================================================================
# ROLE ENUM
# =============================================================================

class Role(Enum):
    """
    Roles in the system.
    
    Only two roles are allowed:
    - OPERATOR: Human role with full permissions
    - EXECUTOR: System role with limited permissions
    """
    OPERATOR = "operator"
    EXECUTOR = "executor"


# =============================================================================
# ROLE PERMISSIONS MAPPING
# =============================================================================

_ROLE_PERMISSIONS: dict[Role, FrozenSet[Permission]] = {
    Role.OPERATOR: frozenset({
        Permission.INITIATE,
        Permission.CONFIRM,
        Permission.OVERRIDE,
        Permission.EXECUTE,
        Permission.AUDIT,
    }),
    Role.EXECUTOR: frozenset({
        Permission.EXECUTE,
    }),
}

_ACTOR_TYPE_TO_ROLE: dict[ActorType, Role] = {
    ActorType.HUMAN: Role.OPERATOR,
    ActorType.SYSTEM: Role.EXECUTOR,
}


# =============================================================================
# ROLE FUNCTIONS
# =============================================================================

def get_role_permissions(role: Role) -> FrozenSet[Permission]:
    """
    Get the permissions for a role.
    
    Args:
        role: The role to get permissions for.
        
    Returns:
        FrozenSet of Permission values.
    """
    return _ROLE_PERMISSIONS[role]


def get_actor_role(actor_type: ActorType) -> Role:
    """
    Get the role assigned to an actor type.
    
    Args:
        actor_type: The actor type.
        
    Returns:
        The Role assigned to that actor type.
    """
    return _ACTOR_TYPE_TO_ROLE[actor_type]
