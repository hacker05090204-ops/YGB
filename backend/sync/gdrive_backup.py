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
import hashlib
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ygb.sync.gdrive")

SYNC_ROOT = Path(os.getenv("YGB_SYNC_ROOT", "C:\\ygb_storage"))
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


class BackupIntegrityError(RuntimeError):
    """Raised when staged or downloaded backup integrity verification fails."""


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


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalize_relative_path(relative_path: str) -> str:
    normalized = str(relative_path or "").replace("\\", "/").strip()
    return normalized.lstrip("/")


def _build_sync_identity(relative_path: str, original_sha256: str) -> str:
    """
    FIX 7.5: Use sha256+path as unique key for GDrive sync.
    
    This ensures content-hash based deduplication and prevents
    duplicate uploads of the same content.
    """
    normalized_path = _normalize_relative_path(relative_path)
    return hashlib.sha256(
        f"{normalized_path}|{original_sha256}".encode("utf-8")
    ).hexdigest()


def _build_staged_stem(relative_path: str, sync_identity: str) -> str:
    safe_name = _normalize_relative_path(relative_path).replace("/", "__") or "root"
    if len(safe_name) > 80:
        safe_name = safe_name[-80:]
    return f"{safe_name}__{sync_identity}"


def _load_sidecar_metadata(sidecar_path: Path) -> dict:
    try:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BackupIntegrityError(f"Backup sidecar missing: {sidecar_path}") from exc
    except json.JSONDecodeError as exc:
        raise BackupIntegrityError(f"Backup sidecar unreadable: {sidecar_path}") from exc
    if not isinstance(payload, dict):
        raise BackupIntegrityError(f"Backup sidecar schema invalid: {sidecar_path}")
    return payload


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


def _decrypt_data_strict(data: bytes) -> bytes:
    if not ENCRYPTION_KEY:
        raise BackupIntegrityError(
            "Encrypted backup cannot be restored without YGB_BACKUP_ENCRYPTION_KEY"
        )
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise BackupIntegrityError(
            "cryptography is required to restore encrypted backups"
        ) from exc

    try:
        return Fernet(ENCRYPTION_KEY.encode("utf-8")).decrypt(data)
    except Exception as exc:
        raise BackupIntegrityError(f"Encrypted backup decryption failed: {exc}") from exc


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


def _decompress_data_strict(data: bytes) -> bytes:
    try:
        import zstandard as zstd

        return zstd.ZstdDecompressor().decompress(data)
    except Exception as zstd_exc:
        try:
            import gzip

            return gzip.decompress(data)
        except Exception as gzip_exc:
            raise BackupIntegrityError(
                f"Compressed backup decompression failed: {zstd_exc}; {gzip_exc}"
            ) from gzip_exc


