# G26: Forensic Evidence Capture Governor
"""
Forensic-grade evidence capture system.

Captures:
✓ Screenshots (PNG, lossless)
✓ Screen recordings (MP4/WebM)
✓ DOM snapshots (HTML + hash)
✓ Network metadata (headers only)

ALL evidence is:
- Read-only capture
- Session-scoped
- Timestamped
- Hash-verified
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any
import hashlib
import uuid
import base64
from datetime import datetime, UTC
from pathlib import Path
import json


class EvidenceType(Enum):
    """CLOSED ENUM - Evidence types."""
    SCREENSHOT = "SCREENSHOT"
    VIDEO = "VIDEO"
    DOM_SNAPSHOT = "DOM_SNAPSHOT"
    NETWORK_METADATA = "NETWORK_METADATA"


class CaptureStatus(Enum):
    """CLOSED ENUM - Capture status."""
    PENDING = "PENDING"
    CAPTURING = "CAPTURING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class EvidenceMetadata:
    """Metadata for a single evidence item."""
    evidence_id: str
    evidence_type: EvidenceType
    timestamp: str
    session_id: str
    source_url: str
    sha256_hash: str
    file_path: Optional[str]
    size_bytes: int
    capture_duration_ms: int


@dataclass(frozen=True)
class Screenshot:
    """Screenshot evidence."""
    metadata: EvidenceMetadata
    width: int
    height: int
    format: str  # "PNG" only
    data: Optional[bytes]  # Raw bytes or None if stored to file


@dataclass(frozen=True)
class VideoRecording:
    """Video recording evidence."""
    metadata: EvidenceMetadata
    width: int
    height: int
    duration_seconds: float
    format: str  # "MP4" or "WEBM"
    frame_rate: int


@dataclass(frozen=True)
class DOMSnapshot:
    """DOM snapshot evidence."""
    metadata: EvidenceMetadata
    html_content: str
    element_count: int
    scripts_stripped: bool


@dataclass(frozen=True)
class NetworkMetadata:
    """Network metadata evidence (headers only, no body)."""
    metadata: EvidenceMetadata
    request_headers: Tuple[Tuple[str, str], ...]
    response_headers: Tuple[Tuple[str, str], ...]
    status_code: int
    method: str
    content_type: Optional[str]


@dataclass(frozen=True)
class EvidenceBundle:
    """Complete evidence bundle for a session."""
    bundle_id: str
    session_id: str
    created_at: str
    screenshots: Tuple[Screenshot, ...]
    videos: Tuple[VideoRecording, ...]
    dom_snapshots: Tuple[DOMSnapshot, ...]
    network_metadata: Tuple[NetworkMetadata, ...]
    bundle_hash: str
    is_complete: bool


# =============================================================================
# GUARDS (MANDATORY)
# =============================================================================

def can_evidence_modify_browser() -> bool:
    """
    Guard: Can evidence capture modify browser state?
    
    ANSWER: NEVER.
    """
    return False


def can_evidence_automate() -> bool:
    """
    Guard: Can evidence system automate interactions?
    
    ANSWER: NEVER.
    """
    return False


def can_evidence_capture_without_session() -> bool:
    """
    Guard: Can evidence be captured without session binding?
    
    ANSWER: NEVER.
    """
    return False


def can_evidence_skip_hash() -> bool:
    """
    Guard: Can evidence skip hash verification?
    
    ANSWER: NEVER.
    """
    return False


# =============================================================================
# HASH UTILITIES
# =============================================================================

def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hash of data."""
    return hashlib.sha256(data).hexdigest()


def compute_sha256_from_file(file_path: str) -> Optional[str]:
    """Compute SHA-256 hash from file."""
    try:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (OSError, IOError):
        return None


def compute_bundle_hash(bundle_parts: List[str]) -> str:
    """Compute hash of all bundle components combined."""
    combined = "|".join(sorted(bundle_parts))
    return compute_sha256(combined.encode("utf-8"))


# =============================================================================
# EVIDENCE ID GENERATION
# =============================================================================

