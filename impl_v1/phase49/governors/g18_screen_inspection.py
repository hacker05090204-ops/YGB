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

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import ctypes
from ctypes import wintypes
from datetime import datetime, UTC
import platform
import uuid

try:
    from PIL import ImageGrab
except Exception:  # pragma: no cover - optional runtime dependency
    ImageGrab = None

try:
    import psutil
except Exception:  # pragma: no cover - optional runtime dependency
    psutil = None


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
    location: Optional[str]
    confidence: float
    timestamp: str


@dataclass(frozen=True)
class InspectionResult:
    """Result of screen inspection."""

    result_id: str
    request_id: str
    status: InspectionStatus
    findings: tuple
    voice_explanation_en: str
    voice_explanation_hi: str
    completed_at: str


@dataclass(frozen=True)
class _ForegroundWindowInfo:
    title: str
    class_name: str
    process_name: Optional[str]
    rect: Optional[Tuple[int, int, int, int]]


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


_inspection_requests: Dict[str, ScreenInspectionRequest] = {}
_inspection_results: Dict[str, InspectionResult] = {}

NATIVE_CAPTURE_AVAILABLE = platform.system().lower() == "windows"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _make_finding(
    finding_type: FindingType,
    description: str,
    confidence: float,
    *,
    location: Optional[str] = None,
) -> ScreenFinding:
    return ScreenFinding(
        finding_id=f"FND-{uuid.uuid4().hex[:16].upper()}",
        finding_type=finding_type,
        description=description,
        location=location,
        confidence=confidence,
        timestamp=_now_iso(),
    )


def _get_foreground_window_info() -> Optional[_ForegroundWindowInfo]:
    if platform.system().lower() != "windows":
        return None

    try:
        user32 = ctypes.windll.user32
    except Exception:
        return None

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    title_length = user32.GetWindowTextLengthW(hwnd)
    title_buffer = ctypes.create_unicode_buffer(title_length + 1)
    user32.GetWindowTextW(hwnd, title_buffer, title_length + 1)

    class_buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_buffer, 256)

    rect = _Rect()
    rect_tuple = None
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        rect_tuple = (rect.left, rect.top, rect.right, rect.bottom)

    process_name = None
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    if process_id.value and psutil is not None:
        try:
            process_name = psutil.Process(process_id.value).name()
        except Exception:
            process_name = None

    return _ForegroundWindowInfo(
        title=title_buffer.value.strip(),
        class_name=class_buffer.value.strip(),
        process_name=process_name,
        rect=rect_tuple,
    )


def _capture_screen_size() -> Optional[Tuple[int, int]]:
    if ImageGrab is None:
        return None

    try:
        image = ImageGrab.grab(all_screens=True)
    except Exception:
        return None

    width, height = image.size
    if width <= 0 or height <= 0:
        return None
    return width, height


def _browser_like(window: _ForegroundWindowInfo) -> bool:
    blob = " ".join(
        value.lower()
        for value in (window.title, window.class_name, window.process_name or "")
        if value
    )
    return any(
        keyword in blob
        for keyword in (
            "chrome",
            "msedge",
            "edge",
            "firefox",
            "brave",
            "opera",
            "browser",
            "iexplore",
        )
    )


def _form_like(window: _ForegroundWindowInfo) -> bool:
    blob = " ".join(
        value.lower()
        for value in (window.title, window.class_name)
        if value
    )
    return any(
        keyword in blob
        for keyword in ("login", "sign in", "signin", "password", "verify", "otp", "auth")
    )


def _collect_live_findings() -> List[ScreenFinding]:
    findings: List[ScreenFinding] = []

    window = _get_foreground_window_info()
    screen_size = _capture_screen_size()

    if window is None and screen_size is None:
        raise RuntimeError(
            "Local read-only inspection is unavailable: no foreground window metadata "
            "and no desktop capture frame could be collected."
        )

    if window is not None:
        location = None
        if window.rect is not None:
            location = ",".join(str(value) for value in window.rect)

        title_bits = [window.title or "Untitled window"]
        if window.process_name:
            title_bits.append(f"process={window.process_name}")
        findings.append(
            _make_finding(
                FindingType.WINDOW_DETECTED,
                "Foreground window: " + " | ".join(title_bits),
                0.99,
                location=location,
            )
        )

        if _browser_like(window):
            findings.append(
                _make_finding(
                    FindingType.BROWSER_DETECTED,
                    f"Browser-like foreground window detected: {window.title or window.process_name or window.class_name}",
                    0.95,
                    location=location,
                )
            )

        if _form_like(window):
            findings.append(
                _make_finding(
                    FindingType.FORM_DETECTED,
                    f"Foreground window title suggests an authentication or input form: {window.title or window.class_name}",
                    0.82,
                    location=location,
                )
            )

        if window.title:
            findings.append(
                _make_finding(
                    FindingType.TEXT_DETECTED,
                    f"Visible title text: {window.title}",
                    0.88,
                    location=location,
                )
            )

    if screen_size is not None:
        width, height = screen_size
        findings.append(
            _make_finding(
                FindingType.ELEMENT_DETECTED,
                f"Screen frame captured at {width}x{height}",
                1.0,
                location=f"{width}x{height}",
            )
        )

    return findings


