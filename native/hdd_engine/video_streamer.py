"""
Video Streamer
==============

Secure video storage and streaming for YGB.

Rules:
- No direct filesystem path exposure
- Access only via signed JWT token (5-minute expiry)
- Range header validated
- Max file size enforced (2 GB)
- No symlink following
- Streaming chunk size controlled
- Path normalization enforced

Video path:
    {HDD_ROOT}/videos/{user_id}/{session_id}/video.webm
"""

import os
import time
import json
import hmac
import hashlib
import base64
import logging
import mimetypes
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Generator
from datetime import datetime, timezone

logger = logging.getLogger("video_streamer")

# Config
MAX_VIDEO_SIZE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
MAX_DURATION_SECONDS = 7200  # 2 hours
STREAM_CHUNK_SIZE = 1024 * 1024  # 1 MB chunks
MAX_CONCURRENT_STREAMS = 10
JWT_EXPIRY_SECONDS = 300  # 5 minutes
JWT_SECRET = os.getenv("YGB_VIDEO_JWT_SECRET", "")
if not JWT_SECRET or len(JWT_SECRET) < 32:
    raise RuntimeError(
        "[FATAL] YGB_VIDEO_JWT_SECRET is not set or too short (min 32 chars). "
        "Set it as an environment variable before starting the server."
    )

# Active stream tracking
_active_streams: int = 0


def _validate_path_safe(user_id: str, session_id: str) -> bool:
    """
    Validate user_id and session_id to prevent path traversal.
    Only alphanumeric, hyphens, underscores allowed.
    """
    for val in (user_id, session_id):
        if not val or len(val) > 128:
            return False
        if not all(c.isalnum() or c in "-_" for c in val):
            return False
    return True


def _sign_token(payload: dict) -> str:
    """
    Create a signed JWT-like token for video access.
    Simple HMAC-SHA256 based token (no external dependency).
    """
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature_input = f"{header}.{body}"
    sig = hmac.new(
        JWT_SECRET.encode(),
        signature_input.encode(),
        hashlib.sha256,
    ).digest()
    signature = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    return f"{header}.{body}.{signature}"


