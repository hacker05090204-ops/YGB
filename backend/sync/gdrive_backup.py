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
import shutil
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
GDRIVE_REMOTE = os.getenv("YGB_GDRIVE_REMOTE", "ygb-gdrive:YGB_Backups/")
GDRIVE_UPLOAD_RETRIES = max(1, int(os.getenv("YGB_GDRIVE_UPLOAD_RETRIES", "3")))
GDRIVE_UPLOAD_BASE_DELAY_SECONDS = max(
    0.5,
    float(os.getenv("YGB_GDRIVE_UPLOAD_BASE_DELAY_SECONDS", "1")),
)
GDRIVE_SDK_CHUNK_BYTES = max(
    256 * 1024,
    int(float(os.getenv("YGB_GDRIVE_SDK_CHUNK_MB", "8")) * 1024 * 1024),
)
ENCRYPTION_KEY = os.getenv("YGB_BACKUP_ENCRYPTION_KEY", "")
ENCRYPTION_REQUIRED = os.getenv("YGB_REQUIRE_ENCRYPTION", "true") == "true"

_upload_lock = threading.Lock()


class EncryptionRequiredError(RuntimeError):
    """Raised when backup encryption is mandatory but unavailable."""


def _encryption_required() -> bool:
    configured = os.getenv("YGB_REQUIRE_ENCRYPTION")
    if configured is None:
        return bool(ENCRYPTION_REQUIRED)
    return configured.strip().lower() == "true"


def _ensure_dirs():
    for d in [STAGING_DIR, PENDING_DIR, UPLOADED_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _pending_payload_files() -> list[Path]:
    _ensure_dirs()
    return sorted(
        f for f in PENDING_DIR.iterdir()
        if f.is_file() and f.suffix == ".enc"
    )


def _sidecar_for_payload(payload: Path) -> Path:
    return PENDING_DIR / f"{payload.stem}.meta.json"


def _move_uploaded_payload(payload: Path) -> None:
    _ensure_dirs()
    destination = UPLOADED_DIR / payload.name
    payload.replace(destination)
    sidecar = _sidecar_for_payload(payload)
    if sidecar.exists():
        sidecar.replace(UPLOADED_DIR / sidecar.name)


def _sdk_available() -> bool:
    try:
        from google.oauth2 import service_account  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401
        from googleapiclient.http import MediaFileUpload  # noqa: F401
        return True
    except ImportError:
        return False


def _rclone_available() -> bool:
    return shutil.which("rclone") is not None


def _active_gdrive_client() -> str:
    if _sdk_available() and Path(GDRIVE_CREDS_PATH).exists():
        return "sdk"
    if _rclone_available():
        return "rclone"
    return "none"


def _call_with_retry(operation, *, label: str):
    last_exc: Exception | None = None
    for attempt in range(1, GDRIVE_UPLOAD_RETRIES + 1):
        try:
            return operation()
        except Exception as exc:
            last_exc = exc
            if attempt >= GDRIVE_UPLOAD_RETRIES:
                break
            delay = min(
                GDRIVE_UPLOAD_BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
                8.0,
            )
            logger.warning(
                "%s failed on attempt %d/%d — retrying in %.1fs: %s",
                label,
                attempt,
                GDRIVE_UPLOAD_RETRIES,
                delay,
                exc,
            )
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"{label} failed without a captured exception")