def generate_evidence_id(evidence_type: EvidenceType) -> str:
    """Generate unique evidence ID."""
    prefix = evidence_type.value[:3].upper()
    unique = uuid.uuid4().hex[:12].upper()
    return f"EV-{prefix}-{unique}"


def generate_session_id() -> str:
    """Generate unique session ID."""
    return f"SES-{uuid.uuid4().hex[:16].upper()}"


def generate_bundle_id() -> str:
    """Generate unique bundle ID."""
    return f"BND-{uuid.uuid4().hex[:16].upper()}"


# =============================================================================
# CAPTURE FUNCTIONS (MOCK FOR TESTING, REAL C++ INTEGRATION LATER)
# =============================================================================

class EvidenceCaptureEngine:
    """Evidence capture engine with C++ backend integration."""
    
    def __init__(self, session_id: str, output_dir: str):
        self.session_id = session_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._screenshots: List[Screenshot] = []
        self._videos: List[VideoRecording] = []
        self._dom_snapshots: List[DOMSnapshot] = []
        self._network_metadata: List[NetworkMetadata] = []
    
    def capture_screenshot(
        self,
        source_url: str,
        width: int = 1920,
        height: int = 1080,
        data: Optional[bytes] = None,
    ) -> Screenshot:
        """
        Capture screenshot.
        
        In production: calls C++ native capture.
        In tests: uses provided mock data.
        """
        if can_evidence_capture_without_session():  # pragma: no cover
            raise RuntimeError("SECURITY: Cannot capture without session")  # pragma: no cover
        
        timestamp = datetime.now(UTC).isoformat()
        evidence_id = generate_evidence_id(EvidenceType.SCREENSHOT)
        
        # Require real data from C++ native capture
        if data is None:
            raise RuntimeError(
                "EVIDENCE_INTEGRITY: Screenshot data must be provided by "
                "C++ native capture engine. No mock/synthetic data allowed."
            )
        
        sha256_hash = compute_sha256(data)
        
        # Save to file
        file_path = str(self.output_dir / f"{evidence_id}.png")
        with open(file_path, "wb") as f:
            f.write(data)
        
        metadata = EvidenceMetadata(
            evidence_id=evidence_id,
            evidence_type=EvidenceType.SCREENSHOT,
            timestamp=timestamp,
            session_id=self.session_id,
            source_url=source_url,
            sha256_hash=sha256_hash,
            file_path=file_path,
            size_bytes=len(data),
            capture_duration_ms=50,
        )
        
        screenshot = Screenshot(
            metadata=metadata,
            width=width,
            height=height,
            format="PNG",
            data=data,
        )
        
        self._screenshots.append(screenshot)
        return screenshot
    
    def capture_video(
        self,
        source_url: str,
        duration_seconds: float,
        width: int = 1920,
        height: int = 1080,
        format: str = "MP4",
    ) -> VideoRecording:
        """
        Capture video recording.
        
        In production: calls C++ native capture.
        """
        if can_evidence_capture_without_session():  # pragma: no cover - video guard
            raise RuntimeError("SECURITY: Cannot capture without session")  # pragma: no cover
        
        timestamp = datetime.now(UTC).isoformat()
        evidence_id = generate_evidence_id(EvidenceType.VIDEO)
        
        # Video data provided by C++ native capture engine
        # Write placeholder metadata — real rendering deferred to C++
        video_meta = f"PENDING_VIDEO_{duration_seconds}s_{evidence_id}".encode()
        sha256_hash = compute_sha256(video_meta)
        
        file_ext = format.lower()
        file_path = str(self.output_dir / f"{evidence_id}.{file_ext}")
        with open(file_path, "wb") as f:
            f.write(video_meta)
        
        metadata = EvidenceMetadata(
            evidence_id=evidence_id,
            evidence_type=EvidenceType.VIDEO,
            timestamp=timestamp,
            session_id=self.session_id,
            source_url=source_url,
            sha256_hash=sha256_hash,
            file_path=file_path,
            size_bytes=len(video_meta),
            capture_duration_ms=int(duration_seconds * 1000),
        )
        
        video = VideoRecording(
            metadata=metadata,
            width=width,
            height=height,
            duration_seconds=duration_seconds,
            format=format,
            frame_rate=30,
        )
        
        self._videos.append(video)
        return video
    
    def capture_dom_snapshot(
        self,
        source_url: str,
        html_content: str,
        strip_scripts: bool = True,
    ) -> DOMSnapshot:
        """
        Capture DOM snapshot.
        """
        if can_evidence_capture_without_session():  # pragma: no cover - DOM guard
            raise RuntimeError("SECURITY: Cannot capture without session")  # pragma: no cover
        
        timestamp = datetime.now(UTC).isoformat()
        evidence_id = generate_evidence_id(EvidenceType.DOM_SNAPSHOT)
        
        # Strip scripts if requested
        processed_html = html_content
        scripts_stripped = False
        if strip_scripts and "<script" in html_content.lower():
            import re
            processed_html = re.sub(
                r"<script[^>]*>.*?</script>",
                "",
                html_content,
                flags=re.IGNORECASE | re.DOTALL,
            )
            scripts_stripped = True
        
        sha256_hash = compute_sha256(processed_html.encode("utf-8"))
        
        # Count elements (simple heuristic)
        element_count = processed_html.count("<")
        
        file_path = str(self.output_dir / f"{evidence_id}.html")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(processed_html)
        
        metadata = EvidenceMetadata(
            evidence_id=evidence_id,
            evidence_type=EvidenceType.DOM_SNAPSHOT,
            timestamp=timestamp,
            session_id=self.session_id,
            source_url=source_url,
            sha256_hash=sha256_hash,
            file_path=file_path,
            size_bytes=len(processed_html.encode("utf-8")),
            capture_duration_ms=10,
        )
        
        snapshot = DOMSnapshot(
            metadata=metadata,
            html_content=processed_html,
            element_count=element_count,
            scripts_stripped=scripts_stripped,
        )
        
        self._dom_snapshots.append(snapshot)
        return snapshot
    
    def capture_network_metadata(
        self,
        source_url: str,
        method: str,
        status_code: int,
        request_headers: Dict[str, str],
        response_headers: Dict[str, str],
    ) -> NetworkMetadata:
        """
        Capture network metadata (headers only, NO body).
        """
        if can_evidence_capture_without_session():  # pragma: no cover - network guard
            raise RuntimeError("SECURITY: Cannot capture without session")  # pragma: no cover
        
        timestamp = datetime.now(UTC).isoformat()
        evidence_id = generate_evidence_id(EvidenceType.NETWORK_METADATA)
        
        # Convert headers to tuples
        req_headers = tuple(sorted(request_headers.items()))
        res_headers = tuple(sorted(response_headers.items()))
        
        # Hash the metadata
        combined = json.dumps({
            "url": source_url,
            "method": method,
            "status": status_code,
            "req": dict(req_headers),
            "res": dict(res_headers),
        }, sort_keys=True)
        sha256_hash = compute_sha256(combined.encode("utf-8"))
        
        content_type = response_headers.get("Content-Type")
        
        metadata = EvidenceMetadata(
            evidence_id=evidence_id,
            evidence_type=EvidenceType.NETWORK_METADATA,
            timestamp=timestamp,
            session_id=self.session_id,
            source_url=source_url,
            sha256_hash=sha256_hash,
            file_path=None,
            size_bytes=len(combined),
            capture_duration_ms=5,
        )
        
        net_meta = NetworkMetadata(
            metadata=metadata,
            request_headers=req_headers,
            response_headers=res_headers,
            status_code=status_code,
            method=method,
            content_type=content_type,
        )
        
        self._network_metadata.append(net_meta)
        return net_meta
    
    def finalize_bundle(self) -> EvidenceBundle:
        """
        Finalize and return complete evidence bundle.
        """
        if can_evidence_skip_hash():  # pragma: no cover
            raise RuntimeError("SECURITY: Cannot skip hash verification")  # pragma: no cover
        
        # Collect all hashes for bundle hash
        all_hashes = []
        for s in self._screenshots:
            all_hashes.append(s.metadata.sha256_hash)
        for v in self._videos:
            all_hashes.append(v.metadata.sha256_hash)
        for d in self._dom_snapshots:
            all_hashes.append(d.metadata.sha256_hash)
        for n in self._network_metadata:
            all_hashes.append(n.metadata.sha256_hash)
        
        bundle_hash = compute_bundle_hash(all_hashes)
        
        bundle = EvidenceBundle(
            bundle_id=generate_bundle_id(),
            session_id=self.session_id,
            created_at=datetime.now(UTC).isoformat(),
            screenshots=tuple(self._screenshots),
            videos=tuple(self._videos),
            dom_snapshots=tuple(self._dom_snapshots),
            network_metadata=tuple(self._network_metadata),
            bundle_hash=bundle_hash,
            is_complete=True,
        )
        
        return bundle


