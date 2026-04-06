# G18: Screen Passive Observation Inspection
"""Infrastructure-gated screen inspection contract with passive-only enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional
from datetime import UTC, datetime
import uuid

from .g02_browser_types import BrowserProfile
from .g03_browser_safety import BrowserSafetyGuard


SCREEN_INSPECTION_PROVISIONING_MESSAGE = (
    "ScreenInspector requires headless browser runtime. Set YGB_BROWSER_RUNTIME env var."
)


class RealBackendNotConfiguredError(RuntimeError):
    pass


class InspectionMode(str, Enum):
    """Passive observation only; legacy read-only alias retained for compatibility."""

    PASSIVE_ONLY = "PASSIVE_ONLY"
    READ_ONLY = PASSIVE_ONLY


class InspectionStatus(str, Enum):
    """Legacy inspection status exports retained for compatibility."""

    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    DENIED = "DENIED"


class FindingType(str, Enum):
    """Legacy finding categories retained for compatibility with existing imports."""

    WINDOW_DETECTED = "WINDOW_DETECTED"
    BROWSER_DETECTED = "BROWSER_DETECTED"
    FORM_DETECTED = "FORM_DETECTED"
    TEXT_DETECTED = "TEXT_DETECTED"
    ELEMENT_DETECTED = "ELEMENT_DETECTED"


@dataclass(frozen=True)
class ScreenFinding:
    """Legacy finding export retained for compatibility."""

    finding_id: str
    finding_type: FindingType
    description: str
    location: Optional[str]
    confidence: float
    timestamp: str


@dataclass(frozen=True)
class InspectionResult:
    """Real inspection result contract for a future passive observation backend."""

    inspection_id: str
    target_url: str
    inspected_at: str
    elements_found: int
    issues_detected: list[str]
    status: str


@dataclass(frozen=True)
class ScreenInspectionRequest:
    """Governed request envelope for passive screen inspection."""

    request_id: str
    device_id: str
    user_id: str
    device_trusted: bool
    user_verified: bool
    profile: BrowserProfile
    target_url: str
    mode: InspectionMode
    status: InspectionStatus
    created_at: str


_inspection_requests: Dict[str, ScreenInspectionRequest] = {}
_inspection_results: Dict[str, InspectionResult] = {}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ScreenInspector:
    """Fail-closed passive observation gateway pending real runtime provisioning."""

    def __init__(self, *, safety_guard: BrowserSafetyGuard | None = None):
        self._safety_guard = safety_guard or BrowserSafetyGuard()

    @staticmethod
    def passive_observation_contract() -> dict[str, bool]:
        """Explicitly forbid mutation and active security probing in production paths."""

        return {
            "mutation_allowed": False,
            "regex_xss_scanning_allowed": False,
            "nmap_allowed": False,
            "automated_exploit_detection_allowed": False,
        }

    def _enforce_passive_only(self) -> None:
        contract = self.passive_observation_contract()
        if any(contract.values()):
            raise PermissionError("Screen inspection contract violated: passive observation only")

    def inspect(self, profile: BrowserProfile, target_url: str) -> InspectionResult:
        """Validate governed browser safety first, then fail closed pending real runtime."""

        if not self._safety_guard.is_safe(profile):
            raise PermissionError("Unsafe browser profile blocked from screen inspection")

        del target_url
        self._enforce_passive_only()
        raise RealBackendNotConfiguredError(SCREEN_INSPECTION_PROVISIONING_MESSAGE)


def get_inspection_mode_info() -> Dict[str, object]:
    """Return truthful infrastructure-gated mode info for runtime status reporting."""

    return {
        "is_stub": False,
        "native_capture_available": False,
        "mode": "INFRASTRUCTURE_GATED_PASSIVE_ONLY",
        "description": (
            "Passive observation contract is defined, but the real headless browser runtime "
            "is not provisioned. Requests fail closed with RealBackendNotConfiguredError."
        ),
    }


def clear_inspection_store() -> None:
    """Clear request and result state for tests."""

    _inspection_requests.clear()
    _inspection_results.clear()


def create_inspection_request(
    device_id: str,
    user_id: str,
    device_trusted: bool,
    user_verified: bool,
    *,
    profile: BrowserProfile,
    target_url: str,
) -> ScreenInspectionRequest:
    """Create a governed passive inspection request without inventing runtime output."""

    request = ScreenInspectionRequest(
        request_id=f"INS-{uuid.uuid4().hex[:16].upper()}",
        device_id=device_id,
        user_id=user_id,
        device_trusted=device_trusted,
        user_verified=user_verified,
        profile=profile,
        target_url=target_url,
        mode=InspectionMode.PASSIVE_ONLY,
        status=InspectionStatus.PENDING,
        created_at=_now_iso(),
    )
    _inspection_requests[request.request_id] = request
    return request


def can_execute_inspection(request: ScreenInspectionRequest) -> tuple[bool, str]:
    """Check whether a passive inspection request can proceed to governed runtime gating."""

    if not request.device_trusted:
        return False, "Device is not trusted - inspection denied"
    if not request.user_verified:
        return False, "User identity not verified - inspection denied"
    if request.mode != InspectionMode.PASSIVE_ONLY:
        return False, "Only PASSIVE_ONLY mode is allowed - inspection denied"
    return True, "Inspection authorized - passive observation only"


def authorize_inspection(request_id: str) -> Optional[ScreenInspectionRequest]:
    """Authorize an inspection request when device and user gates pass."""

    if request_id not in _inspection_requests:
        return None

    request = _inspection_requests[request_id]
    allowed, _ = can_execute_inspection(request)
    next_status = InspectionStatus.AUTHORIZED if allowed else InspectionStatus.DENIED
    updated = ScreenInspectionRequest(
        request_id=request.request_id,
        device_id=request.device_id,
        user_id=request.user_id,
        device_trusted=request.device_trusted,
        user_verified=request.user_verified,
        profile=request.profile,
        target_url=request.target_url,
        mode=request.mode,
        status=next_status,
        created_at=request.created_at,
    )
    _inspection_requests[request_id] = updated
    return updated


def perform_inspection(request_id: str) -> Optional[InspectionResult]:
    """Delegate to the governed screen inspector; never fabricate inspection output."""

    if request_id not in _inspection_requests:
        return None

    request = _inspection_requests[request_id]
    if request.status != InspectionStatus.AUTHORIZED:
        return None

    result = ScreenInspector().inspect(request.profile, request.target_url)
    _inspection_results[request_id] = result
    return result


def can_inspection_interact() -> tuple[bool, str]:
    """Screen inspection is permanently passive-only."""

    return (
        False,
        "Screen inspection is PASSIVE ONLY - no mutation, no regex XSS scanning, no nmap, no automated exploit detection",
    )


def get_inspection_result(request_id: str) -> Optional[InspectionResult]:
    """Get an inspection result when a future real backend records one."""

    return _inspection_results.get(request_id)
