"""
Report Generator API — Backend endpoints for report generation and video recording metadata.

Provides:
- Report creation, listing, and retrieval
- Video recording metadata lifecycle (start, stop, attach to report)
- Governance audit logging for all operations
- Persistence via storage_bridge

ZERO mock data. ZERO auto-approve. ZERO bypass.
"""

import os
import sys
import json
import time
import secrets
import logging
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Dict, List

from fastapi import APIRouter, Request, HTTPException, Depends

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.auth.auth_guard import require_auth

logger = logging.getLogger("ygb.report_generator")
REPORT_GENERATOR_VERSION = "1.0"


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    missing_fields: list[str]
    errors: list[str]


@dataclass(frozen=True)
class ReportExportRecord:
    report_id: str
    exported_at: str
    format: str
    export_size_bytes: int


ReportExportLog = deque(maxlen=1000)


class ReportValidator:
    REQUIRED = ["generated_at", "generator_version"]

    @staticmethod
    def validate(report: dict) -> ValidationResult:
        missing_fields = [field for field in ReportValidator.REQUIRED if not report.get(field)]
        errors: list[str] = []
        generated_at = report.get("generated_at")
        generator_version = report.get("generator_version")

        if generated_at and not _is_iso8601_timestamp(generated_at):
            errors.append("Invalid generated_at: expected ISO8601 timestamp")
        if generator_version and generator_version != REPORT_GENERATOR_VERSION:
            errors.append(
                f"Invalid generator_version: expected {REPORT_GENERATOR_VERSION}"
            )

        return ValidationResult(
            valid=not missing_fields and not errors,
            missing_fields=missing_fields,
            errors=errors,
        )


def _get_db_path() -> str:
    """Resolve SQLite path from DATABASE_URL env var."""
    url = os.environ.get("DATABASE_URL", "sqlite:///C:/ygb_data/ygb.db")
    return url.replace("sqlite:///", "")


def get_db_connection():
    """Get a direct SQLite connection."""
    import sqlite3
    db_path = _get_db_path()
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return sqlite3.connect(db_path)
    except Exception as e:
        logger.error("Failed to connect to DB at %s: %s", db_path, e)
        return None


def _log_activity(user_id: str, action: str, detail: str):
    """Best-effort activity logging via storage bridge."""
    try:
        from backend.storage.storage_bridge import log_activity
        log_activity(user_id, action, detail)
    except Exception as exc:
        logger.info("AUDIT [%s] %s: %s (storage bridge unavailable: %s)", user_id, action, detail, exc)

router = APIRouter(prefix="/api/reports", tags=["reports"])

# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================

_TABLES_CREATED = False