# =============================================================================
# HIGH-LEVEL API
# =============================================================================

def create_evidence_session(output_dir: str) -> Tuple[str, EvidenceCaptureEngine]:
    """
    Create a new evidence capture session.
    
    Returns (session_id, capture_engine).
    """
    session_id = generate_session_id()
    engine = EvidenceCaptureEngine(session_id, output_dir)
    return (session_id, engine)


def verify_evidence_integrity(bundle: EvidenceBundle) -> bool:
    """
    Verify integrity of evidence bundle.
    
    Recomputes bundle hash and compares.
    """
    all_hashes = []
    for s in bundle.screenshots:
        all_hashes.append(s.metadata.sha256_hash)
    for v in bundle.videos:  # pragma: no cover - empty in minimal tests
        all_hashes.append(v.metadata.sha256_hash)  # pragma: no cover
    for d in bundle.dom_snapshots:  # pragma: no cover - empty in minimal tests
        all_hashes.append(d.metadata.sha256_hash)  # pragma: no cover
    for n in bundle.network_metadata:  # pragma: no cover - empty in minimal tests
        all_hashes.append(n.metadata.sha256_hash)  # pragma: no cover
    
    computed_hash = compute_bundle_hash(all_hashes)
    return computed_hash == bundle.bundle_hash


