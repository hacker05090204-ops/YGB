"""
Phase-01 Core Module
REIMPLEMENTED-2026

Immutable system-wide constants, identities, and invariants.
This is the foundation that every future phase MUST obey.

This module contains NO execution logic.
"""

from python.phase01_core.constants import (
    REIMPLEMENTED_2026,
    SYSTEM_NAME,
    SYSTEM_VERSION,
    PHASE_NUMBER,
    PHASE_NAME,
    HUMAN_AUTHORITY_ABSOLUTE,
    AUTONOMOUS_EXECUTION_ALLOWED,
    BACKGROUND_EXECUTION_ALLOWED,
    MUTATION_REQUIRES_HUMAN_CONFIRMATION,
    AUDIT_REQUIRED,
    EXPLICIT_ONLY,
)

from python.phase01_core.invariants import (
    INVARIANT_HUMAN_AUTHORITY_ABSOLUTE,
    INVARIANT_NO_AUTONOMOUS_EXECUTION,
    INVARIANT_NO_BACKGROUND_ACTIONS,
    INVARIANT_NO_SCORING_OR_RANKING,
    INVARIANT_MUTATION_REQUIRES_CONFIRMATION,
    INVARIANT_EVERYTHING_AUDITABLE,
    INVARIANT_EVERYTHING_EXPLICIT,
    check_all_invariants,
    get_all_invariants,
)

from python.phase01_core.identities import (
    Identity,
    HUMAN,
    SYSTEM,
    get_all_identities,
)

from python.phase01_core.errors import (
    Phase01Error,
    InvariantViolationError,
    UnauthorizedActorError,
    ConstantMutationError,
    ForbiddenPatternError,
)

__all__ = [
    # Constants
    'REIMPLEMENTED_2026',
    'SYSTEM_NAME',
    'SYSTEM_VERSION',
    'PHASE_NUMBER',
    'PHASE_NAME',
    'HUMAN_AUTHORITY_ABSOLUTE',
    'AUTONOMOUS_EXECUTION_ALLOWED',
    'BACKGROUND_EXECUTION_ALLOWED',
    'MUTATION_REQUIRES_HUMAN_CONFIRMATION',
    'AUDIT_REQUIRED',
    'EXPLICIT_ONLY',
    # Invariants
    'INVARIANT_HUMAN_AUTHORITY_ABSOLUTE',
    'INVARIANT_NO_AUTONOMOUS_EXECUTION',
    'INVARIANT_NO_BACKGROUND_ACTIONS',
    'INVARIANT_NO_SCORING_OR_RANKING',
    'INVARIANT_MUTATION_REQUIRES_CONFIRMATION',
    'INVARIANT_EVERYTHING_AUDITABLE',
    'INVARIANT_EVERYTHING_EXPLICIT',
    'check_all_invariants',
    'get_all_invariants',
    # Identities
    'Identity',
    'HUMAN',
    'SYSTEM',
    'get_all_identities',
    # Errors
    'Phase01Error',
    'InvariantViolationError',
    'UnauthorizedActorError',
    'ConstantMutationError',
    'ForbiddenPatternError',
]
