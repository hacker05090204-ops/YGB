# Test G26: Forensic Evidence Capture
"""
Tests for forensic evidence capture governor.

100% coverage required.
"""

import pytest
import tempfile
import os
from pathlib import Path

from impl_v1.phase49.governors.g26_forensic_evidence import (
    EvidenceType,
    CaptureStatus,
    EvidenceMetadata,
    Screenshot,
    VideoRecording,
    DOMSnapshot,
    NetworkMetadata,
    EvidenceBundle,
    can_evidence_modify_browser,
    can_evidence_automate,
    can_evidence_capture_without_session,
    can_evidence_skip_hash,
    compute_sha256,
    compute_sha256_from_file,
    compute_bundle_hash,
    generate_evidence_id,
    generate_session_id,
    generate_bundle_id,
    EvidenceCaptureEngine,
    create_evidence_session,
    verify_evidence_integrity,
)


class TestGuards:
    """Test all security guards."""
    
    def test_can_evidence_modify_browser_always_false(self):
        """Guard: Evidence cannot modify browser."""
        assert can_evidence_modify_browser() is False
    
    def test_can_evidence_automate_always_false(self):
        """Guard: Evidence cannot automate."""
        assert can_evidence_automate() is False
    
    def test_can_evidence_capture_without_session_always_false(self):
        """Guard: Evidence requires session."""
        assert can_evidence_capture_without_session() is False
    
    def test_can_evidence_skip_hash_always_false(self):
        """Guard: Evidence requires hash."""
        assert can_evidence_skip_hash() is False


class TestEvidenceTypes:
    """Test evidence type enums."""
    
    def test_evidence_type_values(self):
        """Evidence types defined."""
        assert EvidenceType.SCREENSHOT.value == "SCREENSHOT"
        assert EvidenceType.VIDEO.value == "VIDEO"
        assert EvidenceType.DOM_SNAPSHOT.value == "DOM_SNAPSHOT"
        assert EvidenceType.NETWORK_METADATA.value == "NETWORK_METADATA"
    
    def test_capture_status_values(self):
        """Capture statuses defined."""
        assert CaptureStatus.PENDING.value == "PENDING"
        assert CaptureStatus.COMPLETE.value == "COMPLETE"
        assert CaptureStatus.FAILED.value == "FAILED"


class TestEvidenceMetadata:
    """Test EvidenceMetadata dataclass."""
    
    def test_metadata_creation(self):
        """Create evidence metadata."""
        metadata = EvidenceMetadata(
            evidence_id="EV-SCR-ABC123",
            evidence_type=EvidenceType.SCREENSHOT,
            timestamp="2026-01-28T00:00:00Z",
            session_id="SES-123",
            source_url="https://example.com",
            sha256_hash="abc123",
            file_path="/tmp/test.png",
            size_bytes=1024,
            capture_duration_ms=50,
        )
        assert metadata.evidence_id == "EV-SCR-ABC123"
        assert metadata.evidence_type == EvidenceType.SCREENSHOT
    
    def test_metadata_immutable(self):
        """Metadata is frozen."""
        metadata = EvidenceMetadata(
            evidence_id="test",
            evidence_type=EvidenceType.SCREENSHOT,
            timestamp="2026-01-28T00:00:00Z",
            session_id="SES-123",
            source_url="https://example.com",
            sha256_hash="abc",
            file_path=None,
            size_bytes=0,
            capture_duration_ms=0,
        )
        with pytest.raises(Exception):
            metadata.evidence_id = "changed"


