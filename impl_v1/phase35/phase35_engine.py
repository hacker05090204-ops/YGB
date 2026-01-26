"""
impl_v1 Phase-35 Execution Interface Engine.

DESIGN-ONLY SPECIFICATION of execution interfaces.
Contains PURE VALIDATION FUNCTIONS ONLY.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER RUNS EXECUTION.
THIS MODULE ONLY VALIDATES EXECUTION INTERFACES.

VALIDATION FUNCTIONS ONLY:
- validate_executor_id
- validate_executor_interface
- validate_execution_intent
- validate_capabilities
- evaluate_execution_interface
- get_interface_decision

GOVERNANCE RULES:
- UNKNOWN executor → DENY
- NETWORK capability → ESCALATE
- Capability mismatch → DENY
- Empty intent → DENY
- Default = DENY

DENY-BY-DEFAULT.
"""
import re
from typing import Optional, Set, Tuple

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


# Regex pattern for valid executor ID
_EXECUTOR_ID_PATTERN = re.compile(r'^EXECUTOR-[a-fA-F0-9]{8,}$')

# Regex pattern for valid intent ID
_INTENT_ID_PATTERN = re.compile(r'^INTENT-[a-fA-F0-9]{8,}$')


def validate_executor_id(executor_id: Optional[str]) -> bool:
    """Validate an executor ID format.
    
    Args:
        executor_id: Executor ID to validate
        
    Returns:
        True if valid, False otherwise
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Empty → False
        - Invalid format → False
    """
    if executor_id is None:
        return False
    if not isinstance(executor_id, str):
        return False
    if not executor_id.strip():
        return False
    return bool(_EXECUTOR_ID_PATTERN.match(executor_id))


def validate_executor_interface(
    interface: Optional[ExecutorInterface]
) -> Tuple[bool, Tuple[str, ...]]:
    """Validate an executor interface.
    
    Args:
        interface: ExecutorInterface to validate
        
    Returns:
        Tuple of (is_valid, reasons)
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Invalid ID → False
        - UNKNOWN class → False
        - Invalid capabilities → False
    """
    reasons: list[str] = []
    
    if interface is None:
        return False, ("Missing executor interface",)
    
    # Validate executor_id
    if not validate_executor_id(interface.executor_id):
        reasons.append("Invalid executor ID")
    
    # Validate executor_class
    if not isinstance(interface.executor_class, ExecutorClass):
        reasons.append("Invalid executor class")
    elif interface.executor_class == ExecutorClass.UNKNOWN:
        reasons.append("UNKNOWN executor class not permitted")
    
    # Validate version
    if not interface.version or not isinstance(interface.version, str):
        reasons.append("Missing version")
    elif not interface.version.strip():
        reasons.append("Empty version")
    
    # Validate capabilities
    if not isinstance(interface.declared_capabilities, tuple):
        reasons.append("Capabilities must be a tuple")
    else:
        for cap in interface.declared_capabilities:
            if not isinstance(cap, CapabilityType):
                reasons.append("Invalid capability in declared_capabilities")
                break
    
    return len(reasons) == 0, tuple(reasons)


def validate_execution_intent(
    intent: Optional[ExecutionIntent]
) -> Tuple[bool, Tuple[str, ...]]:
    """Validate an execution intent.
    
    Args:
        intent: ExecutionIntent to validate
        
    Returns:
        Tuple of (is_valid, reasons)
        
    Rules:
        - DENY-BY-DEFAULT
        - None → False
        - Invalid intent ID → False
        - Empty description → False
    """
    reasons: list[str] = []
    
    if intent is None:
        return False, ("Missing execution intent",)
    
    # Validate intent_id
    if not intent.intent_id or not isinstance(intent.intent_id, str):
        reasons.append("Missing intent ID")
    elif not intent.intent_id.strip():
        reasons.append("Empty intent ID")
    elif not _INTENT_ID_PATTERN.match(intent.intent_id):
        reasons.append("Invalid intent ID format")
    
    # Validate description
    if not intent.description or not isinstance(intent.description, str):
        reasons.append("Missing description")
    elif not intent.description.strip():
        reasons.append("Empty description")
    
    # Validate required_capabilities
    if not isinstance(intent.required_capabilities, tuple):
        reasons.append("Required capabilities must be a tuple")
    else:
        for cap in intent.required_capabilities:
            if not isinstance(cap, CapabilityType):
                reasons.append("Invalid capability in required_capabilities")
                break
    
    return len(reasons) == 0, tuple(reasons)


