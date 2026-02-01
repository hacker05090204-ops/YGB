"""
Phase-02 Permissions Module
REIMPLEMENTED-2026

Permission model for the Actor & Role Model.
Permissions define what actions can be performed.

This module contains NO execution logic.
All permissions are immutable.
"""

from enum import Enum

from python.phase02_actors.actors import ActorType
from python.phase01_core.errors import UnauthorizedActorError


# =============================================================================
# PERMISSION ENUM
# =============================================================================

class Permission(Enum):
    """
    Permissions in the system.
    
    These define what actions can be performed.
    """
    INITIATE = "initiate"
    """Start actions - HUMAN only."""
    
    CONFIRM = "confirm"
    """Confirm mutations - HUMAN only."""
    
    OVERRIDE = "override"
    """Override other actors - HUMAN only."""
    
    EXECUTE = "execute"
    """Execute approved actions - SYSTEM can do this."""
    
    AUDIT = "audit"
    """View audit logs - HUMAN only."""


# =============================================================================
# PERMISSION CHECKING
# =============================================================================

def check_permission(actor_type: ActorType, permission: Permission) -> bool:
    """
    Check if an actor type has a permission.
    
    Args:
        actor_type: The actor type to check.
        permission: The permission to check for.
        
    Returns:
        True if the actor type has the permission, False otherwise.
    """
    # Import here to avoid circular import
    from python.phase02_actors.roles import get_actor_role, get_role_permissions
    
    role = get_actor_role(actor_type)
    permissions = get_role_permissions(role)
    
    return permission in permissions


def require_permission(actor_type: ActorType, permission: Permission) -> None:
    """
    Require that an actor type has a permission.
    
    Args:
        actor_type: The actor type to check.
        permission: The permission required.
        
    Raises:
        UnauthorizedActorError: If the actor type lacks the permission.
    """
    if not check_permission(actor_type, permission):
        raise UnauthorizedActorError(
            message=f"Actor type {actor_type.value} lacks permission {permission.value}",
            actor=actor_type.value,
            action=permission.value,
        )
