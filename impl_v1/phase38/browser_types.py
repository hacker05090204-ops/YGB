# Phase-38: Browser Boundary Governor - Types Module
# GOVERNANCE LAYER ONLY - No browser execution
# Implements pre-browser validation contracts

"""
Phase-38 defines the governance types for browser execution boundary.
This module implements:
- Browser enums (CLOSED)
- Intent/Response dataclasses (frozen=True)
- Validation types

NO BROWSER EXECUTION - PURE TYPE DEFINITIONS AND VALIDATION
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List


# =============================================================================
# CLOSED ENUMS - Browser Types
# =============================================================================

class BrowserType(Enum):
    """
    CLOSED ENUM - 3 members
    Types of browser instances.
    """
    HEADLESS = "HEADLESS"     # No visible window
    HEADED = "HEADED"         # Visible window (requires ESCALATE)
    FORBIDDEN = "FORBIDDEN"   # Never allowed


class BrowserAction(Enum):
    """
    CLOSED ENUM - 8 members
    Actions a browser can perform.
    """
    NAVIGATE = "NAVIGATE"
    CLICK = "CLICK"
    TYPE = "TYPE"
    SCREENSHOT = "SCREENSHOT"
    EXECUTE_SCRIPT = "EXECUTE_SCRIPT"  # NEVER - dangerous
    DOWNLOAD = "DOWNLOAD"              # NEVER - file system access
    COOKIE_ACCESS = "COOKIE_ACCESS"    # ESCALATE
    STORAGE_ACCESS = "STORAGE_ACCESS"  # ESCALATE


class BrowserDecision(Enum):
    """
    CLOSED ENUM - 4 members
    Decisions for browser execution requests.
    """
    ALLOW = "ALLOW"
    DENY = "DENY"
    ESCALATE = "ESCALATE"
    PENDING = "PENDING"


class BrowserDenialReason(Enum):
    """
    CLOSED ENUM - 12 members
    Reasons for browser request denial.
    """
    FORBIDDEN_ACTION = "FORBIDDEN_ACTION"
    INVALID_URL = "INVALID_URL"
    MALFORMED_REQUEST = "MALFORMED_REQUEST"
    SCOPE_EXCEEDED = "SCOPE_EXCEEDED"
    RATE_LIMITED = "RATE_LIMITED"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
    UNSAFE_NAVIGATION = "UNSAFE_NAVIGATION"
    CROSS_ORIGIN_BLOCKED = "CROSS_ORIGIN_BLOCKED"
    HEADED_REQUIRES_HUMAN = "HEADED_REQUIRES_HUMAN"
    HUMAN_DENIED = "HUMAN_DENIED"
    TIMEOUT = "TIMEOUT"
    EXTENSION_BLOCKED = "EXTENSION_BLOCKED"


class BrowserScope(Enum):
    """
    CLOSED ENUM - 5 members
    Scope constraints for browser operations.
    """
    SINGLE_PAGE = "SINGLE_PAGE"     # One page only
    SINGLE_DOMAIN = "SINGLE_DOMAIN" # One domain
    ALLOWLIST = "ALLOWLIST"         # Predefined list
    SESSION = "SESSION"             # Single session
    UNBOUNDED = "UNBOUNDED"         # Requires ESCALATE


class TabIsolation(Enum):
    """
    CLOSED ENUM - 3 members
    Tab isolation levels.
    """
    ISOLATED = "ISOLATED"       # No cross-tab access
    SHARED_CONTEXT = "SHARED_CONTEXT"  # Shared context (ESCALATE)
    FORBIDDEN = "FORBIDDEN"     # Cross-tab never allowed


class StoragePolicy(Enum):
    """
    CLOSED ENUM - 4 members
    Browser storage policies.
    """
    NO_STORAGE = "NO_STORAGE"
    SESSION_ONLY = "SESSION_ONLY"
    ENCRYPTED = "ENCRYPTED"
    PERSISTENT = "PERSISTENT"  # NEVER


# =============================================================================
# ACTION STATE CLASSIFICATION
# =============================================================================

class ActionState(Enum):
    """
    CLOSED ENUM - 3 members
    Governance state for browser actions.
    """
    NEVER = "NEVER"        # Immediately denied
    ESCALATE = "ESCALATE"  # Requires human approval
    ALLOW = "ALLOW"        # Can proceed with validation


# =============================================================================
# FROZEN DATACLASSES
# =============================================================================

@dataclass(frozen=True)
class BrowserIntent:
    """
    Frozen dataclass for a browser execution intent.
    Describes what the browser will do.
    """
    intent_id: str
    browser_type: BrowserType
    action: BrowserAction
    target_url: str
    scope: BrowserScope
    tab_isolation: TabIsolation
    storage_policy: StoragePolicy
    description: str
    timestamp: str
    context_hash: str
    requester_id: str


@dataclass(frozen=True)
class BrowserResponse:
    """
    Frozen dataclass for browser request response.
    """
    intent_id: str
    decision: BrowserDecision
    reason_code: str
    reason_description: str
    simulated_result: bool  # Would have succeeded (NO ACTUAL EXECUTION)
    requires_human: bool


@dataclass(frozen=True)
class BrowserValidationResult:
    """
    Frozen dataclass for validation outcome.
    """
    is_valid: bool
    denial_reason: Optional[BrowserDenialReason]
    description: str


@dataclass(frozen=True)
class BrowserAuditEntry:
    """
    Frozen dataclass for browser audit entries.
    """
    audit_id: str
    intent_id: str
    action: BrowserAction
    target_url: str
    decision: BrowserDecision
    reason_code: str
    timestamp: str
    requester_id: str


@dataclass(frozen=True)
class UrlAllowlist:
    """
    Frozen dataclass for URL allowlist.
    """
    allowlist_id: str
    domains: tuple  # Tuple for immutability
    patterns: tuple
    created_at: str
    expires_at: str


@dataclass(frozen=True)
class BrowserContext:
    """
    Frozen dataclass for browser execution context.
    """
    context_id: str
    browser_type: BrowserType
    scope: BrowserScope
    tab_isolation: TabIsolation
    storage_policy: StoragePolicy
    allowed_domains: tuple
    max_tabs: int
    timeout_seconds: int
    human_override_enabled: bool
