# G18: Screen Read-Only Inspection
"""
Screen inspection in READ-ONLY mode only.

If user says "takeover the screen":
1. Verify device trust
2. Verify user identity
3. Inspect screen READ-ONLY
4. Explain findings via VOICE
5. NO clicks, NO interaction

STRICT:
- Only READ_ONLY mode allowed
- NO mouse/keyboard interaction
- NO window manipulation
- Findings explained via voice only
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict
import uuid
import json
import os
from datetime import datetime, UTC
from pathlib import Path


class InspectionMode(Enum):
    """CLOSED ENUM - 1 mode (READ_ONLY only)"""

    READ_ONLY = "READ_ONLY"


class InspectionStatus(Enum):
    """CLOSED ENUM - 5 statuses"""

    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    DENIED = "DENIED"
    FAILED = "FAILED"


class FindingType(Enum):
    """CLOSED ENUM - 5 finding types"""

    WINDOW_DETECTED = "WINDOW_DETECTED"
    BROWSER_DETECTED = "BROWSER_DETECTED"
    FORM_DETECTED = "FORM_DETECTED"
    TEXT_DETECTED = "TEXT_DETECTED"
    ELEMENT_DETECTED = "ELEMENT_DETECTED"


@dataclass(frozen=True)
class ScreenInspectionRequest:
    """Request for screen inspection."""

    request_id: str
    device_id: str
    user_id: str
    device_trusted: bool
    user_verified: bool
    mode: InspectionMode
    status: InspectionStatus
    created_at: str


@dataclass(frozen=True)
class ScreenFinding:
    """A finding from screen inspection."""

    finding_id: str
    finding_type: FindingType
    description: str
    location: Optional[str]  # Window/region identifier
    confidence: float
    timestamp: str


@dataclass(frozen=True)
class InspectionResult:
    """Result of screen inspection."""

    result_id: str
    request_id: str
    status: InspectionStatus
    findings: tuple  # Tuple[ScreenFinding, ...]
    voice_explanation_en: str
    voice_explanation_hi: str
    completed_at: str


# In-memory stores
_inspection_requests: Dict[str, ScreenInspectionRequest] = {}
_inspection_results: Dict[str, InspectionResult] = {}


def clear_inspection_store():
    """Clear inspection store (for testing)."""
    _inspection_requests.clear()
    _inspection_results.clear()


def create_inspection_request(
    device_id: str,
    user_id: str,
    device_trusted: bool,
    user_verified: bool,
) -> ScreenInspectionRequest:
    """Create a screen inspection request."""
    request = ScreenInspectionRequest(
        request_id=f"INS-{uuid.uuid4().hex[:16].upper()}",
        device_id=device_id,
        user_id=user_id,
        device_trusted=device_trusted,
        user_verified=user_verified,
        mode=InspectionMode.READ_ONLY,  # Always READ_ONLY
        status=InspectionStatus.PENDING,
        created_at=datetime.now(UTC).isoformat(),
    )
    _inspection_requests[request.request_id] = request
    return request


def can_execute_inspection(request: ScreenInspectionRequest) -> tuple:
    """
    Check if inspection can proceed.

    Returns:
        (allowed: bool, reason: str)
    """
    if not request.device_trusted:
        return False, "Device is not trusted - inspection denied"

    if not request.user_verified:
        return False, "User identity not verified - inspection denied"

    if request.mode != InspectionMode.READ_ONLY:
        return False, "Only READ_ONLY mode is allowed - inspection denied"

    return True, "Inspection authorized - read-only mode"


def authorize_inspection(request_id: str) -> Optional[ScreenInspectionRequest]:
    """Authorize an inspection request if checks pass."""
    if request_id not in _inspection_requests:
        return None

    request = _inspection_requests[request_id]
    allowed, reason = can_execute_inspection(request)

    if not allowed:
        denied = ScreenInspectionRequest(
            request_id=request.request_id,
            device_id=request.device_id,
            user_id=request.user_id,
            device_trusted=request.device_trusted,
            user_verified=request.user_verified,
            mode=request.mode,
            status=InspectionStatus.DENIED,
            created_at=request.created_at,
        )
        _inspection_requests[request_id] = denied
        return denied

    authorized = ScreenInspectionRequest(
        request_id=request.request_id,
        device_id=request.device_id,
        user_id=request.user_id,
        device_trusted=request.device_trusted,
        user_verified=request.user_verified,
        mode=request.mode,
        status=InspectionStatus.AUTHORIZED,
        created_at=request.created_at,
    )
    _inspection_requests[request_id] = authorized
    return authorized


def _load_findings_from_path(path_value: str) -> List[Dict]:
    payload = json.loads(Path(path_value).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Inspection backend payload must be a JSON list")
    return payload


def _build_result(
    request: ScreenInspectionRequest,
    status: InspectionStatus,
    findings: List[ScreenFinding],
    voice_en: str,
    voice_hi: str,
) -> InspectionResult:
    result = InspectionResult(
        result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
        request_id=request.request_id,
        status=status,
        findings=tuple(findings),
        voice_explanation_en=voice_en,
        voice_explanation_hi=voice_hi,
        completed_at=datetime.now(UTC).isoformat(),
    )
    _inspection_results[request.request_id] = result
    _inspection_requests[request.request_id] = ScreenInspectionRequest(
        request_id=request.request_id,
        device_id=request.device_id,
        user_id=request.user_id,
        device_trusted=request.device_trusted,
        user_verified=request.user_verified,
        mode=request.mode,
        status=status,
        created_at=request.created_at,
    )
    return result


def perform_inspection(
    request_id: str,
    _mock_findings: Optional[List[Dict]] = None,  # For testing
    findings_path: Optional[str] = None,
) -> Optional[InspectionResult]:
    """
    Perform screen inspection in READ-ONLY mode.

    Python only processes externally produced inspection findings.
    It never clicks, types, or manipulates the screen.
    """
    if request_id not in _inspection_requests:
        return None

    request = _inspection_requests[request_id]

    if request.status != InspectionStatus.AUTHORIZED:
        return None

    # Update status to in progress
    in_progress = ScreenInspectionRequest(
        request_id=request.request_id,
        device_id=request.device_id,
        user_id=request.user_id,
        device_trusted=request.device_trusted,
        user_verified=request.user_verified,
        mode=request.mode,
        status=InspectionStatus.IN_PROGRESS,
        created_at=request.created_at,
    )
    _inspection_requests[request_id] = in_progress

    findings_payload: List[Dict]
    if _mock_findings is not None:
        findings_payload = _mock_findings
    else:
        path_value = (
            findings_path
            or os.environ.get("YGB_SCREEN_INSPECTION_FINDINGS_PATH", "").strip()
        )
        if not path_value:
            return _build_result(
                request,
                InspectionStatus.FAILED,
                [],
                "Screen inspection backend unavailable. No real inspection findings were produced.",
                "Screen inspection backend unavailable. Koi real findings produce nahi hui.",
            )
        try:
            findings_payload = _load_findings_from_path(path_value)
        except Exception as exc:
            return _build_result(
                request,
                InspectionStatus.FAILED,
                [],
                f"Screen inspection failed: {exc}",
                f"Screen inspection failed: {exc}",
            )

    findings = []
    for item in findings_payload:
        finding_type_name = str(item.get("type", "TEXT_DETECTED")).upper()
        finding = ScreenFinding(
            finding_id=f"FND-{uuid.uuid4().hex[:16].upper()}",
            finding_type=FindingType[finding_type_name],
            description=str(item.get("description", "")),
            location=item.get("location"),
            confidence=float(item.get("confidence", 0.0) or 0.0),
            timestamp=datetime.now(UTC).isoformat(),
        )
        findings.append(finding)

    if findings:
        en_parts = [f"Found {len(findings)} items on screen."]
        hi_parts = [f"Screen par {len(findings)} items mile."]
        for finding in findings[:3]:
            en_parts.append(f"{finding.finding_type.value}: {finding.description}")
            hi_parts.append(f"{finding.finding_type.value}: {finding.description}")
        voice_en = " ".join(en_parts)
        voice_hi = " ".join(hi_parts)
    else:
        voice_en = "Screen inspection completed with zero findings from the configured backend."
        voice_hi = "Configured backend se zero findings mili."

    return _build_result(
        request,
        InspectionStatus.COMPLETED,
        findings,
        voice_en,
        voice_hi,
    )


def can_inspection_interact() -> tuple:
    """Check if inspection can interact with screen. Returns (can_interact, reason)."""
    # Inspection can NEVER interact
    return (
        False,
        "Screen inspection is READ-ONLY - no clicks, no keyboard, no interaction allowed",
    )


def get_inspection_result(request_id: str) -> Optional[InspectionResult]:
    """Get inspection result by request ID."""
    return _inspection_results.get(request_id)
