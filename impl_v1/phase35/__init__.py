"""
impl_v1 Phase-35 Execution Interface Boundary Mirror.

DESIGN-ONLY SPECIFICATION of execution interfaces.
THIS MODULE NEVER RUNS EXECUTION.
THIS MODULE ONLY DEFINES WHAT AN EXECUTOR IS.
"""
from .phase35_types import (
    ExecutorClass,
    CapabilityType,
    InterfaceDecision,
)
from .phase35_context import (
    ExecutorInterface,
    ExecutionIntent,
    InterfaceEvaluationResult,
)
from .phase35_engine import (
    validate_executor_id,
    validate_executor_interface,
    validate_execution_intent,
    validate_capabilities,
    evaluate_execution_interface,
    get_interface_decision,
)

__all__ = [
    "ExecutorClass",
    "CapabilityType",
    "InterfaceDecision",
    "ExecutorInterface",
    "ExecutionIntent",
    "InterfaceEvaluationResult",
    "validate_executor_id",
    "validate_executor_interface",
    "validate_execution_intent",
    "validate_capabilities",
    "evaluate_execution_interface",
    "get_interface_decision",
]
