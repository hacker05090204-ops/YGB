"""
impl_v1 Phase-35 Execution Interface Types.

DESIGN-ONLY SPECIFICATION of execution interfaces.
Contains CLOSED enums only.

THIS MODULE HAS NO EXECUTION AUTHORITY.
THIS MODULE NEVER RUNS EXECUTION.
THIS MODULE ONLY DEFINES WHAT AN EXECUTOR IS.

CLOSED ENUMS:
- ExecutorClass: 4 members (NATIVE, BROWSER, API, UNKNOWN)
- CapabilityType: 4 members
- InterfaceDecision: 3 members (ALLOW, DENY, ESCALATE)

DEFAULT = DENY.
"""
from enum import Enum, auto


class ExecutorClass(Enum):
    """Class of executor.
    
    CLOSED ENUM - Exactly 4 members. No additions permitted.
    
    Classes:
    - NATIVE: Native code executor
    - BROWSER: Browser automation executor
    - API: API request executor
    - UNKNOWN: Unknown class (always DENY)
    """
    NATIVE = auto()
    BROWSER = auto()
    API = auto()
    UNKNOWN = auto()


class CapabilityType(Enum):
    """Type of capability.
    
    CLOSED ENUM - Exactly 4 members. No additions permitted.
    
    Capabilities:
    - COMPUTE: Computation capability
    - FILE_READ: File read capability
    - FILE_WRITE: File write capability
    - NETWORK: Network access capability
    """
    COMPUTE = auto()
    FILE_READ = auto()
    FILE_WRITE = auto()
    NETWORK = auto()


class InterfaceDecision(Enum):
    """Decision from interface evaluation.
    
    CLOSED ENUM - Exactly 3 members. No additions permitted.
    
    Decisions:
    - ALLOW: Interface may proceed
    - DENY: Interface is denied
    - ESCALATE: Requires human review
    """
    ALLOW = auto()
    DENY = auto()
    ESCALATE = auto()
