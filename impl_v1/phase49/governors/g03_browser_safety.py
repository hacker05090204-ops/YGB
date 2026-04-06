# G03: Browser Safety Adapter
"""
Pre-launch safety checks integrating Phase-41, 44, 46.

ANY CHECK FAILURE = HARD BLOCK

This is the gatekeeper before any browser can launch.
"""

from dataclasses import dataclass
from enum import Enum
import logging
from typing import List, Optional
import uuid
from datetime import datetime, UTC

from impl_v1.phase49.governors.g02_browser_types import (
    BrowserProfile,
    can_profile_store_credentials,
    can_profile_write,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SafetyCheck:
    """Single browser preflight check result."""
    check_id: str
    check_type: str
    passed: bool
    detail: str


class BrowserSafetyGuard:
    """Preflight browser safety gate with no unsafe bypass path."""

    def __init__(self, guard_logger: Optional[logging.Logger] = None):
        self._logger = guard_logger or logger

    def _new_check(self, check_type: str, passed: bool, detail: str) -> SafetyCheck:
        return SafetyCheck(
            check_id=f"CHK-{uuid.uuid4().hex[:12].upper()}",
            check_type=check_type,
            passed=passed,
            detail=detail,
        )

    def run_preflight(self, profile: BrowserProfile) -> list[SafetyCheck]:
        """Run required browser profile checks before a session can start."""
        checks = [
            self._new_check(
                "profile_headless_true",
                profile.headless,
                "Browser profile must run headless",
            ),
            self._new_check(
                "profile_sandboxed_true",
                profile.sandboxed,
                "Browser profile must be sandboxed",
            ),
            self._new_check(
                "no_write_permissions",
                not can_profile_write(profile),
                "Browser profile must not allow write permissions",
            ),
            self._new_check(
                "no_credential_storage",
                not can_profile_store_credentials(profile),
                "Browser profile must not store credentials",
            ),
            self._new_check(
                "domain_whitelist_non_empty",
                bool(profile.allowed_domains),
                "Browser profile must define a non-empty domain whitelist",
            ),
        ]

        for check in checks:
            if not check.passed:
                self._logger.warning(check.detail)

        return checks

    def is_safe(self, profile: BrowserProfile) -> bool:
        """Return ``True`` only when every required preflight check passes."""
        return all(check.passed for check in self.run_preflight(profile))

    def start_session(self, profile: BrowserProfile) -> dict[str, str]:
        """Start a browser session only when the governed profile is safe."""
        checks = self.run_preflight(profile)
        if not all(check.passed for check in checks):
            raise PermissionError("Unsafe browser profile blocked from starting a session")

        return {
            "session_id": f"BRW-{uuid.uuid4().hex[:16].upper()}",
            "profile_id": profile.profile_id,
        }


class BrowserSafetyCheck(Enum):
    """CLOSED ENUM - 5 safety checks"""
    SCOPE = "SCOPE"                # Phase-44
    ETHICS = "ETHICS"              # Phase-44
    DUPLICATE = "DUPLICATE"        # Phase-41
    MUTEX = "MUTEX"                # Phase-46
    HUMAN_APPROVAL = "HUMAN_APPROVAL"


class SafetyCheckResult(Enum):
    """CLOSED ENUM - 3 results"""
    PASS = "PASS"
    FAIL = "FAIL"
    PENDING = "PENDING"


@dataclass(frozen=True)
class SafetyCheckEntry:
    """Single safety check result."""
    check_type: BrowserSafetyCheck
    result: SafetyCheckResult
    reason: str
    timestamp: str


@dataclass(frozen=True)
class BrowserSafetyResult:
    """Aggregate safety check result."""
    result_id: str
    all_passed: bool
    checks: tuple  # Tuple[SafetyCheckEntry, ...]
    blocked_by: Optional[BrowserSafetyCheck]
    block_reason: Optional[str]


def check_scope(target_url: str, allowed_domains: List[str]) -> SafetyCheckEntry:
    """Check if target URL is in scope."""
    from urllib.parse import urlparse
    
    try:
        parsed = urlparse(target_url)
        domain = parsed.netloc.lower()
        
        for allowed in allowed_domains:
            if domain == allowed.lower() or domain.endswith("." + allowed.lower()):
                return SafetyCheckEntry(
                    check_type=BrowserSafetyCheck.SCOPE,
                    result=SafetyCheckResult.PASS,
                    reason=f"Domain {domain} is in scope",
                    timestamp=datetime.now(UTC).isoformat(),
                )
        
        return SafetyCheckEntry(
            check_type=BrowserSafetyCheck.SCOPE,
            result=SafetyCheckResult.FAIL,
            reason=f"Domain {domain} is OUT OF SCOPE",
            timestamp=datetime.now(UTC).isoformat(),
        )
    except Exception as e:
        return SafetyCheckEntry(
            check_type=BrowserSafetyCheck.SCOPE,
            result=SafetyCheckResult.FAIL,
            reason=f"URL parse error: {str(e)}",
            timestamp=datetime.now(UTC).isoformat(),
        )


def check_ethics(action_type: str, prohibited_actions: List[str]) -> SafetyCheckEntry:
    """Check if action is ethically allowed."""
    if action_type.upper() in [a.upper() for a in prohibited_actions]:
        return SafetyCheckEntry(
            check_type=BrowserSafetyCheck.ETHICS,
            result=SafetyCheckResult.FAIL,
            reason=f"Action {action_type} is PROHIBITED",
            timestamp=datetime.now(UTC).isoformat(),
        )
    
    return SafetyCheckEntry(
        check_type=BrowserSafetyCheck.ETHICS,
        result=SafetyCheckResult.PASS,
        reason=f"Action {action_type} is allowed",
        timestamp=datetime.now(UTC).isoformat(),
    )


def check_duplicate(target_id: str, known_targets: List[str]) -> SafetyCheckEntry:
    """Check for duplicate target."""
    if target_id in known_targets:
        return SafetyCheckEntry(
            check_type=BrowserSafetyCheck.DUPLICATE,
            result=SafetyCheckResult.FAIL,
            reason=f"Target {target_id} is a DUPLICATE",
            timestamp=datetime.now(UTC).isoformat(),
        )
    
    return SafetyCheckEntry(
        check_type=BrowserSafetyCheck.DUPLICATE,
        result=SafetyCheckResult.PASS,
        reason="No duplicate found",
        timestamp=datetime.now(UTC).isoformat(),
    )


def check_mutex(resource_id: str, locked_resources: List[str]) -> SafetyCheckEntry:
    """Check mutex/parallel conflict."""
    if resource_id in locked_resources:
        return SafetyCheckEntry(
            check_type=BrowserSafetyCheck.MUTEX,
            result=SafetyCheckResult.FAIL,
            reason=f"Resource {resource_id} is LOCKED",
            timestamp=datetime.now(UTC).isoformat(),
        )
    
    return SafetyCheckEntry(
        check_type=BrowserSafetyCheck.MUTEX,
        result=SafetyCheckResult.PASS,
        reason="No mutex conflict",
        timestamp=datetime.now(UTC).isoformat(),
    )


def check_human_approval(approved: bool, approver_id: Optional[str]) -> SafetyCheckEntry:
    """Check human approval status."""
    if not approved:
        return SafetyCheckEntry(
            check_type=BrowserSafetyCheck.HUMAN_APPROVAL,
            result=SafetyCheckResult.FAIL,
            reason="Human approval NOT granted",
            timestamp=datetime.now(UTC).isoformat(),
        )
    
    return SafetyCheckEntry(
        check_type=BrowserSafetyCheck.HUMAN_APPROVAL,
        result=SafetyCheckResult.PASS,
        reason=f"Approved by {approver_id}",
        timestamp=datetime.now(UTC).isoformat(),
    )


def check_browser_safety(
    target_url: str,
    action_type: str,
    target_id: str,
    resource_id: str,
    human_approved: bool,
    approver_id: Optional[str],
    allowed_domains: List[str],
    prohibited_actions: List[str],
    known_targets: List[str],
    locked_resources: List[str],
) -> BrowserSafetyResult:
    """
    Run all safety checks.
    
    ANY FAILURE = BLOCK
    """
    checks = [
        check_scope(target_url, allowed_domains),
        check_ethics(action_type, prohibited_actions),
        check_duplicate(target_id, known_targets),
        check_mutex(resource_id, locked_resources),
        check_human_approval(human_approved, approver_id),
    ]
    
    # Find first failure
    blocked_by = None
    block_reason = None
    for check in checks:
        if check.result == SafetyCheckResult.FAIL:
            blocked_by = check.check_type
            block_reason = check.reason
            break
    
    all_passed = blocked_by is None
    
    return BrowserSafetyResult(
        result_id=f"SAF-{uuid.uuid4().hex[:16].upper()}",
        all_passed=all_passed,
        checks=tuple(checks),
        blocked_by=blocked_by,
        block_reason=block_reason,
    )
