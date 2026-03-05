"""
YGB Google Drive Backup — Encrypted cloud disaster recovery.

Uploads critical files (models, DB, reports) to Google Drive as
zstd-compressed + Fernet-encrypted chunks.  Manifest is always uploaded
so recovery can bootstrap from cloud alone.

Supports two modes:
  1. Python SDK (google-api-python-client) — programmatic, fine-grained
  2. rclone fallback — bulk sync, simpler setup

Cloud backup is async and NEVER blocks the main sync cycle.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ygb.sync.gdrive")

SYNC_ROOT = Path(os.getenv("YGB_SYNC_ROOT", "D:\\"))
SYNC_META = SYNC_ROOT / "ygb_sync"
MANIFEST_PATH = SYNC_META / "manifest.json"
STAGING_DIR = SYNC_ROOT / "ygb_gdrive_staging"
PENDING_DIR = STAGING_DIR / "pending"
UPLOADED_DIR = STAGING_DIR / "uploaded"

GDRIVE_ENABLED = os.getenv("YGB_GDRIVE_ENABLED", "false").lower() == "true"
GDRIVE_FOLDER_ID = os.getenv("YGB_GDRIVE_FOLDER_ID", "")
GDRIVE_CREDS_PATH = os.getenv(
    "YGB_GDRIVE_CREDENTIALS_PATH",
    "C:/ygb_data/gdrive_service_account.json",
)
ENCRYPTION_KEY = os.getenv("YGB_BACKUP_ENCRYPTION_KEY", "")

_upload_lock = threading.Lock()


def _ensure_dirs():
    for d in [STAGING_DIR, PENDING_DIR, UPLOADED_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _encrypt_data(data: bytes) -> bytes:
    """Encrypt data with Fernet (AES-256-CBC). Returns encrypted bytes."""
    if not ENCRYPTION_KEY:
        logger.warning("No encryption key set — uploading unencrypted")
        return data
    try:
        from cryptography.fernet import Fernet
        f = Fernet(ENCRYPTION_KEY.encode("utf-8"))
        return f.encrypt(data)
    except ImportError:
        logger.warning("cryptography not installed — uploading unencrypted")
        return data
    except Exception as e:
        logger.error("Encryption failed: %s", e)
        return data


def _decrypt_data(data: bytes) -> bytes:
    """Decrypt Fernet-encrypted data."""
    if not ENCRYPTION_KEY:
        return data
    try:
        from cryptography.fernet import Fernet
        f = Fernet(ENCRYPTION_KEY.encode("utf-8"))
        return f.decrypt(data)
    except Exception as e:
        logger.error("Decryption failed: %s", e)
        return data


def _compress_data(data: bytes) -> bytes:
    """Compress with zstd level 3."""
    try:
        import zstandard as zstd
        cctx = zstd.ZstdCompressor(level=3)
        return cctx.compress(data)
    except ImportError:
        import gzip
        return gzip.compress(data, compresslevel=6)


def _decompress_data(data: bytes) -> bytes:
    """Decompress zstd (or gzip fallback)."""
    try:
        import zstandard as zstd
        dctx = zstd.ZstdDecompressor()
        return dctx.decompress(data)
    except Exception:
        try:
            import gzip
            return gzip.decompress(data)
        except Exception:
            return data  # Already uncompressed


def stage_file_for_upload(
    file_path: Path,
    relative_path: str,
    compress: bool = True,
    encrypt: bool = True,
) -> Optional[Path]:
    """
    Stage a file for async upload to Google Drive.
    Compress → Encrypt → Write to staging/pending.
    """
    _ensure_dirs()
    try:
        data = file_path.read_bytes()
        if compress:
            data = _compress_data(data)
        if encrypt:
            data = _encrypt_data(data)

        safe_name = relative_path.replace("/", "__").replace("\\", "__")
        staged = PENDING_DIR / f"{safe_name}.enc"
        staged.write_bytes(data)

        # Write metadata sidecar
        meta = {
            "original_path": relative_path,
            "original_size": file_path.stat().st_size,
            "staged_size": len(data),
            "compressed": compress,
            "encrypted": encrypt,
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        meta_path = PENDING_DIR / f"{safe_name}.meta.json"
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        logger.info("Staged for GDrive: %s (%.1f KB)", relative_path, len(data) / 1024)
        return staged
    except Exception as e:
        logger.error("Failed to stage %s: %s", relative_path, e)
        return None


def upload_manifest_to_gdrive():
    """Upload the current manifest to Google Drive (always, as recovery index)."""
    if not GDRIVE_ENABLED:
        return False
    if not MANIFEST_PATH.exists():
        return False

    data = MANIFEST_PATH.read_bytes()
    compressed = _compress_data(data)
    encrypted = _encrypt_data(compressed)

    staged = PENDING_DIR / "manifest.json.enc"
    _ensure_dirs()
    staged.write_bytes(encrypted)
    logger.info("Manifest staged for GDrive upload (%.1f KB)", len(encrypted) / 1024)
    return _upload_pending_files()


def _upload_with_rclone() -> bool:
    """Upload pending files using rclone (simpler setup)."""
    import subprocess
    try:
        result = subprocess.run(
            [
                "rclone", "copy",
                str(PENDING_DIR),
                f"ygb-gdrive:YGB_Backups/",
                "--progress",
                "--transfers", "4",
            ],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode == 0:
            # Move uploaded files to uploaded dir
            for f in PENDING_DIR.iterdir():
                if f.is_file():
                    dest = UPLOADED_DIR / f.name
                    f.replace(dest)
            logger.info("rclone upload complete")
            return True
        else:
            logger.error("rclone failed: %s", result.stderr[:500])
            return False
    except FileNotFoundError:
        logger.warning("rclone not installed — skipping cloud upload")
        return False
    except Exception as e:
        logger.error("rclone error: %s", e)
        return False


def _upload_with_sdk() -> bool:
    """Upload pending files using Google Drive Python SDK."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        logger.warning("google-api-python-client not installed — trying rclone")
        return _upload_with_rclone()

    if not Path(GDRIVE_CREDS_PATH).exists():
        logger.warning("GDrive credentials not found at %s", GDRIVE_CREDS_PATH)
        return _upload_with_rclone()

    try:
        creds = service_account.Credentials.from_service_account_file(
            GDRIVE_CREDS_PATH,
            scopes=["https://www.googleapis.com/auth/drive.file"],
        )
        service = build("drive", "v3", credentials=creds)

        uploaded = 0
        for f in PENDING_DIR.iterdir():
            if not f.is_file() or f.suffix == ".json":
                continue  # Skip metadata sidecars — upload .enc files only
            media = MediaFileUpload(str(f), resumable=True)
            file_metadata = {
                "name": f.name,
                "parents": [GDRIVE_FOLDER_ID] if GDRIVE_FOLDER_ID else [],
            }
            service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id",
            ).execute()
            # Move to uploaded
            dest = UPLOADED_DIR / f.name
            f.replace(dest)
            # Also move sidecar
            sidecar = PENDING_DIR / f"{f.stem.replace('.enc', '')}.meta.json"
            if sidecar.exists():
                sidecar.replace(UPLOADED_DIR / sidecar.name)
            uploaded += 1

        logger.info("GDrive SDK upload: %d files", uploaded)
        return uploaded > 0
    except Exception as e:
        logger.error("GDrive SDK upload failed: %s", e)
        return _upload_with_rclone()


def _upload_pending_files() -> bool:
    """Upload all pending files to Google Drive (tries SDK first, then rclone)."""
    with _upload_lock:
        pending = list(PENDING_DIR.iterdir())
        if not pending:
            return True
        logger.info("Uploading %d pending files to Google Drive...", len(pending))
        return _upload_with_sdk()


def async_upload():
    """Run upload in background thread (non-blocking)."""
    if not GDRIVE_ENABLED:
        return
    t = threading.Thread(target=_upload_pending_files, daemon=True)
    t.start()


def get_gdrive_status() -> dict:
    """Return current GDrive backup status."""
    _ensure_dirs()
    pending = len(list(PENDING_DIR.iterdir())) if PENDING_DIR.exists() else 0
    uploaded = len(list(UPLOADED_DIR.iterdir())) if UPLOADED_DIR.exists() else 0
    return {
        "enabled": GDRIVE_ENABLED,
        "credentials_found": Path(GDRIVE_CREDS_PATH).exists(),
        "folder_id": GDRIVE_FOLDER_ID[:8] + "..." if GDRIVE_FOLDER_ID else "",
        "pending_files": pending,
        "uploaded_files": uploaded,
        "encryption_configured": bool(ENCRYPTION_KEY),
    }