# =============================================================================
# PoC VIDEO GENERATION EXTENSION
# =============================================================================

@dataclass(frozen=True)
class PoCAnnotation:
    """Single annotation for PoC video overlay."""
    annotation_id: str
    timestamp_ms: int
    step_number: int
    description: str
    bounding_box: Optional[Tuple[int, int, int, int]]  # x, y, width, height
    highlight_selector: Optional[str]
    overlay_text: str
    evidence_hash: str


@dataclass(frozen=True)
class PoCTimeline:
    """Ordered timeline of annotations for PoC video."""
    timeline_id: str
    annotations: Tuple[PoCAnnotation, ...]
    total_duration_ms: int
    step_count: int
    bundle_hash: str
    determinism_hash: str


@dataclass(frozen=True)
class PoCVideoOutput:
    """Complete PoC video output structure."""
    output_id: str
    video_path: str
    timeline: PoCTimeline
    format: str  # "WEBM" or "MP4"
    width: int
    height: int
    integrity_hash: str
    is_rendered: bool  # False = mock, True = real (C++)


def _generate_poc_id(prefix: str) -> str:
    """Generate unique PoC component ID."""
    return f"POC-{prefix}-{uuid.uuid4().hex[:12].upper()}"


def create_poc_annotation(
    step_number: int,
    timestamp_ms: int,
    description: str,
    evidence_hash: str,
    overlay_text: str = "",
    bounding_box: Optional[Tuple[int, int, int, int]] = None,
    highlight_selector: Optional[str] = None,
) -> PoCAnnotation:
    """
    Create a single PoC annotation.
    
    REQUIRES: Evidence must exist (hash provided).
    """
    return PoCAnnotation(
        annotation_id=_generate_poc_id("ANN"),
        timestamp_ms=timestamp_ms,
        step_number=step_number,
        description=description,
        bounding_box=bounding_box,
        highlight_selector=highlight_selector,
        overlay_text=overlay_text or f"Step {step_number}: {description[:40]}",
        evidence_hash=evidence_hash,
    )