def _encrypt_data(data: bytes) -> bytes:
    """Encrypt data with Fernet (AES-256-CBC). Returns encrypted bytes."""
    if not ENCRYPTION_KEY:
        if _encryption_required():
            raise EncryptionRequiredError(
                "Cannot backup without encryption. Set YGB_BACKUP_ENCRYPTION_KEY."
            )
        logger.warning("No encryption key set — uploading unencrypted")
        return data
    try:
        from cryptography.fernet import Fernet
        f = Fernet(ENCRYPTION_KEY.encode("utf-8"))
        return f.encrypt(data)
    except ImportError as exc:
        if _encryption_required():
            raise EncryptionRequiredError(
                "Cannot backup without encryption. Install cryptography."
            ) from exc
        logger.warning("cryptography not installed — uploading unencrypted")
        return data
    except Exception as exc:
        logger.error("Encryption failed: %s", exc)
        if _encryption_required():
            raise EncryptionRequiredError(
                "Cannot backup without encryption. Encryption operation failed."
            ) from exc
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
        if _encryption_required() and not encrypt:
            raise EncryptionRequiredError(
                "Cannot backup without encryption. Encryption is required."
            )
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
    except EncryptionRequiredError:
        raise
    except Exception as exc:
        logger.error("Failed to stage %s: %s", relative_path, exc)
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
    payloads = _pending_payload_files()
    if not payloads:
        return True
    if not _rclone_available():
        logger.warning("rclone not installed — skipping cloud upload")
        return False
    try:
        def _run_copy():
            result = subprocess.run(
                [
                    "rclone", "copy",
                    str(PENDING_DIR),
                    GDRIVE_REMOTE,
                    "--include", "*.enc",
                    "--progress",
                    "--transfers", "4",
                ],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr[:500] or f"rclone exit {result.returncode}")
            return result

        _call_with_retry(_run_copy, label="rclone upload")
        for payload in payloads:
            if payload.exists():
                _move_uploaded_payload(payload)
        logger.info("rclone upload complete (%d files)", len(payloads))
        return True
    except Exception as e:
        logger.error("rclone error: %s", e)
        return False


def _upload_with_sdk() -> bool:
    """Upload pending files using Google Drive Python SDK."""
    payloads = _pending_payload_files()
    if not payloads:
        return True
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
        service = build("drive", "v3", credentials=creds, cache_discovery=False)

        def _find_existing_file_id(name: str) -> Optional[str]:
            safe_name = name.replace("'", "\\'")
            query = f"name = '{safe_name}' and trashed = false"
            if GDRIVE_FOLDER_ID:
                query += f" and '{GDRIVE_FOLDER_ID}' in parents"
            response = service.files().list(
                q=query,
                spaces="drive",
                fields="files(id,name)",
                pageSize=1,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            matches = response.get("files", [])
            if not matches:
                return None
            return str(matches[0].get("id", "") or "") or None

        uploaded = 0
        for f in payloads:
            media = MediaFileUpload(
                str(f),
                resumable=True,
                chunksize=GDRIVE_SDK_CHUNK_BYTES,
            )
            existing_id = _find_existing_file_id(f.name)
            file_metadata = {
                "name": f.name,
                "parents": [GDRIVE_FOLDER_ID] if GDRIVE_FOLDER_ID else [],
            }

            def _upload_one():
                if existing_id:
                    return service.files().update(
                        fileId=existing_id,
                        media_body=media,
                        fields="id",
                        supportsAllDrives=True,
                    ).execute()
                return service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id",
                    supportsAllDrives=True,
                ).execute()

            _call_with_retry(_upload_one, label=f"gdrive sdk upload {f.name}")
            if f.exists():
                _move_uploaded_payload(f)
            uploaded += 1

        logger.info("GDrive SDK upload: %d files", uploaded)
        return uploaded == len(payloads)
    except Exception as e:
        logger.error("GDrive SDK upload failed: %s", e)
        return _upload_with_rclone()


def _upload_pending_files() -> bool:
    """Upload all pending files to Google Drive (tries SDK first, then rclone)."""
    with _upload_lock:
        pending = _pending_payload_files()
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
    pending = len(_pending_payload_files()) if PENDING_DIR.exists() else 0
    uploaded = len(
        [f for f in UPLOADED_DIR.iterdir() if f.is_file() and f.suffix == ".enc"]
    ) if UPLOADED_DIR.exists() else 0
    return {
        "enabled": GDRIVE_ENABLED,
        "credentials_found": Path(GDRIVE_CREDS_PATH).exists(),
        "folder_id": GDRIVE_FOLDER_ID[:8] + "..." if GDRIVE_FOLDER_ID else "",
        "pending_files": pending,
        "uploaded_files": uploaded,
        "encryption_configured": bool(ENCRYPTION_KEY),
        "sdk_available": _sdk_available(),
        "rclone_available": _rclone_available(),
        "active_client": _active_gdrive_client(),
    }