def restore_staged_backup_file(
    payload_path: Path,
    *,
    sidecar_path: Optional[Path] = None,
) -> tuple[bytes, dict]:
    """
    FIX 7.5: Verify hash after download to ensure integrity.
    
    This function validates:
    1. Staged payload hash matches sidecar
    2. Decrypted/decompressed content hash matches original
    3. Sync identity is correctly derived from path+hash
    """
    metadata_path = sidecar_path or _sidecar_for_payload(payload_path)
    meta = _load_sidecar_metadata(metadata_path)

    payload_bytes = payload_path.read_bytes()
    staged_sha256 = str(meta.get("staged_sha256", "") or "").strip().lower()
    if not staged_sha256:
        raise BackupIntegrityError(f"Backup sidecar missing staged_sha256: {metadata_path}")
    if _sha256_bytes(payload_bytes) != staged_sha256:
        raise BackupIntegrityError(f"Staged backup hash mismatch for {payload_path}")

    restored = payload_bytes
    if bool(meta.get("encrypted", False)):
        restored = _decrypt_data_strict(restored)
    if bool(meta.get("compressed", False)):
        restored = _decompress_data_strict(restored)

    original_sha256 = str(meta.get("original_sha256", "") or "").strip().lower()
    if not original_sha256:
        raise BackupIntegrityError(f"Backup sidecar missing original_sha256: {metadata_path}")
    if _sha256_bytes(restored) != original_sha256:
        raise BackupIntegrityError(f"Restored backup hash mismatch for {payload_path}")

    expected_identity = _build_sync_identity(
        str(meta.get("original_path", "") or ""),
        original_sha256,
    )
    if str(meta.get("sync_identity", "") or "") != expected_identity:
        raise BackupIntegrityError(f"Backup sidecar sync identity mismatch: {metadata_path}")

    return restored, meta


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
        original_path = _normalize_relative_path(relative_path)
        original_data = file_path.read_bytes()
        original_sha256 = _sha256_bytes(original_data)
        sync_identity = _build_sync_identity(original_path, original_sha256)
        data = original_data
        if compress:
            data = _compress_data(data)
        if encrypt:
            data = _encrypt_data(data)

        staged_stem = _build_staged_stem(original_path, sync_identity)
        staged = PENDING_DIR / f"{staged_stem}.enc"
        staged.write_bytes(data)

        # Write metadata sidecar
        meta = {
            "original_path": original_path,
            "original_size": file_path.stat().st_size,
            "original_sha256": original_sha256,
            "sync_identity": sync_identity,
            "payload_name": staged.name,
            "staged_size": len(data),
            "staged_sha256": _sha256_bytes(data),
            "compressed": compress,
            "encrypted": encrypt,
            "staged_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        meta_path = _sidecar_for_payload(staged)
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        logger.info(
            "Staged for GDrive: %s identity=%s (%.1f KB)",
            original_path,
            sync_identity[:16],
            len(data) / 1024,
        )
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
    staged = stage_file_for_upload(
        MANIFEST_PATH,
        "manifest.json",
        compress=True,
        encrypt=True,
    )
    if staged is None:
        return False
    logger.info("Manifest staged for GDrive upload: %s", staged.name)
    return _upload_pending_files()


def _rclone_remote_file_exists(name: str) -> bool:
    import subprocess

    if not _rclone_available():
        return False

    def _run_check() -> bool:
        result = subprocess.run(
            [
                "rclone",
                "lsf",
                GDRIVE_REMOTE,
                "--files-only",
                "--include",
                name,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[:500] or f"rclone exit {result.returncode}")
        matches = {line.strip() for line in (result.stdout or "").splitlines() if line.strip()}
        return name in matches

    try:
        return bool(_call_with_retry(_run_check, label=f"rclone remote lookup {name}"))
    except Exception as exc:
        logger.warning("rclone duplicate check failed for %s: %s", name, exc)
        return False


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
        remaining_payloads: list[Path] = []
        for payload in payloads:
            sidecar = _sidecar_for_payload(payload)
            if not sidecar.exists():
                raise BackupIntegrityError(f"Backup sidecar missing for payload {payload.name}")
            payload_exists = _rclone_remote_file_exists(payload.name)
            sidecar_exists = _rclone_remote_file_exists(sidecar.name)
            if payload_exists and sidecar_exists:
                logger.info("Skipping GDrive upload for existing backup identity: %s", payload.name)
                _move_uploaded_payload(payload)
                continue
            remaining_payloads.append(payload)

        if not remaining_payloads:
            return True

        def _run_copy():
            result = subprocess.run(
                [
                    "rclone", "copy",
                    str(PENDING_DIR),
                    GDRIVE_REMOTE,
                    "--include", "*.enc",
                    "--include", "*.meta.json",
                    "--progress",
                    "--transfers", "4",
                ],
                capture_output=True, text=True, timeout=600,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr[:500] or f"rclone exit {result.returncode}")
            return result

        _call_with_retry(_run_copy, label="rclone upload")
        for payload in remaining_payloads:
            if payload.exists():
                _move_uploaded_payload(payload)
        logger.info("rclone upload complete (%d files)", len(remaining_payloads))
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

        def _upload_named_file(local_path: Path) -> None:
            media = MediaFileUpload(
                str(local_path),
                resumable=True,
                chunksize=GDRIVE_SDK_CHUNK_BYTES,
            )
            file_metadata = {
                "name": local_path.name,
                "parents": [GDRIVE_FOLDER_ID] if GDRIVE_FOLDER_ID else [],
            }

            def _create_file():
                return service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields="id",
                    supportsAllDrives=True,
                ).execute()

            _call_with_retry(_create_file, label=f"gdrive sdk upload {local_path.name}")

        for f in payloads:
            sidecar = _sidecar_for_payload(f)
            if not sidecar.exists():
                raise BackupIntegrityError(f"Backup sidecar missing for payload {f.name}")

            existing_payload_id = _find_existing_file_id(f.name)
            existing_sidecar_id = _find_existing_file_id(sidecar.name)
            if existing_payload_id and existing_sidecar_id:
                logger.info("Skipping SDK upload for existing backup identity: %s", f.name)
                if f.exists():
                    _move_uploaded_payload(f)
                uploaded += 1
                continue

            if not existing_payload_id:
                _upload_named_file(f)
            if not existing_sidecar_id:
                _upload_named_file(sidecar)
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