def _ensure_tables():
    """Create report and video_recording tables if they don't exist."""
    global _TABLES_CREATED
    if _TABLES_CREATED:
        return

    conn = get_db_connection()
    if not conn:
        logger.warning("No DB connection — report tables not created")
        return

    try:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                report_type TEXT DEFAULT 'general',
                status TEXT DEFAULT 'draft',
                content TEXT DEFAULT '{}',
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_recordings (
                id TEXT PRIMARY KEY,
                report_id TEXT,
                filename TEXT NOT NULL,
                duration_seconds REAL DEFAULT 0,
                file_size_bytes INTEGER DEFAULT 0,
                status TEXT DEFAULT 'recording',
                started_at TEXT NOT NULL,
                stopped_at TEXT,
                storage_path TEXT,
                created_by TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                FOREIGN KEY (report_id) REFERENCES reports(id)
            )
        """)

        conn.commit()
        _TABLES_CREATED = True
        logger.info("Report and video_recording tables ready")
    except Exception as e:
        logger.error("Failed to create report tables: %s", e)
    finally:
        conn.close()


# =============================================================================
# HELPERS
# =============================================================================

def _generate_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8)}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_unavailable_detail() -> Dict[str, Any]:
    return {
        "error": "SERVICE_UNAVAILABLE",
        "detail": "Database unavailable",
        "fallback_available": False,
    }


def _is_iso8601_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _normalize_generated_at(value: Any, fallback: Optional[str] = None) -> str:
    if _is_iso8601_timestamp(value):
        return str(value)
    if _is_iso8601_timestamp(fallback):
        return str(fallback)
    return _now_iso()


def _validation_errors_for_report(report: Dict[str, Any]) -> List[str]:
    validation = ReportValidator.validate(report)
    validation_errors = [
        f"Missing required field: {field}" for field in validation.missing_fields
    ]
    validation_errors.extend(validation.errors)
    return validation_errors


def _append_report_export_record(
    report: Dict[str, Any], *, export_format: str = "json"
) -> ReportExportRecord:
    try:
        export_bytes = len(
            json.dumps(report, sort_keys=True, default=str).encode("utf-8")
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Report export payload could not be serialized") from exc

    record = ReportExportRecord(
        report_id=str(report.get("id", "")),
        exported_at=_now_iso(),
        format=export_format,
        export_size_bytes=export_bytes,
    )
    ReportExportLog.append(record)
    return record


def _normalize_report_metadata(metadata: Any, *, generated_at: Optional[str] = None) -> dict:
    """Attach required generator metadata to report metadata payloads."""
    normalized = dict(metadata) if isinstance(metadata, dict) else {}
    normalized["generated_at"] = _normalize_generated_at(
        normalized.get("generated_at"), generated_at
    )
    normalized["generator_version"] = REPORT_GENERATOR_VERSION
    return normalized


def _metadata_from_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """Safely parse report metadata from metadata_json."""
    metadata_json = report.get("metadata_json", {})
    if isinstance(metadata_json, dict):
        return dict(metadata_json)
    if not isinstance(metadata_json, str):
        return {}
    try:
        parsed = json.loads(metadata_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _finalize_report_for_response(
    report: Dict[str, Any], *, ensure_metadata: bool = True
) -> Dict[str, Any]:
    """Prepare report payloads for API responses with validation checks."""
    final_report = dict(report)
    metadata = _metadata_from_report(final_report)

    if ensure_metadata:
        final_report["generated_at"] = _normalize_generated_at(
            final_report.get("generated_at") or metadata.get("generated_at"),
            final_report.get("created_at"),
        )
        final_report["generator_version"] = REPORT_GENERATOR_VERSION
        merged_metadata = dict(metadata)
        merged_metadata["generated_at"] = final_report["generated_at"]
        merged_metadata["generator_version"] = final_report["generator_version"]
        if "metadata_json" in final_report:
            final_report["metadata_json"] = json.dumps(merged_metadata)

    validation_errors = _validation_errors_for_report(final_report)
    if validation_errors:
        logger.warning(
            "Report validation failed for %s: validation_errors=%s",
            final_report.get("id", "unknown"),
            validation_errors,
        )
        final_report["validation_warnings"] = validation_errors
    else:
        final_report.pop("validation_warnings", None)

    return final_report


# =============================================================================
# REPORT ENDPOINTS
# =============================================================================

@router.post("")
async def create_report(request: Request, user=Depends(require_auth)):
    """Create a new report."""
    _ensure_tables()
    _t0 = time.monotonic()
    body = await request.json()
    user_id = user.get("sub", "")

    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(status_code=400, detail={
            "error": "VALIDATION_ERROR", "detail": "Title is required"
        })

    report_id = _generate_id("rpt")
    now = _now_iso()
    metadata = _normalize_report_metadata(body.get("metadata", {}), generated_at=now)
    report = {
        "id": report_id,
        "title": title,
        "description": body.get("description", ""),
        "report_type": body.get("report_type", "general"),
        "status": "draft",
        "content": json.dumps(body.get("content", {})),
        "created_by": user_id,
        "created_at": now,
        "updated_at": now,
        "metadata_json": json.dumps(metadata),
        "generated_at": metadata["generated_at"],
        "generator_version": metadata["generator_version"],
    }

    validation_errors = _validation_errors_for_report(report)
    if validation_errors:
        logger.error(
            "Generated report %s failed validation before persistence: %s",
            report_id,
            validation_errors,
        )
        raise HTTPException(status_code=500, detail={
            "error": "INTERNAL_ERROR",
            "detail": "Generated report failed validation",
        })

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail=_db_unavailable_detail())

    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO reports (id, title, description, report_type, status,
               content, created_by, created_at, updated_at, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (report["id"], report["title"], report["description"],
             report["report_type"], report["status"], report["content"],
             report["created_by"], report["created_at"], report["updated_at"],
             report["metadata_json"]),
        )
        conn.commit()
    except Exception as e:
        logger.error("Failed to create report: %s", e)
        raise HTTPException(status_code=500, detail={
            "error": "INTERNAL_ERROR", "detail": "Failed to create report"
        })
    finally:
        conn.close()

    # Emit report generation latency metric
    _rpt_latency = round((time.monotonic() - _t0) * 1000, 2)
    try:
        from backend.observability.metrics import metrics_registry
        metrics_registry.record("report_generation_latency_ms", _rpt_latency)
    except Exception as exc:
        logger.warning(
            "Non-critical failure while recording report generation latency: %s",
            exc,
            exc_info=True,
        )

    _log_activity(user_id, "REPORT_CREATED", f"Report '{title}' created ({report_id})")
    logger.info("Report created: %s by %s", report_id, user_id)

    response_report = _finalize_report_for_response(
        {**report, "content": body.get("content", {})}
    )
    try:
        _append_report_export_record(response_report)
    except ValueError as exc:
        logger.error("Failed to append export record for %s: %s", report_id, exc)
        raise HTTPException(status_code=500, detail={
            "error": "INTERNAL_ERROR",
            "detail": "Failed to record report export metadata",
        })
    return {"success": True, "report": response_report}


@router.get("")
async def list_reports(request: Request, user=Depends(require_auth)):
    """List all reports for the authenticated user."""
    _ensure_tables()
    user_id = user.get("sub", "")
    role = user.get("role", "")

    conn = get_db_connection()
    if not conn:
        return {"success": True, "reports": []}

    try:
        cursor = conn.cursor()
        if role == "admin":
            cursor.execute(
                "SELECT * FROM reports ORDER BY updated_at DESC LIMIT 100"
            )
        else:
            cursor.execute(
                "SELECT * FROM reports WHERE created_by = ? ORDER BY updated_at DESC LIMIT 100",
                (user_id,),
            )
        columns = [desc[0] for desc in cursor.description]
        reports = [
            _finalize_report_for_response(dict(zip(columns, row)))
            for row in cursor.fetchall()
        ]
    except Exception as e:
        logger.error("Failed to list reports: %s", e)
        reports = []
    finally:
        conn.close()

    return {"success": True, "reports": reports}


@router.get("/{report_id}")
async def get_report(report_id: str, user=Depends(require_auth)):
    """Get a specific report."""
    _ensure_tables()
    user_id = user.get("sub", "")

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail=_db_unavailable_detail())

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={
                "error": "NOT_FOUND", "detail": "Report not found"
            })
        columns = [desc[0] for desc in cursor.description]
        report = dict(zip(columns, row))

        # IDOR protection: non-admin can only view own reports
        if user.get("role") != "admin" and report["created_by"] != user_id:
            raise HTTPException(status_code=403, detail={
                "error": "FORBIDDEN", "detail": "Access denied"
            })

        report = _finalize_report_for_response(report)

        # Fetch attached videos
        cursor.execute(
            "SELECT * FROM video_recordings WHERE report_id = ? ORDER BY started_at DESC",
            (report_id,),
        )
        vid_columns = [desc[0] for desc in cursor.description]
        videos = [dict(zip(vid_columns, r)) for r in cursor.fetchall()]
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get report: %s", e)
        raise HTTPException(status_code=500, detail={
            "error": "INTERNAL_ERROR", "detail": "Failed to retrieve report"
        })
    finally:
        conn.close()

    return {"success": True, "report": report, "videos": videos}


# =============================================================================
# REPORT CONTENT ENDPOINT (frontend contract: GET /api/reports/{id}/content)
# =============================================================================

@router.get("/{report_id}/content")
async def get_report_content(report_id: str, user=Depends(require_auth)):
    """Get the content of a specific report (frontend contract match)."""
    _ensure_tables()
    user_id = user.get("sub", "")

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail=_db_unavailable_detail())

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, content, created_by, status, metadata_json FROM reports WHERE id = ?",
            (report_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={
                "error": "NOT_FOUND", "detail": "Report not found"
            })

        columns = [desc[0] for desc in cursor.description]
        report = dict(zip(columns, row))

        # IDOR protection: non-admin can only view own reports
        if user.get("role") != "admin" and report["created_by"] != user_id:
            raise HTTPException(status_code=403, detail={
                "error": "FORBIDDEN", "detail": "Access denied"
            })

        # Parse content JSON
        try:
            content = json.loads(report.get("content", "{}"))
        except (json.JSONDecodeError, TypeError):
            content = {}

        validated_report = _finalize_report_for_response(report)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get report content: %s", e)
        raise HTTPException(status_code=500, detail={
            "error": "INTERNAL_ERROR", "detail": "Failed to retrieve report content"
        })
    finally:
        conn.close()

    return {
        "success": True,
        "report_id": report_id,
        "content": content,
        "status": report.get("status", "unknown"),
        "generated_at": validated_report.get("generated_at"),
        "generator_version": validated_report.get("generator_version"),
        "validation_warnings": validated_report.get("validation_warnings", []),
    }


# =============================================================================
# VIDEO RECORDING ENDPOINTS
# =============================================================================

@router.post("/videos/start")
async def start_video_recording(request: Request, user=Depends(require_auth)):
    """Start a new video recording session."""
    _ensure_tables()
    body = await request.json()
    user_id = user.get("sub", "")

    video_id = _generate_id("vid")
    now = _now_iso()
    filename = body.get("filename", f"recording-{video_id}.webm")

    # Determine storage path
    hdd_root = os.getenv("YGB_HDD_ROOT", "D:/ygb_hdd")
    storage_dir = os.path.join(hdd_root, "videos", user_id)
    os.makedirs(storage_dir, exist_ok=True)
    storage_path = os.path.join(storage_dir, filename)

    recording = {
        "id": video_id,
        "report_id": body.get("report_id"),
        "filename": filename,
        "status": "recording",
        "started_at": now,
        "storage_path": storage_path,
        "created_by": user_id,
        "metadata_json": json.dumps(body.get("metadata", {})),
    }

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail=_db_unavailable_detail())

    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO video_recordings
               (id, report_id, filename, status, started_at, storage_path, created_by, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (recording["id"], recording["report_id"], recording["filename"],
             recording["status"], recording["started_at"], recording["storage_path"],
             recording["created_by"], recording["metadata_json"]),
        )
        conn.commit()
    except Exception as e:
        logger.error("Failed to start recording: %s", e)
        raise HTTPException(status_code=500, detail={
            "error": "INTERNAL_ERROR", "detail": "Failed to start recording"
        })
    finally:
        conn.close()

    _log_activity(user_id, "VIDEO_RECORDING_STARTED", f"Video recording started: {video_id}")
    return {"success": True, "recording": recording}


@router.post("/videos/{video_id}/stop")
async def stop_video_recording(video_id: str, request: Request, user=Depends(require_auth)):
    """Stop a video recording and save metadata."""
    _ensure_tables()
    body = await request.json()
    user_id = user.get("sub", "")
    now = _now_iso()

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail=_db_unavailable_detail())

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM video_recordings WHERE id = ?", (video_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={
                "error": "NOT_FOUND", "detail": "Recording not found"
            })

        columns = [desc[0] for desc in cursor.description]
        recording = dict(zip(columns, row))

        # IDOR protection
        if recording["created_by"] != user_id and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail={
                "error": "FORBIDDEN", "detail": "Access denied"
            })

        duration = body.get("duration_seconds", 0)
        file_size = body.get("file_size_bytes", 0)

        cursor.execute(
            """UPDATE video_recordings
               SET status = 'completed', stopped_at = ?, duration_seconds = ?, file_size_bytes = ?
               WHERE id = ?""",
            (now, duration, file_size, video_id),
        )
        conn.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to stop recording: %s", e)
        raise HTTPException(status_code=500, detail={
            "error": "INTERNAL_ERROR", "detail": "Failed to stop recording"
        })
    finally:
        conn.close()

    _log_activity(user_id, "VIDEO_RECORDING_STOPPED", f"Video recording stopped: {video_id}")
    return {
        "success": True,
        "recording": {
            "id": video_id,
            "status": "completed",
            "stopped_at": now,
            "duration_seconds": duration,
            "file_size_bytes": file_size,
        },
    }


@router.get("/videos")
async def list_videos(request: Request, user=Depends(require_auth)):
    """List video recordings for the authenticated user."""
    _ensure_tables()
    user_id = user.get("sub", "")
    report_id = request.query_params.get("report_id")

    conn = get_db_connection()
    if not conn:
        return {"success": True, "videos": []}

    try:
        cursor = conn.cursor()
        if report_id:
            # IDOR protection: non-admin can only see their own videos by report_id
            if user.get("role") == "admin":
                cursor.execute(
                    "SELECT * FROM video_recordings WHERE report_id = ? ORDER BY started_at DESC",
                    (report_id,),
                )
            else:
                cursor.execute(
                    "SELECT * FROM video_recordings WHERE report_id = ? AND created_by = ? ORDER BY started_at DESC",
                    (report_id, user_id),
                )
        elif user.get("role") == "admin":
            cursor.execute(
                "SELECT * FROM video_recordings ORDER BY started_at DESC LIMIT 100"
            )
        else:
            cursor.execute(
                "SELECT * FROM video_recordings WHERE created_by = ? ORDER BY started_at DESC LIMIT 100",
                (user_id,),
            )
        columns = [desc[0] for desc in cursor.description]
        videos = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as e:
        logger.error("Failed to list videos: %s", e)
        videos = []
    finally:
        conn.close()

    return {"success": True, "videos": videos}
