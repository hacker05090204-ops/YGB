# G02: Browser Engine Types
"""
Python types for browser control.

NOTE: This module contains TYPES ONLY.
Actual browser execution is in C++ (native/browser_engine.cpp).
Python governs all browser operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


def _normalize_browser_type(browser_type: str | "BrowserType") -> "BrowserType":
    """Normalize browser type strings and enum values, including legacy aliases."""
    if isinstance(browser_type, BrowserType):
        return browser_type

    normalized = str(browser_type).strip().upper()
    for member_name, member in BrowserType.__members__.items():
        if normalized in {member_name, member.value}:
            return member

    raise ValueError(f"Unsupported browser type: {browser_type}")


class BrowserType(str, Enum):
    """Closed browser types governed by the browser profile policy."""
    CHROMIUM = "CHROMIUM"
    FIREFOX = "FIREFOX"
    EDGE = "EDGE"  # EDGE is headless-only by policy

    # Legacy aliases kept for compatibility with existing call sites.
    UNGOOGLED_CHROMIUM = CHROMIUM
    EDGE_HEADLESS = EDGE


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
class BrowserProfile:
    """Governed browser profile for read-only browsing."""
    profile_id: str
    browser_type: str
    headless: bool
    sandboxed: bool
    allowed_domains: list[str]


def can_profile_write(profile: BrowserProfile) -> bool:
    """Profiles are hard-coded to read-only mode."""
    del profile
    return False


def can_profile_submit_forms(profile: BrowserProfile) -> bool:
    """Profiles are not permitted to submit forms."""
    del profile
    return False


def can_profile_store_credentials(profile: BrowserProfile) -> bool:
    """Profiles are not permitted to store credentials."""
    del profile
    return False


class ProfileValidator:
    """Validation for governed browser profiles."""

    @staticmethod
    def validation_errors(profile: BrowserProfile) -> list[str]:
        """Return all policy validation failures for a browser profile."""
        errors: list[str] = []

        try:
            browser_type = _normalize_browser_type(profile.browser_type)
        except ValueError as exc:
            errors.append(str(exc))
            browser_type = None

        if not profile.headless:
            errors.append("Browser profiles must run headless")
        if browser_type == BrowserType.EDGE and not profile.headless:
            errors.append("Edge profiles are headless-only by policy")
        if not profile.sandboxed:
            errors.append("Browser profiles must be sandboxed")
        if not profile.allowed_domains:
            errors.append("Browser profiles must declare at least one allowed domain")
        if can_profile_write(profile):
            errors.append("Write operations are forbidden for browser profiles")
        if can_profile_submit_forms(profile):
            errors.append("Form submission is forbidden for browser profiles")
        if can_profile_store_credentials(profile):
            errors.append("Credential storage is forbidden for browser profiles")

        return errors

    @staticmethod
    def validate(profile: BrowserProfile) -> bool:
        """Return ``True`` only when the profile satisfies all browser policy checks."""
        return not ProfileValidator.validation_errors(profile)


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

    if request.browser_type == BrowserType.EDGE and request.mode != BrowserLaunchMode.HEADLESS:
        return False, "Edge browser is headless-only by policy"

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
