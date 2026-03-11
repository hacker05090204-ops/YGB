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
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List

from fastapi import APIRouter, Request, HTTPException, Depends

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.auth.auth_guard import require_auth

logger = logging.getLogger("ygb.report_generator")


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
    except Exception:
        logger.info("AUDIT [%s] %s: %s", user_id, action, detail)

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
        "metadata_json": json.dumps(body.get("metadata", {})),
    }

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=503, detail={
            "error": "SERVICE_UNAVAILABLE", "detail": "Database unavailable"
        })

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
    except Exception:
        pass

    _log_activity(user_id, "REPORT_CREATED", f"Report '{title}' created ({report_id})")
    logger.info("Report created: %s by %s", report_id, user_id)

    return {"success": True, "report": {**report, "content": body.get("content", {})}}


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
        reports = [dict(zip(columns, row)) for row in cursor.fetchall()]
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
        raise HTTPException(status_code=503, detail={
            "error": "SERVICE_UNAVAILABLE", "detail": "Database unavailable"
        })

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
        raise HTTPException(status_code=503, detail={
            "error": "SERVICE_UNAVAILABLE", "detail": "Database unavailable"
        })

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
        raise HTTPException(status_code=503, detail={
            "error": "SERVICE_UNAVAILABLE", "detail": "Database unavailable"
        })

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
        raise HTTPException(status_code=503, detail={
            "error": "SERVICE_UNAVAILABLE", "detail": "Database unavailable"
        })

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