def _build_voice_explanations(findings: List[ScreenFinding]) -> Tuple[str, str]:
    if not findings:
        return (
            "Screen inspection complete. No significant findings were captured in read-only mode.",
            "Screen inspection complete. Read-only mode mein koi significant findings capture nahi hui.",
        )

    summary = []
    for finding in findings[:4]:
        summary.append(f"{finding.finding_type.value}: {finding.description}")

    voice_en = f"Read-only screen inspection captured {len(findings)} findings. " + " ".join(summary)
    voice_hi = f"Read-only screen inspection ne {len(findings)} findings capture ki. " + " ".join(summary)
    return voice_en, voice_hi


def get_inspection_mode_info() -> Dict:
    """Return truthful mode info for runtime status reporting."""

    available = NATIVE_CAPTURE_AVAILABLE
    return {
        "is_stub": False,
        "native_capture_available": available,
        "mode": "LOCAL_READ_ONLY" if available else "UNAVAILABLE_READ_ONLY",
        "description": (
            "Local OS-backed read-only inspection is enabled. Findings come from foreground "
            "window metadata and desktop capture when the session allows it."
        )
        if available
        else (
            "Local read-only inspection backend is unavailable on this host. "
            "Requests will be denied instead of inventing findings."
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
        mode=InspectionMode.READ_ONLY,
        status=InspectionStatus.PENDING,
        created_at=_now_iso(),
    )
    _inspection_requests[request.request_id] = request
    return request


def can_execute_inspection(request: ScreenInspectionRequest) -> tuple:
    """Check whether inspection can proceed."""

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
    allowed, _ = can_execute_inspection(request)
    next_status = InspectionStatus.AUTHORIZED if allowed else InspectionStatus.DENIED

    updated = ScreenInspectionRequest(
        request_id=request.request_id,
        device_id=request.device_id,
        user_id=request.user_id,
        device_trusted=request.device_trusted,
        user_verified=request.user_verified,
        mode=request.mode,
        status=next_status,
        created_at=request.created_at,
    )
    _inspection_requests[request_id] = updated
    return updated


def perform_inspection(request_id: str) -> Optional[InspectionResult]:
    """Perform live read-only inspection using local host signals only."""

    if request_id not in _inspection_requests:
        return None

    request = _inspection_requests[request_id]
    if request.status != InspectionStatus.AUTHORIZED:
        return None

    _inspection_requests[request_id] = ScreenInspectionRequest(
        request_id=request.request_id,
        device_id=request.device_id,
        user_id=request.user_id,
        device_trusted=request.device_trusted,
        user_verified=request.user_verified,
        mode=request.mode,
        status=InspectionStatus.IN_PROGRESS,
        created_at=request.created_at,
    )

    try:
        findings = _collect_live_findings()
        voice_en, voice_hi = _build_voice_explanations(findings)
        status = InspectionStatus.COMPLETED
    except Exception as exc:
        findings = []
        voice_en = f"BLOCKED: {exc}"
        voice_hi = f"BLOCKED: {exc}"
        status = InspectionStatus.DENIED

    result = InspectionResult(
        result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
        request_id=request_id,
        status=status,
        findings=tuple(findings),
        voice_explanation_en=voice_en,
        voice_explanation_hi=voice_hi,
        completed_at=_now_iso(),
    )
    _inspection_results[request_id] = result

    _inspection_requests[request_id] = ScreenInspectionRequest(
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


def can_inspection_interact() -> tuple:
    """Inspection is always read-only."""

    return False, "Screen inspection is READ-ONLY - no clicks, no keyboard, no interaction allowed"


def get_inspection_result(request_id: str) -> Optional[InspectionResult]:
    """Get inspection result by request ID."""

    return _inspection_results.get(request_id)
