"""
Phase-21 Sandbox Types.

This module defines enums for sandbox & fault isolation.

CLOSED ENUMS - No new members may be added.
"""
from enum import Enum, auto


class ExecutionFaultType(Enum):
    """Execution fault types.
    
    CLOSED ENUM - No new members may be added.
    """
    CRASH = auto()
    TIMEOUT = auto()
    PARTIAL = auto()
    INVALID_RESPONSE = auto()
    RESOURCE_EXHAUSTED = auto()
    SECURITY_VIOLATION = auto()


class SandboxDecision(Enum):
    """Sandbox decisions.
    
    CLOSED ENUM - No new members may be added.
    """
    TERMINATE = auto()
    RETRY = auto()
    ESCALATE = auto()


class RetryPolicy(Enum):
    """Retry policies.
    
    CLOSED ENUM - No new members may be added.
    """
    NO_RETRY = auto()
    RETRY_ONCE = auto()
    RETRY_LIMITED = auto()
    HUMAN_DECISION = auto()


# Fault to retry policy mapping
FAULT_RETRY_POLICY = {
    ExecutionFaultType.CRASH: RetryPolicy.RETRY_LIMITED,
    ExecutionFaultType.TIMEOUT: RetryPolicy.RETRY_LIMITED,
    ExecutionFaultType.PARTIAL: RetryPolicy.NO_RETRY,
    ExecutionFaultType.INVALID_RESPONSE: RetryPolicy.NO_RETRY,
    ExecutionFaultType.RESOURCE_EXHAUSTED: RetryPolicy.HUMAN_DECISION,
    ExecutionFaultType.SECURITY_VIOLATION: RetryPolicy.NO_RETRY,
}

# Retryable fault types
RETRYABLE_FAULTS = frozenset({
    ExecutionFaultType.CRASH,
    ExecutionFaultType.TIMEOUT,
})

# Default max retries
DEFAULT_MAX_RETRIES = 3
