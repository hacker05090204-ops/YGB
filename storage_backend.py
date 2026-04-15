"""
Unified Storage Backend — D: Drive + Google Drive Fallback
==========================================================

PRIMARY: D:\\ (local/NAS via Tailscale)
FALLBACK: Google Drive (when D: is inactive/unavailable)

Usage:
    from storage_backend import get_storage
    storage = get_storage()
    storage.read("path/to/file")
    storage.write("path/to/file", data)
    storage.list_dir("path/to/dir")

Environment Variables:
    YGB_STORAGE_PRIMARY    D:\\ path (default: D:\\)
    YGB_GDRIVE_FOLDER_ID   Google Drive folder ID for fallback
    YGB_GDRIVE_CREDS_PATH  Path to Google service account JSON key
    YGB_STORAGE_MODE       "auto" (default), "local", "gdrive"
"""

import os
import json
import time
import shutil
import logging
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

PRIMARY_PATH = Path(os.environ.get("YGB_STORAGE_PRIMARY", "C:\\ygb_storage"))
GDRIVE_FOLDER_ID = os.environ.get("YGB_GDRIVE_FOLDER_ID", "")
GDRIVE_CREDS_PATH = os.environ.get("YGB_GDRIVE_CREDS_PATH", "")
STORAGE_MODE = os.environ.get("YGB_STORAGE_MODE", "auto").lower()

# Health check interval (seconds)
_HEALTH_CHECK_INTERVAL = 30
_last_health_check = 0.0
_d_drive_healthy = True


# =============================================================================
# ABSTRACT STORAGE INTERFACE
# =============================================================================

