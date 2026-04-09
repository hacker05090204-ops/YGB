"""Tests for real video recorder availability and failure behavior."""

import inspect

from backend.evidence import video_recorder as video_recorder_module
from backend.evidence.video_recorder import VideoRecorder


def test_start_recording_returns_unavailable_when_opencv_missing(monkeypatch, tmp_path):
    def dependency_loader():
        return (None, "OpenCV is not installed in this environment.")

    monkeypatch.setattr(video_recorder_module, "_load_capture_dependencies", dependency_loader)

    recorder = VideoRecorder(default_output_dir=tmp_path)
    result = recorder.start_recording(session_id="group4-session")

    assert result.status == "UNAVAILABLE"
    assert result.recording_id is None
    assert result.output_path is None
    assert result.sha256_hash is None
    assert result.size_bytes == 0
    assert result.duration_seconds == 0.0
    assert result.frame_count == 0
    assert result.started_at is not None
    assert result.stopped_at == result.started_at
    assert "OpenCV" in (result.error_message or "")


def test_stop_recording_returns_failed_for_unknown_recording_id(tmp_path):
    recorder = VideoRecorder(default_output_dir=tmp_path)

    result = recorder.stop_recording("VIDREC-UNKNOWN")

    assert result.status == "FAILED"
    assert result.recording_id == "VIDREC-UNKNOWN"
    assert result.output_path is None
    assert result.sha256_hash is None
    assert result.size_bytes == 0
    assert result.frame_count == 0
    assert "Unknown recording_id" in (result.error_message or "")


def test_unavailable_result_fields_are_consistent(monkeypatch, tmp_path):
    def dependency_loader():
        return (None, "OpenCV support is unavailable.")

    monkeypatch.setattr(video_recorder_module, "_load_capture_dependencies", dependency_loader)

    recorder = VideoRecorder(default_output_dir=tmp_path)
    result = recorder.start_recording(session_id="group4-session")

    assert result.status == "UNAVAILABLE"
    assert result.recording_id is None
    assert result.output_path is None
    assert result.sha256_hash is None
    assert result.size_bytes == 0
    assert result.duration_seconds == 0.0
    assert result.frame_count == 0
    assert result.started_at is not None
    assert result.stopped_at is not None


def test_video_recorder_source_never_generates_placeholder_frames():
    module_source = inspect.getsource(video_recorder_module).lower()

    assert "mock frame" not in module_source
    assert "synthetic frame" not in module_source
    assert "fake frame" not in module_source
    assert "np.zeros(" not in module_source
    assert "numpy.zeros(" not in module_source