def validate_capabilities(
    interface: Optional[ExecutorInterface],
    intent: Optional[ExecutionIntent]
) -> Tuple[bool, Tuple[CapabilityType, ...]]:
    """Validate capability match.
    
    Args:
        interface: ExecutorInterface
        intent: ExecutionIntent
        
    Returns:
        Tuple of (all_matched, missing_capabilities)
        
    Rules:
        - DENY-BY-DEFAULT
        - None → all missing
        - Missing capability → listed
    """
    if interface is None:
        return False, ()
    if intent is None:
        return False, ()
    
    declared: Set[CapabilityType] = set(interface.declared_capabilities)
    required: Set[CapabilityType] = set(intent.required_capabilities)
    
    missing = required - declared
    
    if len(missing) == 0:
        return True, ()
    else:
        return False, tuple(sorted(missing, key=lambda x: x.value))


def evaluate_execution_interface(
    interface: Optional[ExecutorInterface],
    intent: Optional[ExecutionIntent]
) -> InterfaceEvaluationResult:
    """Evaluate execution interface.
    
    Args:
        interface: ExecutorInterface
        intent: ExecutionIntent
        
    Returns:
        InterfaceEvaluationResult with decision
        
    Rules:
        - DENY-BY-DEFAULT
        - None interface → DENY
        - None intent → DENY
        - Invalid interface → DENY
        - Invalid intent → DENY
        - UNKNOWN executor → DENY
        - Capability mismatch → DENY
        - NETWORK capability → ESCALATE
        - All valid → ALLOW
    """
    # DENY-BY-DEFAULT: None interface
    if interface is None:
        return InterfaceEvaluationResult(
            decision=InterfaceDecision.DENY,
            missing_capabilities=(),
            reasons=("Missing executor interface",)
        )
    
    # DENY-BY-DEFAULT: None intent
    if intent is None:
        return InterfaceEvaluationResult(
            decision=InterfaceDecision.DENY,
            missing_capabilities=(),
            reasons=("Missing execution intent",)
        )
    
    # Validate interface
    iface_valid, iface_reasons = validate_executor_interface(interface)
    if not iface_valid:
        return InterfaceEvaluationResult(
            decision=InterfaceDecision.DENY,
            missing_capabilities=(),
            reasons=iface_reasons
        )
    
    # Validate intent
    intent_valid, intent_reasons = validate_execution_intent(intent)
    if not intent_valid:
        return InterfaceEvaluationResult(
            decision=InterfaceDecision.DENY,
            missing_capabilities=(),
            reasons=intent_reasons
        )
    
    # Check capability match
    caps_match, missing_caps = validate_capabilities(interface, intent)
    if not caps_match:
        return InterfaceEvaluationResult(
            decision=InterfaceDecision.DENY,
            missing_capabilities=missing_caps,
            reasons=("Missing required capabilities",)
        )
    
    # ESCALATE: NETWORK capability
    if CapabilityType.NETWORK in intent.required_capabilities:
        return InterfaceEvaluationResult(
            decision=InterfaceDecision.ESCALATE,
            missing_capabilities=(),
            reasons=("NETWORK capability requires human approval",)
        )
    
    # All checks passed → ALLOW
    return InterfaceEvaluationResult(
        decision=InterfaceDecision.ALLOW,
        missing_capabilities=(),
        reasons=()
    )


def get_interface_decision(
    result: Optional[InterfaceEvaluationResult]
) -> InterfaceDecision:
    """Get interface decision from result.
    
    Args:
        result: InterfaceEvaluationResult
        
    Returns:
        InterfaceDecision
        
    Rules:
        - DENY-BY-DEFAULT
        - None → DENY
        - Invalid decision type → DENY
        - Valid → result's decision
    """
    if result is None:
        return InterfaceDecision.DENY
    if not isinstance(result.decision, InterfaceDecision):
        return InterfaceDecision.DENY
    return result.decision
