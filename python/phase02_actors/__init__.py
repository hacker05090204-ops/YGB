"""
Phase-02 Actors Module
REIMPLEMENTED-2026

Actor & Role Model for the kali-mcp-toolkit-rebuilt system.
This module defines WHO can do WHAT in the system.

This module contains NO execution logic.
"""

from python.phase02_actors.actors import (
    Actor,
    ActorType,
    ActorRegistry,
    HUMAN_ACTOR,
    SYSTEM_ACTOR,
)

from python.phase02_actors.roles import (
    Role,
    get_role_permissions,
    get_actor_role,
)

from python.phase02_actors.permissions import (
    Permission,
    check_permission,
    require_permission,
)

__all__ = [
    # Actors
    'Actor',
    'ActorType',
    'ActorRegistry',
    'HUMAN_ACTOR',
    'SYSTEM_ACTOR',
    # Roles
    'Role',
    'get_role_permissions',
    'get_actor_role',
    # Permissions
    'Permission',
    'check_permission',
    'require_permission',
]