class TestHashUtilities:
    """Test hash utility functions."""
    
    def test_compute_sha256(self):
        """Compute SHA-256 of bytes."""
        data = b"test data"
        result = compute_sha256(data)
        assert len(result) == 64
        assert result == compute_sha256(data)  # Deterministic
    
    def test_compute_sha256_from_file(self):
        """Compute SHA-256 from file."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test data")
            f.flush()
            
            result = compute_sha256_from_file(f.name)
            assert result is not None
            assert len(result) == 64
            
            os.unlink(f.name)
    
    def test_compute_sha256_from_file_not_exists(self):
        """Hash of non-existent file."""
        result = compute_sha256_from_file("/nonexistent/path")
        assert result is None
    
    def test_compute_bundle_hash(self):
        """Compute bundle hash."""
        hashes = ["abc", "def", "ghi"]
        result = compute_bundle_hash(hashes)
        assert len(result) == 64
        
        # Same input = same output
        assert result == compute_bundle_hash(hashes)
        
        # Order doesn't matter (sorted)
        assert result == compute_bundle_hash(["ghi", "abc", "def"])


class TestIdGeneration:
    """Test ID generation functions."""
    
    def test_generate_evidence_id_screenshot(self):
        """Generate screenshot evidence ID."""
        eid = generate_evidence_id(EvidenceType.SCREENSHOT)
        assert eid.startswith("EV-SCR-")
        assert len(eid) == 19  # EV-SCR- + 12
    
    def test_generate_evidence_id_video(self):
        """Generate video evidence ID."""
        eid = generate_evidence_id(EvidenceType.VIDEO)
        assert eid.startswith("EV-VID-")
    
    def test_generate_evidence_id_unique(self):
        """Evidence IDs are unique."""
        ids = [generate_evidence_id(EvidenceType.SCREENSHOT) for _ in range(10)]
        assert len(set(ids)) == 10
    
    def test_generate_session_id(self):
        """Generate session ID."""
        sid = generate_session_id()
        assert sid.startswith("SES-")
        assert len(sid) == 20  # SES- + 16
    
    def test_generate_bundle_id(self):
        """Generate bundle ID."""
        bid = generate_bundle_id()
        assert bid.startswith("BND-")


class TestEvidenceCaptureEngine:
    """Test evidence capture engine."""
    
    def test_engine_creation(self):
        """Create capture engine."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id, engine = create_evidence_session(tmpdir)
            assert session_id.startswith("SES-")
            assert engine.session_id == session_id
    
    def test_capture_screenshot(self):
        """Capture screenshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id, engine = create_evidence_session(tmpdir)
            
            screenshot = engine.capture_screenshot(
                source_url="https://example.com",
                width=1920,
                height=1080,
            )
            
            assert screenshot.width == 1920
            assert screenshot.height == 1080
            assert screenshot.format == "PNG"
            assert screenshot.metadata.evidence_type == EvidenceType.SCREENSHOT
            assert screenshot.metadata.session_id == session_id
            assert Path(screenshot.metadata.file_path).exists()
    
    def test_capture_screenshot_with_data(self):
        """Capture screenshot with provided data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id, engine = create_evidence_session(tmpdir)
            
            custom_data = b"CUSTOM_PNG_BYTES"
            screenshot = engine.capture_screenshot(
                source_url="https://example.com",
                data=custom_data,
            )
            
            assert screenshot.data == custom_data
            assert screenshot.metadata.sha256_hash == compute_sha256(custom_data)
    
    def test_capture_video(self):
        """Capture video recording."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id, engine = create_evidence_session(tmpdir)
            
            video = engine.capture_video(
                source_url="https://example.com",
                duration_seconds=10.5,
                format="MP4",
            )
            
            assert video.duration_seconds == 10.5
            assert video.format == "MP4"
            assert video.frame_rate == 30
            assert video.metadata.evidence_type == EvidenceType.VIDEO
            assert Path(video.metadata.file_path).exists()
    
    def test_capture_video_webm(self):
        """Capture video as WebM."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id, engine = create_evidence_session(tmpdir)
            
            video = engine.capture_video(
                source_url="https://example.com",
                duration_seconds=5.0,
                format="WEBM",
            )
            
            assert video.format == "WEBM"
            assert video.metadata.file_path.endswith(".webm")
    
    def test_capture_dom_snapshot(self):
        """Capture DOM snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id, engine = create_evidence_session(tmpdir)
            
            html = "<html><body><h1>Test</h1></body></html>"
            snapshot = engine.capture_dom_snapshot(
                source_url="https://example.com",
                html_content=html,
            )
            
            assert snapshot.html_content == html
            assert snapshot.element_count > 0
            assert snapshot.metadata.evidence_type == EvidenceType.DOM_SNAPSHOT
    
    def test_capture_dom_snapshot_strips_scripts(self):
        """DOM snapshot strips scripts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id, engine = create_evidence_session(tmpdir)
            
            html = "<html><body><script>alert('xss')</script><h1>Test</h1></body></html>"
            snapshot = engine.capture_dom_snapshot(
                source_url="https://example.com",
                html_content=html,
                strip_scripts=True,
            )
            
            assert "<script" not in snapshot.html_content
            assert snapshot.scripts_stripped is True
    
    def test_capture_dom_snapshot_no_strip(self):
        """DOM snapshot keeps scripts if requested."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id, engine = create_evidence_session(tmpdir)
            
            html = "<html><body><h1>Test</h1></body></html>"
            snapshot = engine.capture_dom_snapshot(
                source_url="https://example.com",
                html_content=html,
                strip_scripts=False,
            )
            
            assert snapshot.scripts_stripped is False
    
    def test_capture_network_metadata(self):
        """Capture network metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id, engine = create_evidence_session(tmpdir)
            
            net = engine.capture_network_metadata(
                source_url="https://example.com/api",
                method="GET",
                status_code=200,
                request_headers={"User-Agent": "Test"},
                response_headers={"Content-Type": "application/json"},
            )
            
            assert net.method == "GET"
            assert net.status_code == 200
            assert net.content_type == "application/json"
            assert ("User-Agent", "Test") in net.request_headers
    
    def test_finalize_bundle(self):
        """Finalize evidence bundle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id, engine = create_evidence_session(tmpdir)
            
            # Capture various evidence
            engine.capture_screenshot("https://example.com")
            engine.capture_video("https://example.com", 5.0)
            engine.capture_dom_snapshot("https://example.com", "<html></html>")
            engine.capture_network_metadata(
                "https://example.com",
                "GET",
                200,
                {},
                {"Content-Type": "text/html"},
            )
            
            bundle = engine.finalize_bundle()
            
            assert bundle.session_id == session_id
            assert bundle.is_complete is True
            assert len(bundle.screenshots) == 1
            assert len(bundle.videos) == 1
            assert len(bundle.dom_snapshots) == 1
            assert len(bundle.network_metadata) == 1
            assert bundle.bundle_hash is not None


class TestEvidenceIntegrity:
    """Test evidence integrity verification."""
    
    def test_verify_integrity_valid(self):
        """Verify valid bundle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id, engine = create_evidence_session(tmpdir)
            
            engine.capture_screenshot("https://example.com")
            bundle = engine.finalize_bundle()
            
            assert verify_evidence_integrity(bundle) is True
    
    def test_verify_integrity_empty_bundle(self):
        """Verify empty bundle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_id, engine = create_evidence_session(tmpdir)
            bundle = engine.finalize_bundle()
            
            assert verify_evidence_integrity(bundle) is True


class TestDataclasses:
    """Test remaining dataclass structures."""
    
    def test_screenshot_frozen(self):
        """Screenshot is immutable."""
        metadata = EvidenceMetadata(
            evidence_id="test",
            evidence_type=EvidenceType.SCREENSHOT,
            timestamp="2026-01-28T00:00:00Z",
            session_id="SES-123",
            source_url="https://example.com",
            sha256_hash="abc",
            file_path=None,
            size_bytes=0,
            capture_duration_ms=0,
        )
        screenshot = Screenshot(
            metadata=metadata,
            width=100,
            height=100,
            format="PNG",
            data=None,
        )
        with pytest.raises(Exception):
            screenshot.width = 200
    
    def test_video_recording_frozen(self):
        """VideoRecording is immutable."""
        metadata = EvidenceMetadata(
            evidence_id="test",
            evidence_type=EvidenceType.VIDEO,
            timestamp="2026-01-28T00:00:00Z",
            session_id="SES-123",
            source_url="https://example.com",
            sha256_hash="abc",
            file_path=None,
            size_bytes=0,
            capture_duration_ms=0,
        )
        video = VideoRecording(
            metadata=metadata,
            width=100,
            height=100,
            duration_seconds=10.0,
            format="MP4",
            frame_rate=30,
        )
        with pytest.raises(Exception):
            video.duration_seconds = 20.0
    
    def test_bundle_frozen(self):
        """EvidenceBundle is immutable."""
        bundle = EvidenceBundle(
            bundle_id="test",
            session_id="SES-123",
            created_at="2026-01-28T00:00:00Z",
            screenshots=(),
            videos=(),
            dom_snapshots=(),
            network_metadata=(),
            bundle_hash="abc",
            is_complete=True,
        )
        with pytest.raises(Exception):
            bundle.is_complete = False