class StorageBackend(ABC):
    """Abstract storage interface for unified file access."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this storage backend is currently available."""
        ...

    @abstractmethod
    def read(self, path: str) -> bytes:
        """Read a file and return its contents as bytes."""
        ...

    @abstractmethod
    def write(self, path: str, data: bytes) -> bool:
        """Write data to a file. Returns True on success."""
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if a file or directory exists."""
        ...

    @abstractmethod
    def list_dir(self, path: str) -> List[str]:
        """List contents of a directory."""
        ...

    @abstractmethod
    def delete(self, path: str) -> bool:
        """Delete a file. Returns True on success."""
        ...

    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """Return backend info (name, status, capacity, etc.)."""
        ...


# =============================================================================
# LOCAL D: DRIVE BACKEND
# =============================================================================

class LocalDriveBackend(StorageBackend):
    """Primary storage: Local D:\\ drive (accessible via Tailscale NAS)."""

    def __init__(self, root: Path = PRIMARY_PATH):
        self.root = root
        self._name = "LocalDrive"

    def is_available(self) -> bool:
        """Check if D: drive is mounted, writable, and has space."""
        global _last_health_check, _d_drive_healthy

        now = time.time()
        if now - _last_health_check < _HEALTH_CHECK_INTERVAL:
            return _d_drive_healthy

        _last_health_check = now

        try:
            # Check if drive exists
            if not self.root.exists():
                logger.warning(f"[STORAGE] {self.root} not found")
                _d_drive_healthy = False
                return False

            # Check if writable (create temp file)
            test_file = self.root / ".ygb_health_check"
            test_file.write_text("ok")
            test_file.unlink()

            # Check free space (require at least 1 GB)
            usage = shutil.disk_usage(str(self.root))
            free_gb = usage.free / (1024 ** 3)
            if free_gb < 1.0:
                logger.warning(f"[STORAGE] {self.root} low space: {free_gb:.1f} GB")
                _d_drive_healthy = False
                return False

            _d_drive_healthy = True
            return True

        except Exception as e:
            logger.warning(f"[STORAGE] {self.root} health check failed: {e}")
            _d_drive_healthy = False
            return False

    def _resolve(self, path: str) -> Path:
        """Resolve relative path against root."""
        return self.root / path

    def read(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def write(self, path: str, data: bytes) -> bool:
        try:
            target = self._resolve(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return True
        except Exception as e:
            logger.error(f"[STORAGE] LocalDrive write failed: {e}")
            return False

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def list_dir(self, path: str) -> List[str]:
        target = self._resolve(path)
        if not target.is_dir():
            return []
        return [p.name for p in target.iterdir()]

    def delete(self, path: str) -> bool:
        try:
            self._resolve(path).unlink()
            return True
        except Exception as e:
            logger.error(f"[STORAGE] LocalDrive delete failed: {e}")
            return False

    def get_info(self) -> Dict[str, Any]:
        try:
            usage = shutil.disk_usage(str(self.root))
            return {
                "backend": self._name,
                "path": str(self.root),
                "available": self.is_available(),
                "total_gb": round(usage.total / (1024 ** 3), 2),
                "free_gb": round(usage.free / (1024 ** 3), 2),
                "used_pct": round(usage.used / usage.total * 100, 1),
            }
        except Exception:
            return {
                "backend": self._name,
                "path": str(self.root),
                "available": False,
            }


# =============================================================================
# GOOGLE DRIVE FALLBACK BACKEND
# =============================================================================

class GoogleDriveBackend(StorageBackend):
    """
    Fallback storage: Google Drive via service account.

    Requires:
      - google-api-python-client, google-auth packages
      - Service account JSON key (YGB_GDRIVE_CREDS_PATH)
      - Target folder ID (YGB_GDRIVE_FOLDER_ID)
    """

    def __init__(self, folder_id: str = GDRIVE_FOLDER_ID,
                 creds_path: str = GDRIVE_CREDS_PATH):
        self.folder_id = folder_id
        self.creds_path = creds_path
        self._service = None
        self._name = "GoogleDrive"
        self._initialized = False

    def _get_service(self):
        """Lazy-init Google Drive API service."""
        if self._service is not None:
            return self._service

        if not self.creds_path or not os.path.exists(self.creds_path):
            logger.warning("[STORAGE] Google Drive creds not found — fallback unavailable")
            return None

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            SCOPES = ['https://www.googleapis.com/auth/drive']
            creds = service_account.Credentials.from_service_account_file(
                self.creds_path, scopes=SCOPES,
            )
            self._service = build('drive', 'v3', credentials=creds)
            self._initialized = True
            logger.info("[STORAGE] Google Drive API initialized")
            return self._service

        except ImportError:
            logger.warning(
                "[STORAGE] Google Drive packages not installed. "
                "Run: pip install google-api-python-client google-auth"
            )
            return None
        except Exception as e:
            logger.error(f"[STORAGE] Google Drive init failed: {e}")
            return None

    def _find_file(self, path: str) -> Optional[str]:
        """Find file ID by path within the target folder."""
        service = self._get_service()
        if not service:
            return None

        name = os.path.basename(path)
        try:
            query = (
                f"name='{name}' and "
                f"'{self.folder_id}' in parents and "
                f"trashed=false"
            )
            results = service.files().list(
                q=query, fields="files(id, name)", pageSize=1,
            ).execute()
            files = results.get("files", [])
            return files[0]["id"] if files else None
        except Exception as e:
            logger.error(f"[STORAGE] Google Drive search failed: {e}")
            return None

    def is_available(self) -> bool:
        """Check if Google Drive API is accessible."""
        service = self._get_service()
        if not service:
            return False
        try:
            service.files().get(fileId=self.folder_id, fields="id").execute()
            return True
        except Exception:
            return False

    def read(self, path: str) -> bytes:
        service = self._get_service()
        if not service:
            raise IOError("Google Drive not available")

        file_id = self._find_file(path)
        if not file_id:
            raise FileNotFoundError(f"Not found on Google Drive: {path}")

        from googleapiclient.http import MediaIoBaseDownload
        import io

        request = service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue()

    def write(self, path: str, data: bytes) -> bool:
        service = self._get_service()
        if not service:
            return False

        from googleapiclient.http import MediaInMemoryUpload
        import io

        name = os.path.basename(path)
        media = MediaInMemoryUpload(data)

        # Check if file already exists (update vs create)
        existing_id = self._find_file(path)

        try:
            if existing_id:
                service.files().update(
                    fileId=existing_id, media_body=media,
                ).execute()
            else:
                metadata = {
                    "name": name,
                    "parents": [self.folder_id],
                }
                service.files().create(
                    body=metadata, media_body=media,
                ).execute()
            logger.info(f"[STORAGE] Google Drive write: {name}")
            return True
        except Exception as e:
            logger.error(f"[STORAGE] Google Drive write failed: {e}")
            return False

    def exists(self, path: str) -> bool:
        return self._find_file(path) is not None

    def list_dir(self, path: str) -> List[str]:
        service = self._get_service()
        if not service:
            return []
        try:
            query = f"'{self.folder_id}' in parents and trashed=false"
            results = service.files().list(
                q=query, fields="files(name)", pageSize=100,
            ).execute()
            return [f["name"] for f in results.get("files", [])]
        except Exception:
            return []

    def delete(self, path: str) -> bool:
        service = self._get_service()
        if not service:
            return False
        file_id = self._find_file(path)
        if not file_id:
            return False
        try:
            service.files().delete(fileId=file_id).execute()
            return True
        except Exception:
            return False

    def get_info(self) -> Dict[str, Any]:
        return {
            "backend": self._name,
            "folder_id": self.folder_id,
            "available": self.is_available() if self.creds_path else False,
            "creds_configured": bool(self.creds_path),
            "initialized": self._initialized,
        }


# =============================================================================
# UNIFIED STORAGE (AUTO-FAILOVER)
# =============================================================================

class UnifiedStorage:
    """
    Unified storage with automatic failover.

    Priority:
      1. D:\\ drive (local/NAS via Tailscale)
      2. Google Drive (cloud fallback when D: is inactive)

    Privacy:
      - All Tailscale traffic is WireGuard encrypted (E2E)
      - shields-up mode blocks unsolicited incoming connections
      - Google Drive uses service account (no personal OAuth)
    """

    def __init__(self):
        self.local = LocalDriveBackend()
        self.gdrive = GoogleDriveBackend()
        self._active_backend = None
        self._check_active()

    def _check_active(self) -> StorageBackend:
        """Determine active backend with auto-failover."""
        if STORAGE_MODE == "local":
            self._active_backend = self.local
            return self.local

        if STORAGE_MODE == "gdrive":
            self._active_backend = self.gdrive
            return self.gdrive

        # Auto mode: prefer local, fallback to gdrive
        if self.local.is_available():
            if self._active_backend != self.local:
                logger.info("[STORAGE] ✅ Active backend: LocalDrive (D:\\)")
                self._active_backend = self.local
            return self.local

        # D: unavailable — failover to Google Drive
        if self.gdrive.is_available():
            if self._active_backend != self.gdrive:
                logger.warning(
                    "[STORAGE] ⚠️ D:\\ unavailable — failing over to Google Drive"
                )
                self._active_backend = self.gdrive
            return self.gdrive

        # Both unavailable
        logger.error("[STORAGE] ❌ No storage backend available!")
        self._active_backend = self.local  # optimistic default
        return self.local

    @property
    def active(self) -> StorageBackend:
        """Get currently active backend (re-checks health)."""
        return self._check_active()

    @property
    def backend_name(self) -> str:
        """Name of the currently active backend."""
        return self._active_backend._name if self._active_backend else "None"

    def read(self, path: str) -> bytes:
        return self.active.read(path)

    def write(self, path: str, data: bytes) -> bool:
        return self.active.write(path, data)

    def exists(self, path: str) -> bool:
        return self.active.exists(path)

    def list_dir(self, path: str) -> List[str]:
        return self.active.list_dir(path)

    def delete(self, path: str) -> bool:
        return self.active.delete(path)

    def get_status(self) -> Dict[str, Any]:
        """Get full storage status report."""
        return {
            "active_backend": self.backend_name,
            "mode": STORAGE_MODE,
            "local": self.local.get_info(),
            "gdrive": self.gdrive.get_info(),
        }


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_storage_instance: Optional[UnifiedStorage] = None


def get_storage() -> UnifiedStorage:
    """Get the global unified storage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = UnifiedStorage()
    return _storage_instance


def get_storage_status() -> Dict[str, Any]:
    """Get current storage status (for API/telemetry)."""
    return get_storage().get_status()


# =============================================================================
# CLI DIAGNOSTIC
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    storage = get_storage()
    status = storage.get_status()
    print(json.dumps(status, indent=2))
