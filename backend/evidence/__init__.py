"""Evidence utilities for backend capture workflows."""

from .video_recorder import VideoRecorder, VideoRecordingResult, get_video_recorder

__all__ = [
    "VideoRecorder",
    "VideoRecordingResult",
    "get_video_recorder",
]
