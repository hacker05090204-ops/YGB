# G02: Browser Engine Types
"""
Python types for browser control.

NOTE: This module contains TYPES ONLY.
Actual browser execution is in C++ (native/browser_engine.cpp).
Python governs all browser operations.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class BrowserType(Enum):
    """CLOSED ENUM - 2 browser types"""
    UNGOOGLED_CHROMIUM = "UNGOOGLED_CHROMIUM"  # Default, headed
    EDGE_HEADLESS = "EDGE_HEADLESS"            # Last resort fallback


class BrowserLaunchMode(Enum):
    """CLOSED ENUM - 2 modes"""
    HEADED = "HEADED"      # Default - user can see
    HEADLESS = "HEADLESS"  # Requires explicit approval


class BrowserRequestStatus(Enum):
    """CLOSED ENUM - 4 statuses"""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class BrowserLaunchRequest:
    """Request to launch a browser."""
    request_id: str
    browser_type: BrowserType
    mode: BrowserLaunchMode
    target_url: str
    scope_check_passed: bool
    ethics_check_passed: bool
    duplicate_check_passed: bool
    mutex_check_passed: bool
    human_approved: bool
    reason: str


@dataclass(frozen=True)
class BrowserLaunchResult:
    """Result of browser launch attempt."""
    request_id: str
    status: BrowserRequestStatus
    browser_type: Optional[BrowserType]
    mode: Optional[BrowserLaunchMode]
    error_message: Optional[str]
    fallback_used: bool
    fallback_reason: Optional[str]


def validate_launch_request(request: BrowserLaunchRequest) -> Tuple[bool, str]:
    """
    Validate a browser launch request.
    
    Returns (is_valid, reason).
    """
    # All governance checks must pass
    if not request.scope_check_passed:
        return False, "Scope check failed"
    if not request.ethics_check_passed:
        return False, "Ethics check failed"
    if not request.duplicate_check_passed:
        return False, "Duplicate check failed"
    if not request.mutex_check_passed:
        return False, "Mutex check failed"
    if not request.human_approved:
        return False, "Human approval required"
    
    # Headless requires explicit justification
    if request.mode == BrowserLaunchMode.HEADLESS:
        if not request.reason:
            return False, "Headless mode requires explicit reason"
    
    return True, "All checks passed"


def create_launch_result(
    request: BrowserLaunchRequest,
    success: bool,
    error: Optional[str] = None,
    fallback_used: bool = False,
    fallback_reason: Optional[str] = None,
) -> BrowserLaunchResult:
    """Create a browser launch result."""
    return BrowserLaunchResult(
        request_id=request.request_id,
        status=BrowserRequestStatus.APPROVED if success else BrowserRequestStatus.FAILED,
        browser_type=request.browser_type if success else None,
        mode=request.mode if success else None,
        error_message=error,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
    )
