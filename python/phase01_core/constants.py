"""
Phase-01 Core Constants
REIMPLEMENTED-2026

Immutable system-wide constants that every future phase MUST obey.
These constants define the non-negotiable foundation of the system.

This module contains NO execution logic.
All constants are UPPERCASE and immutable.
"""

from typing import Final

# =============================================================================
# REIMPLEMENTATION MARKER
# =============================================================================

REIMPLEMENTED_2026: Final[bool] = True
"""Marker indicating this is a 2026 reimplementation, not original code."""

# =============================================================================
# SYSTEM IDENTITY CONSTANTS
# =============================================================================

SYSTEM_NAME: Final[str] = "kali-mcp-toolkit-rebuilt"
"""Official name of the system."""

SYSTEM_VERSION: Final[str] = "1.0.0-reimplemented"
"""System version identifier."""

PHASE_NUMBER: Final[int] = 1
"""This phase number."""

PHASE_NAME: Final[str] = "Core Constants, Identities, and Invariants"
"""Human-readable phase name."""

# =============================================================================
# AUTHORITY CONSTANTS
# =============================================================================

HUMAN_AUTHORITY_ABSOLUTE: Final[bool] = True
"""Human authority is absolute and cannot be overridden."""

AUTONOMOUS_EXECUTION_ALLOWED: Final[bool] = False
"""Autonomous execution is FORBIDDEN. All actions require human initiation."""

BACKGROUND_EXECUTION_ALLOWED: Final[bool] = False
"""Background execution is FORBIDDEN. No daemons, no scheduled tasks."""

# =============================================================================
# MUTATION CONSTANTS
# =============================================================================

MUTATION_REQUIRES_HUMAN_CONFIRMATION: Final[bool] = True
"""All mutations require explicit human confirmation."""

# =============================================================================
# AUDIT CONSTANTS
# =============================================================================

AUDIT_REQUIRED: Final[bool] = True
"""All actions must be auditable and traceable."""

EXPLICIT_ONLY: Final[bool] = True
"""No implicit behavior. Everything must be explicit."""