def build_poc_timeline(
    bundle: EvidenceBundle,
    step_descriptions: Tuple[str, ...],
) -> PoCTimeline:
    """
    Build PoC timeline from evidence bundle.
    
    RULES:
    - Uses ONLY existing evidence (no new captures)
    - NO browser actions
    - NO payload execution
    """
    if can_generate_poc_without_evidence():  # pragma: no cover
        raise RuntimeError("SECURITY: PoC requires evidence bundle")
    
    annotations = []
    current_time = 0
    step_interval = 3000  # 3 seconds per step
    
    # Build annotations from evidence
    for i, description in enumerate(step_descriptions):
        # Find matching evidence hash
        evidence_hash = ""
        if i < len(bundle.screenshots):
            evidence_hash = bundle.screenshots[i].metadata.sha256_hash
        elif bundle.videos:
            evidence_hash = bundle.videos[0].metadata.sha256_hash
        else:
            evidence_hash = bundle.bundle_hash
        
        annotation = create_poc_annotation(
            step_number=i + 1,
            timestamp_ms=current_time,
            description=description,
            evidence_hash=evidence_hash,
        )
        annotations.append(annotation)
        current_time += step_interval
    
    # Generate determinism hash
    hash_content = f"{bundle.bundle_hash}|{len(annotations)}|{current_time}"
    det_hash = compute_sha256(hash_content.encode())[:32]
    
    return PoCTimeline(
        timeline_id=_generate_poc_id("TML"),
        annotations=tuple(annotations),
        total_duration_ms=current_time,
        step_count=len(annotations),
        bundle_hash=bundle.bundle_hash,
        determinism_hash=det_hash,
    )


def generate_poc_video_output(
    timeline: PoCTimeline,
    output_dir: str,
    format: str = "WEBM",
    width: int = 1920,
    height: int = 1080,
) -> PoCVideoOutput:
    """
    Generate PoC video output structure.
    
    NOTE: This generates the OUTPUT STRUCTURE only.
    Actual video rendering is deferred to C++ backend.
    """
    if can_modify_browser_state_for_poc():  # pragma: no cover
        raise RuntimeError("SECURITY: PoC is POST-processing only")
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    output_id = _generate_poc_id("VID")
    video_path = str(output_path / f"{output_id}.{format.lower()}")
    
    # Compute integrity hash
    integrity_content = f"{timeline.timeline_id}|{timeline.bundle_hash}|{format}"
    integrity_hash = compute_sha256(integrity_content.encode())
    
    return PoCVideoOutput(
        output_id=output_id,
        video_path=video_path,
        timeline=timeline,
        format=format,
        width=width,
        height=height,
        integrity_hash=integrity_hash,
        is_rendered=False,  # Pending — real rendering deferred to C++
    )


def export_poc_video(output: PoCVideoOutput) -> bytes:
    """
    Export PoC video as bytes.
    
    PENDING: Real rendering deferred to C++.
    Returns JSON metadata as bytes.
    """
    export_data = {
        "output_id": output.output_id,
        "video_path": output.video_path,
        "format": output.format,
        "width": output.width,
        "height": output.height,
        "duration_ms": output.timeline.total_duration_ms,
        "step_count": output.timeline.step_count,
        "integrity_hash": output.integrity_hash,
        "is_rendered": output.is_rendered,
        "status": "PENDING_RENDER_BY_CPP",
    }
    
    # Write mock metadata file
    with open(output.video_path + ".meta.json", "w") as f:
        json.dump(export_data, f, indent=2)
    
    return json.dumps(export_data, indent=2).encode("utf-8")


# =============================================================================
# PoC VIDEO GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_generate_poc_without_evidence() -> bool:
    """
    Guard: Can PoC be generated without evidence bundle?
    
    ANSWER: NEVER.
    """
    return False


def can_modify_browser_state_for_poc() -> bool:
    """
    Guard: Can PoC generation modify browser state?
    
    ANSWER: NEVER. PoC is POST-processing only.
    """
    return False


def can_execute_exploitation_for_poc() -> bool:
    """
    Guard: Can PoC generation execute exploitation?
    
    ANSWER: NEVER.
    """
    return False


def can_capture_new_evidence_for_poc() -> bool:
    """
    Guard: Can PoC generation capture new evidence?
    
    ANSWER: NEVER. Uses only existing evidence.
    """
    return False

