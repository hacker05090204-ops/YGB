"""
Phase-01 Core Errors
REIMPLEMENTED-2026

Explicit error types for Phase-01 constraint violations.
All errors are auditable and traceable.

This module contains NO execution logic.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Phase01Error(Exception):
    """Base error for all Phase-01 violations."""
    message: str
    
    def __str__(self) -> str:
        return f"[PHASE-01 ERROR] {self.message}"


@dataclass(frozen=True)
class InvariantViolationError(Phase01Error):
    """
    Raised when an invariant is violated.
    
    Invariant violations are FATAL and cannot be recovered.
    """
    invariant_name: str = ""
    
    def __str__(self) -> str:
        return f"[INVARIANT VIOLATION] {self.invariant_name}: {self.message}"


@dataclass(frozen=True)
class UnauthorizedActorError(Phase01Error):
    """
    Raised when a non-HUMAN actor attempts an unauthorized action.
    
    Only HUMAN may perform authoritative actions.
    """
    actor: str = ""
    action: str = ""
    
    def __str__(self) -> str:
        return f"[UNAUTHORIZED ACTOR] {self.actor} attempted: {self.action} - {self.message}"


@dataclass(frozen=True)
class ConstantMutationError(Phase01Error):
    """
    Raised when code attempts to mutate a constant.
    
    Constants are immutable by definition.
    """
    constant_name: str = ""
    
    def __str__(self) -> str:
        return f"[CONSTANT MUTATION] Cannot modify {self.constant_name}: {self.message}"


@dataclass(frozen=True)
class ForbiddenPatternError(Phase01Error):
    """
    Raised when a forbidden pattern is detected.
    
    Forbidden patterns include: auto_*, score, rank, severity,
    background, daemon, thread, async, schedule.
    """
    pattern: str = ""
    location: str = ""
    
    def __str__(self) -> str:
        return f"[FORBIDDEN PATTERN] '{self.pattern}' found in {self.location}: {self.message}"
