"""
impl_v1 Phase-35 Execution Interface Context.

DESIGN-ONLY SPECIFICATION of execution interfaces.
Contains FROZEN dataclasses only.

THIS MODULE HAS NO EXECUTION AUTHORITY.

ALL DATACLASSES ARE FROZEN (frozen=True):
- ExecutorInterface: 4 fields
- ExecutionIntent: 3 fields
- InterfaceEvaluationResult: 3 fields
"""
from dataclasses import dataclass
from typing import Tuple

from .phase35_types import (
    ExecutorClass,
    CapabilityType,
    InterfaceDecision,
)


@dataclass(frozen=True)
class ExecutorInterface:
    """Interface definition for an executor.
    
    Immutable once created.
    
    Attributes:
        executor_id: Unique identifier
        executor_class: Class of executor
        declared_capabilities: Tuple of capabilities
        version: Version string
    """
    executor_id: str
    executor_class: ExecutorClass
    declared_capabilities: Tuple[CapabilityType, ...]
    version: str


@dataclass(frozen=True)
class ExecutionIntent:
    """Intent for execution.
    
    Immutable once created.
    
    Attributes:
        intent_id: Unique identifier
        description: Human-readable description
        required_capabilities: Tuple of required capabilities
    """
    intent_id: str
    description: str
    required_capabilities: Tuple[CapabilityType, ...]


@dataclass(frozen=True)
class InterfaceEvaluationResult:
    """Result of interface evaluation.
    
    Immutable once created.
    
    Attributes:
        decision: Final decision
        missing_capabilities: Tuple of missing capabilities
        reasons: Tuple of reason strings
    """
    decision: InterfaceDecision
    missing_capabilities: Tuple[CapabilityType, ...]
    reasons: Tuple[str, ...]
