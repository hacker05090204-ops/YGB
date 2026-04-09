"""Real session video recording support backed by screen capture."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import importlib
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Type
import uuid


@dataclass(frozen=True)
class VideoRecordingResult:
    """Status and metadata for a video recording attempt."""

    recording_id: Optional[str]
    status: str
    started_at: Optional[str]
    stopped_at: Optional[str]
    output_path: Optional[str]
    sha256_hash: Optional[str]
    size_bytes: int
    duration_seconds: float
    frame_count: int
    error_message: Optional[str] = None


@dataclass(frozen=True)
class _DependencyBundle:
    cv2: Any
    mss: Any
    numpy: Any
    screenshot_error: Type[BaseException]


@dataclass
class _ActiveRecording:
    recording_id: str
    session_id: str
    output_path: Path
    fps: int
    width: int
    height: int
    monitor: Dict[str, int]
    started_at: str
    start_monotonic: float
    stop_event: threading.Event
    writer: Any
    dependencies: _DependencyBundle
    thread: threading.Thread
    frame_count: int = 0
    error_message: Optional[str] = None


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _load_capture_dependencies() -> Tuple[Optional[_DependencyBundle], Optional[str]]:
    missing: List[str] = []

    try:
        cv2_module = importlib.import_module("cv2")
    except ModuleNotFoundError:
        missing.append("cv2")
        cv2_module = None
    except ImportError as exc:
        return (None, f"Unable to import cv2: {exc}")

    try:
        mss_module = importlib.import_module("mss")
    except ModuleNotFoundError:
        missing.append("mss")
        mss_module = None
    except ImportError as exc:
        return (None, f"Unable to import mss: {exc}")

    try:
        numpy_module = importlib.import_module("numpy")
    except ModuleNotFoundError:
        missing.append("numpy")
        numpy_module = None
    except ImportError as exc:
        return (None, f"Unable to import numpy: {exc}")

    if missing:
        return (None, f"Video recording is unavailable because required dependencies are missing: {', '.join(missing)}")

    screenshot_error: Type[BaseException] = RuntimeError
    try:
        mss_exception_module = importlib.import_module("mss.exception")
        imported_error = getattr(mss_exception_module, "ScreenShotError")
        if isinstance(imported_error, type) and issubclass(imported_error, BaseException):
            screenshot_error = imported_error
    except ModuleNotFoundError:
        screenshot_error = RuntimeError
    except ImportError:
        screenshot_error = RuntimeError
    except AttributeError:
        screenshot_error = RuntimeError

    return (
        _DependencyBundle(
            cv2=cv2_module,
            mss=mss_module,
            numpy=numpy_module,
            screenshot_error=screenshot_error,
        ),
        None,
    )


def _sha256_for_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_file_size(file_path: Path) -> int:
    try:
        return file_path.stat().st_size
    except FileNotFoundError:
        return 0
    except OSError:
        return 0


def _sanitize_session_id(session_id: str) -> str:
    sanitized = "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in session_id)
    return sanitized or "session"


class VideoRecorder:
    """Real screen recorder using OpenCV and MSS when available."""

    def __init__(self, default_output_dir: Optional[Path | str] = None):
        if default_output_dir is None:
            output_root = Path(tempfile.gettempdir()) / "ygb_video_recordings"
        else:
            output_root = Path(default_output_dir)
        self._default_output_dir = output_root
        self._lock = threading.RLock()
        self._active_recordings: Dict[str, _ActiveRecording] = {}
        self._finished_recordings: List[VideoRecordingResult] = []

    def start_recording(
        self,
        session_id: Optional[str] = None,
        output_dir: Optional[Path | str] = None,
        fps: int = 10,
    ) -> VideoRecordingResult:
        """Start a real screen recording if capture dependencies are available."""

        started_at = _utc_now_iso()
        dependencies, dependency_error = _load_capture_dependencies()
        if dependencies is None:
            result = VideoRecordingResult(
                recording_id=None,
                status="UNAVAILABLE",
                started_at=started_at,
                stopped_at=started_at,
                output_path=None,
                sha256_hash=None,
                size_bytes=0,
                duration_seconds=0.0,
                frame_count=0,
                error_message=dependency_error,
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result

        safe_session_id = _sanitize_session_id(session_id or f"session-{uuid.uuid4().hex[:12]}")
        recording_id = f"VIDREC-{uuid.uuid4().hex[:12].upper()}"
        frame_rate = max(1, int(fps))
        output_root = Path(output_dir) if output_dir is not None else self._default_output_dir

        try:
            output_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=started_at,
                stopped_at=_utc_now_iso(),
                output_path=None,
                sha256_hash=None,
                size_bytes=0,
                duration_seconds=0.0,
                frame_count=0,
                error_message=f"Unable to create output directory: {exc}",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result

        try:
            with dependencies.mss.mss() as capture_session:
                monitor = self._select_monitor(capture_session)
                first_frame = self._grab_frame(dependencies, capture_session, monitor)
        except dependencies.screenshot_error as exc:
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=started_at,
                stopped_at=_utc_now_iso(),
                output_path=None,
                sha256_hash=None,
                size_bytes=0,
                duration_seconds=0.0,
                frame_count=0,
                error_message=f"Unable to capture the initial frame: {exc}",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result
        except OSError as exc:
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=started_at,
                stopped_at=_utc_now_iso(),
                output_path=None,
                sha256_hash=None,
                size_bytes=0,
                duration_seconds=0.0,
                frame_count=0,
                error_message=f"Unable to access display capture resources: {exc}",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result
        except ValueError as exc:
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=started_at,
                stopped_at=_utc_now_iso(),
                output_path=None,
                sha256_hash=None,
                size_bytes=0,
                duration_seconds=0.0,
                frame_count=0,
                error_message=f"Unable to process the initial frame: {exc}",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result
        except RuntimeError as exc:
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=started_at,
                stopped_at=_utc_now_iso(),
                output_path=None,
                sha256_hash=None,
                size_bytes=0,
                duration_seconds=0.0,
                frame_count=0,
                error_message=f"Unable to start the recorder: {exc}",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result
        except AttributeError as exc:
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=started_at,
                stopped_at=_utc_now_iso(),
                output_path=None,
                sha256_hash=None,
                size_bytes=0,
                duration_seconds=0.0,
                frame_count=0,
                error_message=f"Capture dependency interface is incomplete: {exc}",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result
        except dependencies.cv2.error as exc:
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=started_at,
                stopped_at=_utc_now_iso(),
                output_path=None,
                sha256_hash=None,
                size_bytes=0,
                duration_seconds=0.0,
                frame_count=0,
                error_message=f"OpenCV failed during initial frame handling: {exc}",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result

        width = int(first_frame.shape[1])
        height = int(first_frame.shape[0])
        output_path = output_root / f"{safe_session_id}-{recording_id}.mp4"

        try:
            writer = dependencies.cv2.VideoWriter(
                str(output_path),
                dependencies.cv2.VideoWriter_fourcc(*"mp4v"),
                float(frame_rate),
                (width, height),
            )
        except dependencies.cv2.error as exc:
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=started_at,
                stopped_at=_utc_now_iso(),
                output_path=str(output_path),
                sha256_hash=None,
                size_bytes=0,
                duration_seconds=0.0,
                frame_count=0,
                error_message=f"Unable to initialize the video writer: {exc}",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result

        if not writer.isOpened():
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=started_at,
                stopped_at=_utc_now_iso(),
                output_path=str(output_path),
                sha256_hash=None,
                size_bytes=0,
                duration_seconds=0.0,
                frame_count=0,
                error_message="Unable to initialize the video writer for the requested output path.",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result

        try:
            writer.write(first_frame)
        except dependencies.cv2.error as exc:
            writer.release()
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=started_at,
                stopped_at=_utc_now_iso(),
                output_path=str(output_path),
                sha256_hash=None,
                size_bytes=0,
                duration_seconds=0.0,
                frame_count=0,
                error_message=f"Unable to persist the initial frame: {exc}",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result

        start_monotonic = time.monotonic()
        stop_event = threading.Event()
        active_recording = _ActiveRecording(
            recording_id=recording_id,
            session_id=safe_session_id,
            output_path=output_path,
            fps=frame_rate,
            width=width,
            height=height,
            monitor=monitor,
            started_at=started_at,
            start_monotonic=start_monotonic,
            stop_event=stop_event,
            writer=writer,
            dependencies=dependencies,
            thread=threading.Thread(target=lambda: None),
            frame_count=1,
        )
        recording_thread = threading.Thread(
            target=self._record_loop,
            args=(active_recording,),
            name=f"video-recorder-{recording_id.lower()}",
            daemon=True,
        )
        active_recording.thread = recording_thread

        with self._lock:
            self._active_recordings[recording_id] = active_recording

        recording_thread.start()
        return VideoRecordingResult(
            recording_id=recording_id,
            status="RECORDING",
            started_at=started_at,
            stopped_at=None,
            output_path=str(output_path),
            sha256_hash=None,
            size_bytes=_safe_file_size(output_path),
            duration_seconds=0.0,
            frame_count=1,
            error_message=None,
        )

    def stop_recording(self, recording_id: str, join_timeout_seconds: float = 5.0) -> VideoRecordingResult:
        """Stop a recording and finalize its on-disk hash."""

        with self._lock:
            active_recording = self._active_recordings.pop(recording_id, None)

        if active_recording is None:
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=None,
                stopped_at=_utc_now_iso(),
                output_path=None,
                sha256_hash=None,
                size_bytes=0,
                duration_seconds=0.0,
                frame_count=0,
                error_message=f"Unknown recording_id: {recording_id}",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result

        active_recording.stop_event.set()
        active_recording.thread.join(timeout=max(0.1, float(join_timeout_seconds)))

        stopped_at = _utc_now_iso()
        duration_seconds = max(0.0, time.monotonic() - active_recording.start_monotonic)
        file_size = _safe_file_size(active_recording.output_path)

        if active_recording.thread.is_alive():
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=active_recording.started_at,
                stopped_at=stopped_at,
                output_path=str(active_recording.output_path),
                sha256_hash=None,
                size_bytes=file_size,
                duration_seconds=duration_seconds,
                frame_count=active_recording.frame_count,
                error_message="Recording thread did not terminate within the requested timeout.",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result

        if active_recording.error_message is not None:
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=active_recording.started_at,
                stopped_at=stopped_at,
                output_path=str(active_recording.output_path),
                sha256_hash=None,
                size_bytes=file_size,
                duration_seconds=duration_seconds,
                frame_count=active_recording.frame_count,
                error_message=active_recording.error_message,
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result

        if file_size <= 0:
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=active_recording.started_at,
                stopped_at=stopped_at,
                output_path=str(active_recording.output_path),
                sha256_hash=None,
                size_bytes=file_size,
                duration_seconds=duration_seconds,
                frame_count=active_recording.frame_count,
                error_message="The recording completed without producing a readable output file.",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result

        try:
            sha256_hash = _sha256_for_file(active_recording.output_path)
        except FileNotFoundError as exc:
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=active_recording.started_at,
                stopped_at=stopped_at,
                output_path=str(active_recording.output_path),
                sha256_hash=None,
                size_bytes=0,
                duration_seconds=duration_seconds,
                frame_count=active_recording.frame_count,
                error_message=f"Recording output disappeared before hashing: {exc}",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result
        except OSError as exc:
            result = VideoRecordingResult(
                recording_id=recording_id,
                status="FAILED",
                started_at=active_recording.started_at,
                stopped_at=stopped_at,
                output_path=str(active_recording.output_path),
                sha256_hash=None,
                size_bytes=file_size,
                duration_seconds=duration_seconds,
                frame_count=active_recording.frame_count,
                error_message=f"Unable to hash the completed recording: {exc}",
            )
            with self._lock:
                self._finished_recordings.append(result)
            return result

        result = VideoRecordingResult(
            recording_id=recording_id,
            status="COMPLETED",
            started_at=active_recording.started_at,
            stopped_at=stopped_at,
            output_path=str(active_recording.output_path),
            sha256_hash=sha256_hash,
            size_bytes=file_size,
            duration_seconds=duration_seconds,
            frame_count=active_recording.frame_count,
            error_message=None,
        )
        with self._lock:
            self._finished_recordings.append(result)
        return result

    def list_recordings(self) -> List[VideoRecordingResult]:
        """Return finalized recordings plus current in-progress sessions."""

        with self._lock:
            finished = list(self._finished_recordings)
            active_items = list(self._active_recordings.values())

        active_snapshots = [self._active_snapshot(recording) for recording in active_items]
        return finished + active_snapshots

    def _active_snapshot(self, active_recording: _ActiveRecording) -> VideoRecordingResult:
        return VideoRecordingResult(
            recording_id=active_recording.recording_id,
            status="RECORDING",
            started_at=active_recording.started_at,
            stopped_at=None,
            output_path=str(active_recording.output_path),
            sha256_hash=None,
            size_bytes=_safe_file_size(active_recording.output_path),
            duration_seconds=max(0.0, time.monotonic() - active_recording.start_monotonic),
            frame_count=active_recording.frame_count,
            error_message=active_recording.error_message,
        )

    def _record_loop(self, active_recording: _ActiveRecording) -> None:
        frame_interval = 1.0 / float(active_recording.fps)
        dependencies = active_recording.dependencies

        try:
            with dependencies.mss.mss() as capture_session:
                while not active_recording.stop_event.wait(frame_interval):
                    frame = self._grab_frame(dependencies, capture_session, active_recording.monitor)
                    active_recording.writer.write(frame)
                    active_recording.frame_count += 1
        except dependencies.screenshot_error as exc:
            active_recording.error_message = f"Display capture failed during recording: {exc}"
        except OSError as exc:
            active_recording.error_message = f"Recording I/O failed: {exc}"
        except ValueError as exc:
            active_recording.error_message = f"Captured frame could not be encoded: {exc}"
        except RuntimeError as exc:
            active_recording.error_message = f"Recording runtime failed: {exc}"
        except AttributeError as exc:
            active_recording.error_message = f"Capture dependency interface changed unexpectedly: {exc}"
        except dependencies.cv2.error as exc:
            active_recording.error_message = f"OpenCV failed while writing a frame: {exc}"
        finally:
            try:
                active_recording.writer.release()
            except dependencies.cv2.error as exc:
                if active_recording.error_message is None:
                    active_recording.error_message = f"Unable to release the video writer: {exc}"
            except AttributeError as exc:
                if active_recording.error_message is None:
                    active_recording.error_message = f"Video writer release path is unavailable: {exc}"
            except OSError as exc:
                if active_recording.error_message is None:
                    active_recording.error_message = f"Recording finalization failed: {exc}"
            except ValueError as exc:
                if active_recording.error_message is None:
                    active_recording.error_message = f"Recording finalization returned invalid data: {exc}"

    def _select_monitor(self, capture_session: Any) -> Dict[str, int]:
        monitors = getattr(capture_session, "monitors")
        if len(monitors) > 1:
            selected_monitor = monitors[1]
        elif len(monitors) == 1:
            selected_monitor = monitors[0]
        else:
            raise RuntimeError("No monitors are available for capture.")

        return {
            "top": int(selected_monitor["top"]),
            "left": int(selected_monitor["left"]),
            "width": int(selected_monitor["width"]),
            "height": int(selected_monitor["height"]),
        }

    def _grab_frame(
        self,
        dependencies: _DependencyBundle,
        capture_session: Any,
        monitor: Dict[str, int],
    ) -> Any:
        screenshot = capture_session.grab(monitor)
        raw_frame = dependencies.numpy.asarray(screenshot)
        return dependencies.cv2.cvtColor(raw_frame, dependencies.cv2.COLOR_BGRA2BGR)


_VIDEO_RECORDER_SINGLETON: Optional[VideoRecorder] = None
_VIDEO_RECORDER_SINGLETON_LOCK = threading.Lock()


def get_video_recorder() -> VideoRecorder:
    """Return the shared recorder instance."""

    global _VIDEO_RECORDER_SINGLETON
    if _VIDEO_RECORDER_SINGLETON is None:
        with _VIDEO_RECORDER_SINGLETON_LOCK:
            if _VIDEO_RECORDER_SINGLETON is None:
                _VIDEO_RECORDER_SINGLETON = VideoRecorder()
    return _VIDEO_RECORDER_SINGLETON