def _verify_token(token: str) -> Optional[dict]:
    """
    Verify a signed token and return the payload.
    Returns None if invalid or expired.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header, body, signature = parts

        # Verify signature
        signature_input = f"{header}.{body}"
        expected_sig = hmac.new(
            JWT_SECRET.encode(),
            signature_input.encode(),
            hashlib.sha256,
        ).digest()
        expected = base64.urlsafe_b64encode(expected_sig).decode().rstrip("=")

        if not hmac.compare_digest(signature, expected):
            return None

        # Decode payload
        # Add padding
        padded = body + "=" * (4 - len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))

        # Check expiry
        if payload.get("exp", 0) < time.time():
            return None

        return payload

    except Exception:
        return None


class VideoStreamer:
    """
    Secure video storage and streaming.
    """

    def __init__(self, hdd_root: str):
        self._root = Path(hdd_root) / "videos"
        self._root.mkdir(parents=True, exist_ok=True)

    def store_video(
        self,
        user_id: str,
        session_id: str,
        video_data: bytes,
        filename: str = "video.webm",
    ) -> Dict[str, Any]:
        """
        Store a video file securely.

        Args:
            user_id: Owner user ID
            session_id: Session ID
            video_data: Raw video bytes
            filename: Video filename (sanitized)

        Returns:
            Storage result with file info
        """
        if not _validate_path_safe(user_id, session_id):
            return {"success": False, "reason": "Invalid user_id or session_id"}

        if len(video_data) > MAX_VIDEO_SIZE_BYTES:
            return {"success": False, "reason": f"Video too large (max {MAX_VIDEO_SIZE_BYTES} bytes)"}

        # Sanitize filename
        safe_name = "".join(c for c in filename if c.isalnum() or c in "-_.")
        if not safe_name:
            safe_name = "video.webm"

        # Build path (no symlinks)
        video_dir = self._root / user_id / session_id
        video_dir.mkdir(parents=True, exist_ok=True)
        video_path = video_dir / safe_name

        # Resolve and validate (prevent traversal)
        resolved = video_path.resolve()
        if not str(resolved).startswith(str(self._root.resolve())):
            return {"success": False, "reason": "Path traversal detected"}

        # Atomic write
        tmp_path = str(resolved) + ".tmp"
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, video_data)
            os.fsync(fd)
        finally:
            os.close(fd)

        os.replace(tmp_path, str(resolved))

        # File hash
        file_hash = hashlib.sha256(video_data).hexdigest()

        logger.info(
            f"Video stored: {user_id}/{session_id}/{safe_name} "
            f"({len(video_data)} bytes, hash={file_hash[:16]})"
        )

        return {
            "success": True,
            "user_id": user_id,
            "session_id": session_id,
            "filename": safe_name,
            "size_bytes": len(video_data),
            "hash": file_hash,
        }

    def generate_stream_token(
        self,
        user_id: str,
        session_id: str,
        filename: str = "video.webm",
    ) -> Optional[str]:
        """
        Generate a signed token for streaming a video.
        Token expires in 5 minutes.
        """
        if not _validate_path_safe(user_id, session_id):
            return None

        video_path = self._root / user_id / session_id / filename
        if not video_path.exists():
            return None

        # Check no symlink
        resolved = video_path.resolve()
        if not str(resolved).startswith(str(self._root.resolve())):
            return None

        payload = {
            "uid": user_id,
            "sid": session_id,
            "fname": filename,
            "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
            "iat": int(time.time()),
        }

        return _sign_token(payload)

    def stream_video(
        self,
        token: str,
        range_start: int = 0,
        range_end: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Stream video content using a signed token.

        Args:
            token: Signed access token
            range_start: Start byte for range request
            range_end: End byte (None = to end of file)

        Returns:
            Dict with file info for streaming, or None if unauthorized.
        """
        global _active_streams

        # Verify token
        payload = _verify_token(token)
        if not payload:
            return None

        # Check concurrent stream limit
        if _active_streams >= MAX_CONCURRENT_STREAMS:
            return {"error": "Too many concurrent streams"}

        user_id = payload["uid"]
        session_id = payload["sid"]
        filename = payload.get("fname", "video.webm")

        if not _validate_path_safe(user_id, session_id):
            return None

        video_path = self._root / user_id / session_id / filename
        resolved = video_path.resolve()

        # Path safety check
        if not str(resolved).startswith(str(self._root.resolve())):
            return None

        if not resolved.exists() or resolved.is_symlink():
            return None

        file_size = resolved.stat().st_size

        # Validate range
        if range_start < 0 or range_start >= file_size:
            range_start = 0
        if range_end is None or range_end >= file_size:
            range_end = file_size - 1

        content_length = range_end - range_start + 1

        # Determine MIME type
        mime_type = mimetypes.guess_type(filename)[0] or "video/webm"

        return {
            "file_path": str(resolved),
            "file_size": file_size,
            "range_start": range_start,
            "range_end": range_end,
            "content_length": content_length,
            "content_type": mime_type,
            "chunk_size": STREAM_CHUNK_SIZE,
        }

    def stream_chunks(
        self,
        file_path: str,
        range_start: int,
        range_end: int,
    ) -> Generator[bytes, None, None]:
        """
        Generator that yields video file chunks for streaming.
        """
        global _active_streams
        _active_streams += 1

        try:
            with open(file_path, "rb") as f:
                f.seek(range_start)
                remaining = range_end - range_start + 1

                while remaining > 0:
                    chunk_size = min(STREAM_CHUNK_SIZE, remaining)
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
        finally:
            _active_streams -= 1

    def list_videos(
        self,
        user_id: Optional[str] = None,
    ) -> list:
        """List all stored videos, optionally filtered by user."""
        videos = []

        if user_id:
            if not _validate_path_safe(user_id, "dummy"):
                return []
            user_dir = self._root / user_id
            if user_dir.exists():
                for session_dir in user_dir.iterdir():
                    if session_dir.is_dir():
                        for f in session_dir.iterdir():
                            if f.is_file() and not f.name.endswith(".tmp"):
                                videos.append({
                                    "user_id": user_id,
                                    "session_id": session_dir.name,
                                    "filename": f.name,
                                    "size_bytes": f.stat().st_size,
                                    "created_at": datetime.fromtimestamp(
                                        f.stat().st_ctime, tz=timezone.utc
                                    ).isoformat(),
                                })
        else:
            if self._root.exists():
                for user_dir in self._root.iterdir():
                    if user_dir.is_dir():
                        for session_dir in user_dir.iterdir():
                            if session_dir.is_dir():
                                for f in session_dir.iterdir():
                                    if f.is_file() and not f.name.endswith(".tmp"):
                                        videos.append({
                                            "user_id": user_dir.name,
                                            "session_id": session_dir.name,
                                            "filename": f.name,
                                            "size_bytes": f.stat().st_size,
                                            "created_at": datetime.fromtimestamp(
                                                f.stat().st_ctime, tz=timezone.utc
                                            ).isoformat(),
                                        })

        return videos

    def delete_video(
        self,
        user_id: str,
        session_id: str,
        filename: str = "video.webm",
    ) -> Dict[str, Any]:
        """
        Delete a video (must use secure wipe externally).
        This only removes the reference — actual wipe should use secure_wiper.
        """
        if not _validate_path_safe(user_id, session_id):
            return {"success": False, "reason": "Invalid path"}

        video_path = self._root / user_id / session_id / filename
        resolved = video_path.resolve()

        if not str(resolved).startswith(str(self._root.resolve())):
            return {"success": False, "reason": "Path traversal"}

        if not resolved.exists():
            return {"success": False, "reason": "Not found"}

        return {
            "success": True,
            "path": str(resolved),
            "size_bytes": resolved.stat().st_size,
            "note": "Use secure_wiper.secure_wipe() for actual deletion",
        }
