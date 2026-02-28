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
from datetime import datetime, UTC


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

# =============================================================================
# STUB MODE INDICATOR — Python stub, no native screen capture driver
# =============================================================================

NATIVE_CAPTURE_AVAILABLE = False  # True only when C++ capture library loaded


def get_inspection_mode_info() -> Dict:
    """Return explicit mode info for truthful status reporting."""
    return {
        "is_stub": not NATIVE_CAPTURE_AVAILABLE,
        "native_capture_available": NATIVE_CAPTURE_AVAILABLE,
        "mode": "STUB_READ_ONLY" if not NATIVE_CAPTURE_AVAILABLE else "NATIVE_READ_ONLY",
        "description": (
            "Python stub — screen findings are mock/test data. "
            "Native C++ capture driver required for real inspection."
        ) if not NATIVE_CAPTURE_AVAILABLE else (
            "Native C++ capture driver active — real screen inspection."
        ),
    }


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


def perform_inspection(
    request_id: str,
    _mock_findings: Optional[List[Dict]] = None,  # For testing
) -> Optional[InspectionResult]:
    """
    Perform screen inspection in READ-ONLY mode.
    
    This is a Python stub - actual screen capture would be done by C++ native code.
    Python receives findings and generates voice explanation.
    """
    if request_id not in _inspection_requests:
        return None
    
    request = _inspection_requests[request_id]
    
    if request.status != InspectionStatus.AUTHORIZED:
        return None

    # PRODUCTION GUARD: If no native capture and no test mock, return BLOCKED
    if _mock_findings is None and not NATIVE_CAPTURE_AVAILABLE:
        result = InspectionResult(
            result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
            request_id=request_id,
            status=InspectionStatus.COMPLETED,
            findings=(),
            voice_explanation_en=(
                "BLOCKED: Native screen capture driver not available. "
                "No findings captured."
            ),
            voice_explanation_hi=(
                "BLOCKED: Native screen capture driver upalabdh nahi. "
                "Koi findings capture nahi hui."
            ),
            completed_at=datetime.now(UTC).isoformat(),
        )
        # Persist result so get_inspection_result() returns it
        _inspection_results[request_id] = result
        # Update request status to COMPLETED
        _inspection_requests[request_id] = ScreenInspectionRequest(
            request_id=request.request_id,
            device_id=request.device_id,
            user_id=request.user_id,
            device_trusted=request.device_trusted,
            user_verified=request.user_verified,
            mode=request.mode,
            status=InspectionStatus.COMPLETED,
            created_at=request.created_at,
        )
        return result
    
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
    
    # Process mock findings for testing
    findings = []
    if _mock_findings:
        for f in _mock_findings:
            finding = ScreenFinding(
                finding_id=f"FND-{uuid.uuid4().hex[:16].upper()}",
                finding_type=FindingType[f.get("type", "TEXT_DETECTED")],
                description=f.get("description", ""),
                location=f.get("location"),
                confidence=f.get("confidence", 0.8),
                timestamp=datetime.now(UTC).isoformat(),
            )
            findings.append(finding)
    
    # Generate voice explanation
    if findings:
        en_parts = [f"Found {len(findings)} items on screen."]
        hi_parts = [f"Screen par {len(findings)} items mile."]
        
        for f in findings[:3]:  # Limit to first 3
            en_parts.append(f"{f.finding_type.value}: {f.description}")
            hi_parts.append(f"{f.finding_type.value}: {f.description}")
        
        voice_en = " ".join(en_parts)
        voice_hi = " ".join(hi_parts)
    else:
        voice_en = "Screen inspection complete. No significant findings in read-only mode."
        voice_hi = "Screen inspection complete. Read-only mode mein koi significant findings nahi."
    
    result = InspectionResult(
        result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
        request_id=request_id,
        status=InspectionStatus.COMPLETED,
        findings=tuple(findings),
        voice_explanation_en=voice_en,
        voice_explanation_hi=voice_hi,
        completed_at=datetime.now(UTC).isoformat(),
    )
    _inspection_results[request_id] = result
    
    # Update request status
    completed = ScreenInspectionRequest(
        request_id=request.request_id,
        device_id=request.device_id,
        user_id=request.user_id,
        device_trusted=request.device_trusted,
        user_verified=request.user_verified,
        mode=request.mode,
        status=InspectionStatus.COMPLETED,
        created_at=request.created_at,
    )
    _inspection_requests[request_id] = completed
    
    return result


def can_inspection_interact() -> tuple:
    """Check if inspection can interact with screen. Returns (can_interact, reason)."""
    # Inspection can NEVER interact
    return False, "Screen inspection is READ-ONLY - no clicks, no keyboard, no interaction allowed"


def get_inspection_result(request_id: str) -> Optional[InspectionResult]:
    """Get inspection result by request ID."""
    return _inspection_results.get(request_id)
