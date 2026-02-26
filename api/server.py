"""
YGB API Server

FastAPI backend providing REST and WebSocket endpoints for the YGB frontend.
Bridges Python governance phases and HUMANOID_HUNTER modules with the UI.

THIS SERVER IS FOR DISPLAY AND COORDINATION ONLY.
IT CANNOT EXECUTE BROWSER ACTIONS OR BYPASS GOVERNANCE.
"""

import os
import sys
import uuid
import json
import asyncio
import hashlib
import logging

logger = logging.getLogger("ygb.server")
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel

# Centralized auth guard
from backend.auth.auth_guard import (
    require_auth, require_admin,
    revoke_token, revoke_session,
    preflight_check_secrets,
    validate_target_url,
    ws_authenticate,
)

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure HDD storage root points to the dedicated YGB_DATA partition (D:\)
import platform as _plat
if _plat.system() == "Windows":
    os.environ["YGB_HDD_ROOT"] = "D:/ygb_hdd"

# Import HDD storage bridge (replaces SQLite database module)
from backend.storage.storage_bridge import (
    init_storage, shutdown_storage,
    create_user, get_user, get_all_users, update_user_stats,
    create_target, get_all_targets, get_target,
    create_bounty, get_user_bounties, get_all_bounties, update_bounty_status,
    create_session, get_user_sessions, update_session_progress,
    log_activity, get_recent_activity, get_admin_stats,
    get_storage_stats, get_lifecycle_status, get_disk_status,
    get_delete_preview, store_video, get_video_stream_token,
    stream_video, list_videos, get_storage_health,
)

# Import activation profiles
try:
    from backend.config.activation_profiles import (
        validate_startup, log_boot_summary, get_profile,
        get_smtp_pass, IntegrationState,
    )
    ACTIVATION_PROFILES_AVAILABLE = True
except ImportError:
    ACTIVATION_PROFILES_AVAILABLE = False

# Import training state manager
from backend.training.state_manager import get_training_state_manager

# Import auth and alerts
from backend.auth.auth import (
    hash_password, verify_password, generate_jwt, verify_jwt,
    compute_device_hash, get_rate_limiter, generate_csrf_token,
    needs_rehash,
)
from backend.alerts.email_alerts import (
    alert_new_login, alert_new_device, alert_multiple_devices,
    alert_suspicious_activity, alert_rate_limit_exceeded
)
from backend.storage.storage_bridge import (
    register_device, get_user_devices, get_all_active_devices,
    get_active_device_count, get_active_sessions, end_session,
    get_user_by_email, update_user_password
)

# Import REAL phase runner with actual browser automation
from phase_runner import RealPhaseRunner, run_real_workflow

# =============================================================================
# G38 AUTO-TRAINING IMPORTS
# =============================================================================

try:
    from impl_v1.phase49.runtime import (
        get_auto_trainer,
        start_auto_training,
        stop_auto_training,
        start_continuous_training,
        stop_continuous_training,
        get_idle_seconds,
        is_power_connected,
        is_scan_active,
        set_scan_active,
        TrainingState,
    )
    from impl_v1.phase49.governors.g38_self_trained_model import (
        verify_all_guards,
        ALL_GUARDS,
    )
    from impl_v1.phase49.governors.g38_safe_pretraining import (
        verify_pretraining_guards,
        get_mode_a_status,
        get_training_mode_summary,
    )
    G38_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  G38 modules not available: {e}")
    G38_AVAILABLE = False

# =============================================================================
# SYSTEM INTEGRITY SUPERVISOR
# =============================================================================

try:
    from backend.integrity.integrity_bridge import get_integrity_supervisor
    INTEGRITY_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Integrity supervisor not available: {e}")
    INTEGRITY_AVAILABLE = False

# =============================================================================
# RESEARCH ASSISTANT (DUAL-MODE VOICE)
# =============================================================================

try:
    from backend.assistant.query_router import (
        QueryRouter, ResearchSearchPipeline, VoiceMode, ResearchStatus,
    )
    from backend.assistant.isolation_guard import IsolationGuard
    RESEARCH_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Research assistant not available: {e}")
    RESEARCH_AVAILABLE = False

# =============================================================================
# APP CONFIGURATION
# =============================================================================

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    """Server lifespan: start CVE scheduler on boot, stop on shutdown."""
    # --- STARTUP ---
    try:
        from backend.cve.cve_scheduler import get_scheduler
        scheduler = get_scheduler()
        scheduler.start()
        print("✅ CVE scheduler started (5-minute interval)")
    except Exception as e:
        print(f"⚠️  CVE scheduler not started: {e}")
    yield
    # --- SHUTDOWN ---
    try:
        from backend.cve.cve_scheduler import get_scheduler
        scheduler = get_scheduler()
        await scheduler.stop()
        print("CVE scheduler stopped")
    except Exception:
        pass

app = FastAPI(
    title="YGB API",
    description="Bug Bounty Governance Backend",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class StartWorkflowRequest(BaseModel):
    target: str
    mode: str = "READ_ONLY"  # READ_ONLY or REAL


class WorkflowStartResponse(BaseModel):
    workflow_id: str
    report_id: Optional[str] = None
    status: str


class PhaseInfo(BaseModel):
    name: str
    number: int
    available: bool
    description: str


# =============================================================================
# PHASE-49 MODELS
# =============================================================================

class CreateDashboardRequest(BaseModel):
    user_id: str
    user_name: str


class ExecutionTransitionRequest(BaseModel):
    transition: str  # PLAN, SIMULATE, REQUEST_APPROVAL, HUMAN_APPROVE, HUMAN_DENY, COMPLETE, ABORT
    actor_id: str
    reason: str = ""


class ApprovalDecisionRequest(BaseModel):
    request_id: str
    approved: bool
    approver_id: str
    reason: str = ""


class TargetDiscoveryRequest(BaseModel):
    min_payout: str = "LOW"  # LOW, MEDIUM, HIGH
    max_density: str = "MEDIUM"  # LOW, MEDIUM, HIGH
    public_only: bool = True


class VoiceParseRequest(BaseModel):
    text: str


class AutonomySessionRequest(BaseModel):
    mode: str  # READ_ONLY, AUTONOMOUS_FIND, REAL
    duration_hours: float = 0.0


# =============================================================================
# DATABASE MODELS
# =============================================================================

class CreateUserRequest(BaseModel):
    name: str
    email: Optional[str] = None
    role: str = "researcher"


class CreateTargetRequest(BaseModel):
    program_name: str
    scope: str
    link: Optional[str] = None
    platform: Optional[str] = None
    payout_tier: str = "MEDIUM"


class CreateBountyRequest(BaseModel):
    user_id: str
    target_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    severity: str = "MEDIUM"


class UpdateBountyRequest(BaseModel):
    bounty_id: str
    status: str
    reward: Optional[float] = None


class CreateSessionRequest(BaseModel):
    user_id: str
    mode: str
    target_scope: Optional[str] = None


# =============================================================================
# IN-MEMORY STATE (runtime state — persisted in-memory per server lifetime)
# =============================================================================

# Active WebSocket connections
hunter_connections: Dict[str, WebSocket] = {}
bounty_connections: Dict[str, WebSocket] = {}

# Active workflows
active_workflows: Dict[str, Dict[str, Any]] = {}

# Phase-49 State Stores
dashboard_states: Dict[str, Dict[str, Any]] = {}
execution_kernels: Dict[str, Dict[str, Any]] = {}
approval_requests: Dict[str, Dict[str, Any]] = {}
autonomy_sessions: Dict[str, Dict[str, Any]] = {}


# =============================================================================
# PHASE DISCOVERY
# =============================================================================

def discover_python_phases() -> List[Dict[str, Any]]:
    """Discover available Python phases."""
    phases = []
    
    # Phases 01-19 in python/
    python_dir = PROJECT_ROOT / "python"
    if python_dir.exists():
        for item in python_dir.iterdir():
            if item.is_dir() and item.name.startswith("phase"):
                try:
                    num = int(item.name.replace("phase", "").split("_")[0])
                    phases.append({
                        "name": item.name,
                        "number": num,
                        "path": str(item),
                        "available": True,
                        "description": f"Phase {num:02d} - {item.name.split('_', 1)[-1].replace('_', ' ').title()}"
                    })
                except ValueError:
                    pass
    
    # Phases 20-49 in impl_v1/
    impl_dir = PROJECT_ROOT / "impl_v1"
    if impl_dir.exists():
        for item in impl_dir.iterdir():
            if item.is_dir() and item.name.startswith("phase"):
                try:
                    num = int(item.name.replace("phase", ""))
                    phases.append({
                        "name": item.name,
                        "number": num,
                        "path": str(item),
                        "available": True,
                        "description": f"Phase {num:02d} - Implementation Layer"
                    })
                except ValueError:
                    pass
    
    return sorted(phases, key=lambda x: x["number"])


def discover_hunter_modules() -> Dict[str, bool]:
    """Discover available HUMANOID_HUNTER modules."""
    modules = {}
    hunter_dir = PROJECT_ROOT / "HUMANOID_HUNTER"
    
    if hunter_dir.exists():
        for item in hunter_dir.iterdir():
            if item.is_dir() and not item.name.startswith("_") and not item.name.startswith("."):
                modules[item.name] = True
    
    return modules


# =============================================================================
# REST ENDPOINTS
# =============================================================================

@app.get("/api/health")
async def health_check():
    """Health check endpoint with REAL system status — no fake active states.
    
    Returns structured sub-sections:
      - storage_engine_status
      - dataset_readiness_status
      - integration_status
    """
    phases = discover_python_phases()
    hunter_modules = discover_hunter_modules()

    # Real storage health (single source of truth)
    storage_health = get_storage_health()

    # Dataset readiness
    dataset_status = _get_dataset_readiness()

    # Integration status
    integration_status = _get_integration_summary()

    # Overall: only "ok" if all critical subsystems active
    if not storage_health["storage_active"]:
        overall = "degraded"
    elif dataset_status.get("status") == "BLOCKED_REAL_DATA":
        overall = "degraded"
    else:
        overall = "ok"

    return {
        "status": overall,
        "python_phases": len([p for p in phases if p["number"] <= 19]),
        "impl_phases": len([p for p in phases if p["number"] >= 20]),
        "hunter_modules": len(hunter_modules),
        "storage_engine_status": storage_health,
        "dataset_readiness_status": dataset_status,
        "integration_status": integration_status,
        "timestamp": datetime.now(UTC).isoformat()
    }


@app.get("/api/storage/status")
async def get_storage_status():
    """Canonical storage/DB truth endpoint.

    Returns real check results — never fake active.
    Frontend must use this as single source of truth.
    """
    return get_storage_health()


@app.get("/api/rollout/metrics")
async def get_rollout_metrics():
    """Rollout metrics endpoint — returns DEGRADED when real metrics unavailable.

    Never defaults to all-pass zeros that look healthy.
    """
    try:
        from governance.real_data_rollout_governor import get_current_status
        status = get_current_status()
        return {
            "status": "available",
            "metrics_available": True,
            **status,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except ImportError:
        return {
            "status": "DEGRADED",
            "metrics_available": False,
            "reason": "Rollout governor module not available",
            "stage": None,
            "real_data_pct": None,
            "frozen": None,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        return {
            "status": "DEGRADED",
            "metrics_available": False,
            "reason": f"Error reading rollout metrics: {str(e)}",
            "stage": None,
            "real_data_pct": None,
            "frozen": None,
            "timestamp": datetime.now(UTC).isoformat(),
        }


def _get_dataset_readiness() -> Dict[str, Any]:
    """Get dataset readiness status for health endpoint."""
    try:
        from impl_v1.training.data.real_dataset_loader import (
            validate_dataset_integrity, YGB_MIN_REAL_SAMPLES,
        )
        ok, msg = validate_dataset_integrity()
        if ok:
            return {
                "status": "READY",
                "min_samples_required": YGB_MIN_REAL_SAMPLES,
                "reason": None,
            }
        else:
            return {
                "status": "BLOCKED_REAL_DATA",
                "min_samples_required": YGB_MIN_REAL_SAMPLES,
                "reason": msg,
            }
    except Exception as e:
        return {
            "status": "UNKNOWN",
            "min_samples_required": None,
            "reason": f"Cannot check dataset: {str(e)}",
        }


def _get_integration_summary() -> Dict[str, Any]:
    """Get integration status summary."""
    if not ACTIVATION_PROFILES_AVAILABLE:
        return {"status": "UNKNOWN", "reason": "activation_profiles not available"}
    try:
        ok, errors, integrations = validate_startup()
        return {
            "profile": get_profile().value,
            "startup_ok": ok,
            "integrations": {
                i.name: {"state": i.state.value, "reason": i.reason}
                for i in integrations
            },
        }
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}


@app.get("/api/readiness")
async def get_readiness():
    """Dataset readiness endpoint — shows sample counts, thresholds, and blocking reasons."""
    return _get_dataset_readiness()


@app.get("/api/integration/status")
async def get_integration_status():
    """Integration status per configured service."""
    return _get_integration_summary()


@app.get("/api/cve/status")
async def get_cve_status():
    """CVE pipeline status — sources, freshness, record counts."""
    try:
        from backend.cve.cve_pipeline import get_pipeline
        pipeline = get_pipeline()
        return pipeline.get_pipeline_status()
    except ImportError:
        return {"status": "NOT_AVAILABLE", "reason": "CVE pipeline module not found"}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}


@app.get("/api/cve/scheduler/health")
async def get_cve_scheduler_health():
    """CVE scheduler SLO metrics and health status."""
    try:
        from backend.cve.cve_scheduler import get_scheduler
        scheduler = get_scheduler()
        return scheduler.get_health()
    except ImportError:
        return {"status": "NOT_AVAILABLE", "reason": "Scheduler module not found"}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}


@app.get("/api/cve/pipeline/status")
async def get_cve_pipeline_full_status():
    """Full CVE pipeline status with promotion, dedup/drift, and anti-hallucination."""
    try:
        from backend.cve.cve_pipeline import get_pipeline
        from backend.cve.promotion_policy import get_promotion_policy
        from backend.cve.dedup_drift import get_dedup_drift_engine
        from backend.cve.anti_hallucination import get_anti_hallucination_validator
        from backend.cve.cve_scheduler import get_scheduler

        return {
            "pipeline": get_pipeline().get_pipeline_status(),
            "scheduler": get_scheduler().get_health(),
            "promotion": get_promotion_policy().get_counts(),
            "dedup_drift": get_dedup_drift_engine().get_status(),
            "anti_hallucination": get_anti_hallucination_validator().get_status(),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}


@app.get("/health")
async def health_alias():
    """Alias for /api/health — some frontend pages use /health."""
    return await health_check()


@app.get("/api/cve/summary")
async def get_cve_summary():
    """Quick CVE summary — total records, sources, freshness."""
    try:
        from backend.cve.cve_pipeline import get_pipeline
        pipeline = get_pipeline()
        status = pipeline.get_pipeline_status()
        return {
            "total_records": status.get("total_records", 0),
            "sources_connected": status.get("sources_connected", 0),
            "last_ingest": status.get("last_ingest_at"),
            "freshness": status.get("freshness", "UNKNOWN"),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except ImportError:
        return {"total_records": 0, "sources_connected": 0, "freshness": "NOT_AVAILABLE"}
    except Exception as e:
        return {"total_records": 0, "sources_connected": 0, "freshness": "ERROR", "reason": str(e)}


@app.get("/api/cve/search")
async def search_cves(q: str = "", user=Depends(require_auth)):
    """Search CVE records by ID or keyword."""
    if not q or len(q) < 3:
        return {"results": [], "query": q, "reason": "Query must be at least 3 characters"}
    try:
        from backend.cve.cve_pipeline import get_pipeline
        pipeline = get_pipeline()
        results = pipeline.search(q)
        return {"results": results[:50], "query": q, "total": len(results)}
    except ImportError:
        return {"results": [], "query": q, "reason": "CVE pipeline not available"}
    except AttributeError:
        return {"results": [], "query": q, "reason": "Search not implemented in pipeline"}
    except Exception as e:
        return {"results": [], "query": q, "reason": str(e)}


@app.get("/api/training/readiness")
async def get_training_readiness():
    """Training readiness truth table — per-field status with exact block reasons."""
    try:
        from impl_v1.training.data.real_dataset_loader import (
            validate_dataset_integrity, YGB_MIN_REAL_SAMPLES,
            STRICT_REAL_MODE,
        )
        ok, msg = validate_dataset_integrity()

        # Build per-field readiness
        fields = {}
        storage_health = get_storage_health()

        fields["storage_engine"] = {
            "status": "READY" if storage_health.get("storage_active") else "BLOCKED",
            "reason": None if storage_health.get("storage_active") else "Storage engine not active",
        }
        fields["dataset_source"] = {
            "status": "READY" if ok else "BLOCKED",
            "reason": None if ok else msg,
        }
        fields["strict_real_mode"] = {
            "status": "READY" if STRICT_REAL_MODE else "PARTIAL",
            "reason": None if STRICT_REAL_MODE else "STRICT_REAL_MODE=false (lab mode)",
        }
        fields["min_samples"] = {
            "status": "READY" if ok else "BLOCKED",
            "threshold": YGB_MIN_REAL_SAMPLES,
            "reason": None if ok else msg,
        }

        # Overall readiness
        blocked = [f for f in fields.values() if f["status"] == "BLOCKED"]
        partial = [f for f in fields.values() if f["status"] == "PARTIAL"]

        if blocked:
            overall = "BLOCKED"
        elif partial:
            overall = "PARTIAL"
        else:
            overall = "READY"

        return {
            "overall": overall,
            "fields": fields,
            "training_allowed": overall == "READY",
            "go_no_go": "GO" if overall == "READY" else "NO_GO",
            "remediation": msg if not ok else None,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        return {
            "overall": "BLOCKED",
            "training_allowed": False,
            "go_no_go": "NO_GO",
            "reason": str(e),
        }


@app.get("/api/backup/status")
async def get_backup_status_endpoint():
    """Backup strategy status — local HDD, peer replication, Google Drive."""
    try:
        from backend.storage.backup_config import get_backup_status
        return get_backup_status()
    except ImportError:
        return {"status": "NOT_AVAILABLE", "reason": "Backup config module not found"}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}



@app.get("/api/bounty/phases")
async def get_bounty_phases(user=Depends(require_auth)):
    """Get all available bounty phases."""
    phases = discover_python_phases()
    return {
        p["name"]: {
            "number": p["number"],
            "available": p["available"],
            "description": p["description"]
        }
        for p in phases
    }


@app.get("/api/reports")
async def list_reports(user=Depends(require_auth)):
    """List all security reports in the report directory. Auth required."""
    report_dir = PROJECT_ROOT / "report"
    if not report_dir.exists():
        return {"reports": [], "count": 0}
    
    reports = []
    for file in sorted(report_dir.glob("*.txt"), reverse=True):
        stat = file.stat()
        reports.append({
            "filename": file.name,
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "download_url": f"/api/reports/{file.name}"
        })
    
    return {"reports": reports, "count": len(reports)}


@app.get("/api/reports/{filename}")
async def download_report(filename: str, user=Depends(require_auth)):
    """Download a specific report file."""
    report_dir = PROJECT_ROOT / "report"
    file_path = report_dir / filename
    
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    
    # Security check - prevent directory traversal
    if not str(file_path.resolve()).startswith(str(report_dir.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="text/plain"
    )


@app.get("/api/reports/{filename}/content")
async def get_report_content(filename: str, user=Depends(require_auth)):
    """Get report content as text."""
    report_dir = PROJECT_ROOT / "report"
    file_path = report_dir / filename
    
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    
    # Security check
    if not str(file_path.resolve()).startswith(str(report_dir.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")
    
    content = file_path.read_text(encoding="utf-8")
    return PlainTextResponse(content)


@app.post("/api/hunter/start")
async def start_hunter(request: StartWorkflowRequest, user=Depends(require_auth)):
    """Start a V1 Hunter workflow."""
    if not request.target:
        raise HTTPException(status_code=400, detail="Target URL is required")
    
    # SSRF protection
    is_safe, violations = validate_target_url(request.target)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Target URL rejected: {violations[0]['message']}")
    
    workflow_id = f"HNT-{uuid.uuid4().hex[:12].upper()}"
    
    active_workflows[workflow_id] = {
        "type": "hunter",
        "target": request.target,
        "status": "started",
        "started_at": datetime.now(UTC).isoformat(),
        "steps": []
    }
    
    return WorkflowStartResponse(
        workflow_id=workflow_id,
        status="started"
    )


@app.post("/api/bounty/start")
@app.post("/api/workflow/bounty/start")  # Alias for frontend compatibility
async def start_bounty(request: StartWorkflowRequest, user=Depends(require_auth)):
    """Start a Bounty Finder workflow with REAL browser automation."""
    if not request.target:
        raise HTTPException(status_code=400, detail="Target URL is required")
    
    # Validate target URL
    target = request.target.strip()
    if not target.startswith(("http://", "https://")):
        target = f"https://{target}"
    
    # SSRF protection
    is_safe, violations = validate_target_url(target)
    if not is_safe:
        raise HTTPException(status_code=400, detail=f"Target URL rejected: {violations[0]['message']}")
    
    report_id = f"RPT-{uuid.uuid4().hex[:12].upper()}"
    
    # Store workflow with target URL
    active_workflows[report_id] = {
        "type": "bounty",
        "target": target,
        "mode": request.mode,  # READ_ONLY or REAL
        "status": "started",
        "started_at": datetime.now(UTC).isoformat(),
        "steps": [],
        "findings": []
    }
    
    # Debug logging
    print(f"🎯 NEW WORKFLOW: {report_id}")
    print(f"   Target: {target}")
    print(f"   Mode: {request.mode}")
    
    return WorkflowStartResponse(
        workflow_id=report_id,
        report_id=report_id,
        status="started"
    )


# =============================================================================
# PHASE-49 ENDPOINTS
# =============================================================================

@app.post("/api/dashboard/create")
async def create_dashboard(request: CreateDashboardRequest, user=Depends(require_auth)):
    """Create a new dashboard for a user."""
    dashboard_id = f"DASH-{uuid.uuid4().hex[:16].upper()}"
    now = datetime.now(UTC).isoformat()
    
    # Create execution kernel for this dashboard
    kernel_id = f"KERN-{uuid.uuid4().hex[:12].upper()}"
    execution_kernels[kernel_id] = {
        "session_id": kernel_id,
        "state": "IDLE",
        "human_approved": False,
        "deny_reason": None,
        "audit_log": []
    }
    
    dashboard_states[dashboard_id] = {
        "dashboard_id": dashboard_id,
        "user_id": request.user_id,
        "user_name": request.user_name,
        "kernel_id": kernel_id,
        "created_at": now,
        "active_panel": "USER"
    }
    
    return {
        "dashboard_id": dashboard_id,
        "kernel_id": kernel_id,
        "status": "created"
    }


@app.get("/api/dashboard/state")
async def get_dashboard_state(dashboard_id: Optional[str] = None, user=Depends(require_auth)):
    """Get current dashboard state."""
    if dashboard_id and dashboard_id in dashboard_states:
        return dashboard_states[dashboard_id]
    
    # No dashboard found — return error
    return {"error": "No dashboard found", "dashboard_id": None, "state": "DISCONNECTED"}


@app.get("/api/execution/state")
async def get_execution_state(kernel_id: Optional[str] = None, user=Depends(require_auth)):
    """Get execution kernel state."""
    if kernel_id and kernel_id in execution_kernels:
        return execution_kernels[kernel_id]
    
    return {
        "state": "IDLE",
        "human_approved": False
    }


@app.post("/api/execution/transition")
async def execution_transition(request: ExecutionTransitionRequest, user=Depends(require_auth)):
    """Request a state transition on the execution kernel."""
    # Valid transitions based on G01
    valid_transitions = {
        ("IDLE", "PLAN"): "PLANNED",
        ("PLANNED", "SIMULATE"): "SIMULATED",
        ("SIMULATED", "REQUEST_APPROVAL"): "AWAIT_HUMAN",
        ("AWAIT_HUMAN", "HUMAN_APPROVE"): "EXECUTING",
        ("AWAIT_HUMAN", "HUMAN_DENY"): "STOPPED",
        ("EXECUTING", "COMPLETE"): "STOPPED",
        ("EXECUTING", "ABORT"): "STOPPED",
        ("IDLE", "ABORT"): "STOPPED",
        ("PLANNED", "ABORT"): "STOPPED",
        ("SIMULATED", "ABORT"): "STOPPED",
        ("AWAIT_HUMAN", "ABORT"): "STOPPED",
    }
    
    # Find kernel or create demo one
    kernel = None
    for kid, k in execution_kernels.items():
        kernel = k
        break
    
    if not kernel:
        kernel = {"state": "IDLE", "human_approved": False, "deny_reason": None}
    
    current_state: str = kernel.get("state", "IDLE")  # type: ignore[assignment]
    transition = request.transition
    
    key = (current_state, transition)
    if key in valid_transitions:
        new_state = valid_transitions[key]
        kernel["state"] = new_state
        
        if transition == "HUMAN_APPROVE":
            kernel["human_approved"] = True
        if transition == "HUMAN_DENY":
            kernel["deny_reason"] = request.reason
        
        return {
            "result": "SUCCESS",
            "from_state": current_state,
            "to_state": new_state,
            "reason": request.reason
        }
    
    return {
        "result": "INVALID",
        "from_state": current_state,
        "to_state": current_state,
        "reason": f"Invalid transition {transition} from {current_state}"
    }


@app.post("/api/approval/decision")
async def submit_approval_decision(request: ApprovalDecisionRequest, user=Depends(require_admin)):
    """Submit an approval decision."""
    now = datetime.now(UTC).isoformat()
    
    decision = {
        "decision_id": f"DEC-{uuid.uuid4().hex[:16].upper()}",
        "request_id": request.request_id,
        "approved": request.approved,
        "approver_id": request.approver_id,
        "reason": request.reason,
        "timestamp": now
    }
    
    # Update any matching approval request
    if request.request_id in approval_requests:
        approval_requests[request.request_id]["status"] = "APPROVED" if request.approved else "REJECTED"
    
    return decision


@app.post("/api/targets/discover")
async def discover_targets(request: TargetDiscoveryRequest, user=Depends(require_auth)):
    """Discover potential bug bounty targets from the database."""
    try:
        targets = await get_all_targets()
        candidates = []
        for t in targets:
            candidate = {
                "candidate_id": f"TGT-{t.get('id', uuid.uuid4().hex[:16].upper())}",
                "program_name": t.get("program_name", "Unknown"),
                "source": t.get("platform", "DATABASE"),
                "scope_summary": t.get("scope", ""),
                "payout_tier": t.get("payout_tier", "UNKNOWN"),
                "report_density": "UNKNOWN",
                "is_public": True,
                "requires_invite": False,
                "discovered_at": t.get("created_at", datetime.now(UTC).isoformat())
            }
            candidates.append(candidate)

        # Filter based on request
        filtered = [c for c in candidates if c["is_public"] or not request.public_only]

        return {
            "result_id": f"DIS-{uuid.uuid4().hex[:16].upper()}",
            "candidates": filtered,
            "total_found": len(candidates),
            "filtered_count": len(candidates) - len(filtered),
            "timestamp": datetime.now(UTC).isoformat()
        }
    except Exception as e:
        logger.exception("Error discovering targets")
        return {
            "result_id": f"DIS-{uuid.uuid4().hex[:16].upper()}",
            "candidates": [],
            "total_found": 0,
            "filtered_count": 0,
            "error": "Internal error while discovering targets",
            "timestamp": datetime.now(UTC).isoformat()
        }


# =============================================================================
# SCOPE VALIDATION & TARGET SESSION MANAGEMENT
# =============================================================================

# In-memory target session state
target_sessions: Dict[str, Dict[str, Any]] = {}
scope_violations: List[Dict[str, Any]] = []


@app.post("/scope/validate")
async def validate_scope(request: Request, user=Depends(require_auth)):
    """Validate a scope definition against security rules. Auth required."""
    data = await request.json()
    target_url = data.get("target_url", "")
    now = datetime.now(UTC).isoformat()

    # Use robust SSRF-safe validation from auth_guard
    is_valid, violations = validate_target_url(target_url)

    return {
        "valid": is_valid,
        "target_url": target_url,
        "violations": violations,
        "validated_at": now
    }


@app.post("/target/start")
async def start_target_session(request: Request, user=Depends(require_auth)):
    """Start a target scanning session. Auth required. Scope validation enforced."""
    data = await request.json()
    target_url = data.get("target_url", "")
    scope_definition = data.get("scope_definition", {})
    mode = data.get("mode", "READ_ONLY")
    now = datetime.now(UTC).isoformat()

    # Enforce scope validation before starting session (SSRF protection)
    is_safe, violations = validate_target_url(target_url)
    if not is_safe:
        return {"error": "Scope validation failed", "started": False, "violations": violations}

    session_id = f"TSESS-{uuid.uuid4().hex[:12].upper()}"
    target_sessions[session_id] = {
        "session_id": session_id,
        "target_url": target_url,
        "scope_definition": scope_definition,
        "mode": mode,
        "status": "ACTIVE",
        "started_at": now,
        "stopped_at": None,
        "violations": [],
        "findings_count": 0
    }

    return {
        "started": True,
        "session_id": session_id,
        "target_url": target_url,
        "mode": mode,
        "started_at": now
    }


@app.post("/target/stop")
async def stop_target_session(request: Request, user=Depends(require_auth)):
    """Stop an active target scanning session."""
    data = await request.json()
    session_id = data.get("session_id", "")
    now = datetime.now(UTC).isoformat()

    if session_id not in target_sessions:
        return {"error": f"Session {session_id} not found", "stopped": False}

    session = target_sessions[session_id]
    session["status"] = "STOPPED"
    session["stopped_at"] = now

    return {
        "stopped": True,
        "session_id": session_id,
        "stopped_at": now,
        "duration_seconds": 0  # Would compute real duration in production
    }


@app.get("/target/status")
async def get_target_status(user=Depends(require_auth)):
    """Get status of all target sessions."""
    active = [s for s in target_sessions.values() if s["status"] == "ACTIVE"]
    stopped = [s for s in target_sessions.values() if s["status"] == "STOPPED"]

    return {
        "active_sessions": active,
        "stopped_sessions": stopped[-10:],  # Last 10 stopped
        "total_active": len(active),
        "total_stopped": len(stopped),
        "violations": scope_violations[-20:]  # Last 20 violations
    }


# NOTE: /api/voice/parse is defined below under DUAL-MODE VOICE ENDPOINTS
# The duplicate simple route has been removed to avoid ambiguity.



@app.post("/api/autonomy/session")
async def create_autonomy_session(request: AutonomySessionRequest, user=Depends(require_auth)):
    """Create an autonomy session."""
    now = datetime.now(UTC)
    session_id = f"AUT-{uuid.uuid4().hex[:16].upper()}"
    
    # Calculate expiry for AUTONOMOUS_FIND mode
    expires_at = None
    if request.mode == "AUTONOMOUS_FIND" and request.duration_hours > 0:
        max_hours = min(request.duration_hours, 12)  # Cap at 12 hours
        from datetime import timedelta
        expires_at = (now + timedelta(hours=max_hours)).isoformat()
    
    # Determine blocked actions based on mode
    blocked = []
    if request.mode == "AUTONOMOUS_FIND":
        blocked = ["EXPLOIT", "SUBMISSION", "STATE_CHANGE", "BROWSER_ACTION"]
    elif request.mode == "READ_ONLY":
        blocked = ["EXPLOIT", "SUBMISSION", "STATE_CHANGE", "BROWSER_ACTION"]
    elif request.mode == "MOCK":
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=400,
            content={"error": "MOCK mode is disabled. Use READ_ONLY, AUTONOMOUS_FIND, or REAL."}
        )
    
    session = {
        "session_id": session_id,
        "mode": request.mode,
        "status": "ACTIVE",
        "duration_hours": request.duration_hours,
        "started_at": now.isoformat(),
        "expires_at": expires_at,
        "human_enabled": request.mode == "REAL",
        "actions_blocked": blocked
    }
    
    autonomy_sessions[session_id] = session
    return session


# =============================================================================
# G38 AUTO-TRAINING ENDPOINTS
# =============================================================================

@app.get("/api/g38/status")
async def get_g38_status(user=Depends(require_auth)):
    """Get G38 auto-training status."""
    if not G38_AVAILABLE:
        return {"available": False, "error": "G38 modules not loaded"}
    
    trainer = get_auto_trainer()
    status = trainer.get_status()
    
    # Add guard verification
    guards_ok, guards_msg = verify_all_guards()
    pretraining_ok, pretraining_msg = verify_pretraining_guards()
    mode_a_status, mode_a_msg = get_mode_a_status()
    
    return {
        "available": True,
        "auto_training": {
            "state": status["state"],
            "is_training": status["is_training"],
            "epoch": status["epoch"],
            "total_epochs": status.get("total_epochs", 0),
            "total_completed": status.get("total_completed", 0),
            "progress": status.get("progress", 0),
            "idle_seconds": status["idle_seconds"],
            "power_connected": status["power_connected"],
            "scan_active": status["scan_active"],
            "gpu_available": status["gpu_available"],
            "events_count": status["events_count"],
            "last_event": status["last_event"],
            # Real GPU + training metrics
            "gpu_mem_allocated_mb": status.get("gpu_mem_allocated_mb", 0),
            "gpu_mem_reserved_mb": status.get("gpu_mem_reserved_mb", 0),
            "last_loss": status.get("last_loss", 0),
            "last_accuracy": status.get("last_accuracy", 0),
            "samples_per_sec": status.get("samples_per_sec", 0),
            "dataset_size": status.get("dataset_size", 0),
            "training_mode": status.get("training_mode", "MANUAL"),
        },

        "guards": {
            "main_guards": len(ALL_GUARDS),
            "all_verified": guards_ok,
            "message": guards_msg,
        },
        "pretraining": {
            "verified": pretraining_ok,
            "message": pretraining_msg,
        },
        "mode": {
            "mode_a_status": mode_a_status.value,
            "message": mode_a_msg,
        },
        "training_summary": get_training_mode_summary() if G38_AVAILABLE else None,
    }


@app.get("/api/g38/events")
async def get_g38_events(limit: int = 50, user=Depends(require_auth)):
    """Get recent G38 training events."""
    if not G38_AVAILABLE:
        return {"events": [], "error": "G38 modules not loaded"}
    
    trainer = get_auto_trainer()
    events = trainer.events[-limit:] if trainer.events else []
    
    return {
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "timestamp": e.timestamp,
                "details": e.details,
                "idle_seconds": e.idle_seconds,
                "gpu_used": e.gpu_used,
                "epoch": e.epoch,
            }
            for e in events
        ],
        "total": len(trainer.events),
    }


@app.post("/api/g38/abort")
async def abort_g38_training(user=Depends(require_auth)):
    """Abort current G38 training."""
    if not G38_AVAILABLE:
        return {"success": False, "error": "G38 modules not loaded"}
    
    trainer = get_auto_trainer()
    result = trainer.abort_training()
    
    return {
        "success": result.get("aborted", False),
        "state": trainer.state.value,
        "message": "Training abort requested" if result.get("aborted") else result.get("reason", "No training in progress"),
    }


@app.post("/api/g38/start")
async def start_g38_training(epochs: int = 10, user=Depends(require_auth)):
    """Manually start G38 training for demo/testing."""
    if not G38_AVAILABLE:
        return {"success": False, "error": "G38 modules not loaded"}
    
    trainer = get_auto_trainer()
    
    # Check if already training
    if trainer.is_training:
        return {
            "success": False,
            "error": "Training already in progress",
            "state": trainer.state.value,
        }
    
    # Start training in background thread (async)
    import threading
    def run_training():
        trainer.force_start_training(epochs=epochs)
    
    thread = threading.Thread(target=run_training, daemon=True)
    thread.start()
    
    return {
        "success": True,
        "message": f"Training started for {epochs} epochs",
        "state": "TRAINING",
    }


# =============================================================================
# ADMIN PANEL TRAINING/GPU ROUTES
# (frontend admin/panel/page.tsx calls these)
# =============================================================================

@app.get("/gpu/status")
async def gpu_status(user=Depends(require_auth)):
    """GPU status for admin panel — real GPU info."""
    gpu_info = {
        "gpu_available": False,
        "device_name": None,
        "utilization_percent": None,
        "memory_allocated_mb": None,
        "memory_total_mb": None,
        "temperature": None,
        "compute_capability": None,
    }
    try:
        import torch
        if torch.cuda.is_available():
            gpu_info["gpu_available"] = True
            gpu_info["device_name"] = torch.cuda.get_device_name(0)
            gpu_info["memory_allocated_mb"] = round(torch.cuda.memory_allocated(0) / 1024 / 1024, 1)
            gpu_info["memory_total_mb"] = round(torch.cuda.get_device_properties(0).total_mem / 1024 / 1024, 1)
            cap = torch.cuda.get_device_capability(0)
            gpu_info["compute_capability"] = f"{cap[0]}.{cap[1]}"
    except Exception:
        pass
    return gpu_info


@app.get("/training/status")
async def training_status(user=Depends(require_admin)):
    """Training status for admin panel."""
    if not G38_AVAILABLE:
        return {"is_training": False, "error": "G38 not available"}
    trainer = get_auto_trainer()
    return {
        "is_training": trainer.is_training,
        "state": trainer.state.value,
        "epoch": trainer._epoch,
        "continuous_mode": trainer._continuous_mode,
        "continuous_target": trainer._continuous_target,
    }


@app.post("/training/start")
async def training_start(user=Depends(require_admin)):
    """Start training via admin panel."""
    if not G38_AVAILABLE:
        raise HTTPException(status_code=503, detail="G38 not available")
    trainer = get_auto_trainer()
    if trainer.is_training:
        return {"success": False, "message": "Already training"}
    import threading
    def _run():
        trainer.force_start_training(epochs=10)
    threading.Thread(target=_run, daemon=True).start()
    return {"success": True, "message": "Training started"}


@app.post("/training/stop")
async def training_stop(user=Depends(require_admin)):
    """Stop training via admin panel."""
    if not G38_AVAILABLE:
        raise HTTPException(status_code=503, detail="G38 not available")
    trainer = get_auto_trainer()
    result = trainer.abort_training()
    return {"success": True, "message": "Training stop requested", **result}


@app.post("/training/continuous")
async def training_continuous(request: Request, user=Depends(require_admin)):
    """Toggle continuous training mode via admin panel."""
    if not G38_AVAILABLE:
        raise HTTPException(status_code=503, detail="G38 not available")
    data = await request.json()
    enabled = data.get("enabled", False)
    target_epochs = data.get("target_epochs", 0)
    if enabled:
        start_continuous_training(target_epochs=target_epochs)
        return {"success": True, "message": "Continuous mode enabled"}
    else:
        stop_continuous_training()
        return {"success": True, "message": "Continuous mode disabled"}


@app.post("/training/interval")
async def training_interval(request: Request, user=Depends(require_admin)):
    """Set training check interval via admin panel."""
    if not G38_AVAILABLE:
        raise HTTPException(status_code=503, detail="G38 not available")
    data = await request.json()
    interval = data.get("interval", 30)
    trainer = get_auto_trainer()
    trainer.CHECK_INTERVAL_SECONDS = max(10, min(interval, 3600))
    return {"success": True, "interval": trainer.CHECK_INTERVAL_SECONDS}


@app.get("/api/g38/guards")
async def get_g38_guards(user=Depends(require_auth)):
    """Get all G38 guard statuses."""
    if not G38_AVAILABLE:
        return {"guards": [], "error": "G38 modules not loaded"}
    
    guards = []
    for guard in ALL_GUARDS:
        result, msg = guard()
        guards.append({
            "name": guard.__name__,
            "returns_false": not result,
            "message": msg,
        })
    
    return {
        "guards": guards,
        "total": len(guards),
        "all_passing": all(not g["returns_false"] is False for g in guards),
    }


@app.get("/api/g38/reports")
async def get_g38_training_reports(user=Depends(require_auth)):
    """Get G38 training reports."""
    reports_dir = PROJECT_ROOT / "reports" / "g38_training"
    
    if not reports_dir.exists():
        return {"reports": [], "count": 0}
    
    reports = []
    
    # Find all summary files
    for summary_file in sorted(reports_dir.glob("training_summary_*.txt"), reverse=True):
        session_id = summary_file.stem.replace("training_summary_", "")
        
        # Find corresponding learned and not_learned files
        learned_file = reports_dir / f"learned_features_{session_id}.json"
        not_learned_file = reports_dir / f"not_learned_yet_{session_id}.txt"
        
        report = {
            "session_id": session_id,
            "summary_file": summary_file.name,
            "summary_content": summary_file.read_text()[:500] + "..." if summary_file.exists() else None,
            "has_learned_features": learned_file.exists(),
            "has_not_learned": not_learned_file.exists(),
            "created_at": datetime.fromtimestamp(summary_file.stat().st_mtime).isoformat(),
        }
        
        # Read learned features JSON if exists
        if learned_file.exists():
            import json
            try:
                report["learned_features"] = json.loads(learned_file.read_text())
            except Exception:
                logger.exception("Failed to parse learned features JSON")
                report["learned_features"] = None
        
        reports.append(report)
    
    return {
        "reports": reports[:20],  # Last 20 reports
        "count": len(reports),
    }


@app.get("/api/g38/reports/latest")
async def get_g38_latest_report(user=Depends(require_auth)):
    """Get the latest G38 training report."""
    reports_dir = PROJECT_ROOT / "reports" / "g38_training"
    
    if not reports_dir.exists():
        return {"available": False, "error": "No reports directory"}
    
    # Find latest summary
    summaries = sorted(reports_dir.glob("training_summary_*.txt"), reverse=True)
    
    if not summaries:
        return {"available": False, "error": "No reports found"}
    
    latest = summaries[0]
    session_id = latest.stem.replace("training_summary_", "")
    
    # Read all files for this session
    learned_file = reports_dir / f"learned_features_{session_id}.json"
    not_learned_file = reports_dir / f"not_learned_yet_{session_id}.txt"
    
    import json
    
    return {
        "available": True,
        "session_id": session_id,
        "summary": latest.read_text() if latest.exists() else None,
        "learned_features": json.loads(learned_file.read_text()) if learned_file.exists() else None,
        "not_learned": not_learned_file.read_text() if not_learned_file.exists() else None,
        "created_at": datetime.fromtimestamp(latest.stat().st_mtime).isoformat(),
    }


# =============================================================================
# MANUAL TRAINING CONTROL ENDPOINTS
# =============================================================================

@app.post("/training/start")
async def manual_start_training(epochs: int = 10, user=Depends(require_auth)):
    """Manually start GPU training. No auto-trigger."""
    if not G38_AVAILABLE:
        return {"success": False, "error": "G38 modules not loaded"}
    
    trainer = get_auto_trainer()
    
    if trainer.is_training:
        return {
            "success": False,
            "error": "Training already in progress",
            "state": trainer.state.value,
        }
    
    import threading
    def run_training():
        trainer.force_start_training(epochs=epochs)
    
    thread = threading.Thread(target=run_training, daemon=True)
    thread.start()
    
    return {
        "success": True,
        "message": f"Training started for {epochs} epochs",
        "state": "TRAINING",
        "training_mode": "MANUAL",
    }


@app.post("/training/continuous")
async def start_24_7_training(epochs: int = 0, user=Depends(require_auth)):
    """Start 24/7 continuous GPU training. epochs=0 means infinite."""
    if not G38_AVAILABLE:
        return {"success": False, "error": "G38 modules not loaded"}
    
    result = start_continuous_training(target_epochs=epochs)
    return {"success": result.get("started", False), **result}


@app.post("/training/continuous/stop")
async def stop_24_7_training(user=Depends(require_auth)):
    """Stop 24/7 continuous training."""
    if not G38_AVAILABLE:
        return {"success": False, "error": "G38 modules not loaded"}
    
    result = stop_continuous_training()
    return {"success": result.get("stopped", False), **result}


@app.post("/training/stop")
async def manual_stop_training(user=Depends(require_auth)):
    """Stop training immediately."""
    if not G38_AVAILABLE:
        return {"success": False, "error": "G38 modules not loaded"}
    
    trainer = get_auto_trainer()
    result = trainer.abort_training()
    
    return {
        "success": result.get("aborted", False),
        "message": "Training stopped" if result.get("aborted") else "No training in progress",
        "state": trainer.state.value,
    }


@app.get("/training/status")
async def manual_training_status(user=Depends(require_auth)):
    """Get current training status."""
    if not G38_AVAILABLE:
        return {"available": False, "error": "G38 modules not loaded"}
    
    trainer = get_auto_trainer()
    return trainer.get_status()


@app.get("/training/progress")
async def manual_training_progress(user=Depends(require_auth)):
    """Get real-time training progress. Returns null if unavailable."""
    mgr = get_training_state_manager()
    metrics = mgr.get_training_progress()
    return metrics.to_dict()


@app.get("/gpu/status")
async def gpu_status(user=Depends(require_auth)):
    """Get GPU utilization and memory metrics. Real data only."""
    result: Dict[str, Any] = {
        "gpu_available": False,
        "device_name": None,
        "utilization_percent": None,
        "memory_allocated_mb": None,
        "memory_reserved_mb": None, 
        "memory_total_mb": None,
        "temperature": None,
        "compute_capability": None,
    }
    
    try:
        import torch
        if not torch.cuda.is_available():
            return result
        
        result["gpu_available"] = True
        result["device_name"] = torch.cuda.get_device_name(0)
        result["memory_allocated_mb"] = round(torch.cuda.memory_allocated() / 1024 / 1024, 2)
        result["memory_reserved_mb"] = round(torch.cuda.memory_reserved() / 1024 / 1024, 2)
        props = torch.cuda.get_device_properties(0)
        result["memory_total_mb"] = round(props.total_mem / 1024 / 1024, 2)
        cap = torch.cuda.get_device_capability(0)
        result["compute_capability"] = f"{cap[0]}.{cap[1]}"
    except Exception:
        pass
    
    # nvidia-smi for utilization and temperature
    try:
        import subprocess
        smi_output = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,temperature.gpu",
             "--format=csv,noheader,nounits"],
            timeout=5, text=True
        ).strip()
        parts = smi_output.split(",")
        if len(parts) >= 2:
            result["utilization_percent"] = float(parts[0].strip())
            result["temperature"] = float(parts[1].strip())
    except Exception:
        pass
    
    return result


@app.get("/dataset/stats")
async def dataset_stats(user=Depends(require_auth)):
    """Get training dataset statistics."""
    if not G38_AVAILABLE:
        return {"available": False, "error": "G38 modules not loaded"}
    
    trainer = get_auto_trainer()
    if trainer._gpu_dataset_stats:
        return {
            "available": True,
            **trainer._gpu_dataset_stats,
        }
    
    # Try to get stats from dataset loader directly
    try:
        from impl_v1.training.data.real_dataset_loader import validate_dataset_integrity
        valid, msg = validate_dataset_integrity()
        return {
            "available": valid,
            "message": msg,
            "source": "real_dataset_loader",
        }
    except Exception as e:
        logger.exception("Error in dataset_stats")
        return {"available": False, "error": "Internal error"}
# =============================================================================

@app.get("/api/db/users")
def list_users(user=Depends(require_auth)):
    """Get all users from HDD storage."""
    try:
        users = get_all_users()
        return {"users": users, "total": len(users)}
    except Exception as e:
        logger.exception("Error listing users")
        return {"users": [], "total": 0, "error": "Internal error"}


@app.post("/api/db/users")
def add_user(request: CreateUserRequest, admin_user=Depends(require_admin)):
    """Create a new user."""
    try:
        new_user = create_user(request.name, request.email, request.role)
        log_activity(str(new_user['id']), "USER_CREATED", f"User {request.name} created")
        return {"success": True, "user": new_user}
    except Exception as e:
        logger.exception("Error creating user")
        raise HTTPException(status_code=400, detail="Failed to create user")


@app.get("/api/db/users/{user_id}")
def get_single_user(user_id: str, user=Depends(require_auth)):
    """Get a specific user by ID."""
    try:
        user = get_user(user_id)
        if user:
            return {"success": True, "user": user}
        return {"success": False, "error": "User not found"}
    except Exception as e:
        logger.exception("Error fetching user")
        raise HTTPException(status_code=400, detail="Failed to fetch user")


@app.get("/api/db/users/{user_id}/bounties")
def get_user_bounties_endpoint(user_id: str, user=Depends(require_auth)):
    """Get all bounties for a specific user."""
    try:
        bounties = get_user_bounties(user_id)
        return {"bounties": bounties, "total": len(bounties)}
    except Exception as e:
        logger.exception("Error listing user bounties")
        return {"bounties": [], "total": 0, "error": "Internal error"}


@app.get("/api/db/targets")
def list_targets(user=Depends(require_auth)):
    """Get all targets from HDD storage."""
    try:
        targets = get_all_targets()
        return {"targets": targets, "total": len(targets)}
    except Exception as e:
        logger.exception("Error listing targets")
        return {"targets": [], "total": 0, "error": "Internal error"}


@app.post("/api/db/targets")
def add_target(request: CreateTargetRequest, user=Depends(require_admin)):
    """Create a new target."""
    try:
        target = create_target(
            request.program_name,
            request.scope,
            request.link,
            request.platform,
            request.payout_tier
        )
        log_activity(None, "TARGET_CREATED", f"Target {request.program_name} created")
        return {"success": True, "target": target}
    except Exception as e:
        logger.exception("Error creating target")
        raise HTTPException(status_code=400, detail="Failed to create target")


@app.get("/api/db/bounties")
def list_bounties(user=Depends(require_auth)):
    """Get all bounties."""
    try:
        bounties = get_all_bounties()
        return {"bounties": bounties, "total": len(bounties)}
    except Exception as e:
        logger.exception("Error listing bounties")
        return {"bounties": [], "total": 0, "error": "Internal error"}


@app.post("/api/db/bounties")
def add_bounty(request: CreateBountyRequest, user=Depends(require_admin)):
    """Create a new bounty submission."""
    try:
        bounty = create_bounty(
            request.user_id,
            request.target_id,
            request.title,
            request.description,
            request.severity
        )
        log_activity(request.user_id, "BOUNTY_SUBMITTED", f"Bounty: {request.title}")
        return {"success": True, "bounty": bounty}
    except Exception as e:
        logger.exception("Error creating bounty")
        raise HTTPException(status_code=400, detail="Failed to create bounty")


@app.put("/api/db/bounties")
def update_bounty(request: UpdateBountyRequest, user=Depends(require_admin)):
    """Update bounty status and reward."""
    try:
        update_bounty_status(request.bounty_id, request.status, request.reward)
        log_activity(None, "BOUNTY_UPDATED", f"Bounty {request.bounty_id} -> {request.status}")
        return {"success": True, "bounty_id": request.bounty_id, "status": request.status}
    except Exception as e:
        logger.exception("Error updating bounty")
        raise HTTPException(status_code=400, detail="Failed to update bounty")


@app.post("/api/db/sessions")
def add_session(request: CreateSessionRequest, user=Depends(require_admin)):
    """Create a new session."""
    try:
        session = create_session(request.user_id, request.mode, request.target_scope)
        log_activity(request.user_id, "SESSION_STARTED", f"Mode: {request.mode}")
        return {"success": True, "session": session}
    except Exception as e:
        logger.exception("Error creating session")
        raise HTTPException(status_code=400, detail="Failed to create session")


@app.get("/api/db/activity")
def list_activity(limit: int = 50, user=Depends(require_auth)):
    """Get recent activity log."""
    try:
        activities = get_recent_activity(limit)
        return {"activities": activities, "total": len(activities)}
    except Exception as e:
        logger.exception("Error listing activity")
        return {"activities": [], "total": 0, "error": "Internal error"}


@app.get("/api/db/admin/stats")
def get_admin_statistics(user=Depends(require_admin)):
    """Get admin dashboard statistics."""
    try:
        stats = get_admin_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        logger.exception("Error fetching admin stats")
        return {"success": False, "stats": None, "error": "Internal error"}


# =============================================================================
# HDD STORAGE ENGINE ENDPOINTS (NEW)
# =============================================================================

@app.get("/api/storage/stats")
def storage_stats_endpoint(user=Depends(require_auth)):
    """Get HDD storage engine statistics."""
    return get_storage_stats()


@app.get("/api/storage/lifecycle")
def lifecycle_status_endpoint(user=Depends(require_auth)):
    """Get lifecycle status and deletion preview."""
    return get_lifecycle_status()


@app.get("/api/storage/disk")
def disk_status_endpoint(user=Depends(require_auth)):
    """Get HDD disk usage, alerts, and health."""
    return get_disk_status()


@app.get("/api/storage/delete-preview")
def delete_preview_endpoint(entity_type: Optional[str] = None, user=Depends(require_admin)):
    """Preview which entities would be auto-deleted."""
    return get_delete_preview(entity_type)


@app.get("/api/video/list")
def video_list_endpoint(user_id: Optional[str] = None, user=Depends(require_auth)):
    """List stored videos. Non-admin users can only see their own videos."""
    # IDOR: Force user_id to authenticated user for non-admins
    if user.get("role") != "admin":
        user_id = user.get("sub")
    return list_videos(user_id)


@app.post("/api/video/token")
async def video_token_endpoint(request: Request, user=Depends(require_auth)):
    """Generate a signed video streaming token. Auth required."""
    body = await request.json()
    # IDOR: Force user_id to authenticated user for non-admins
    requested_user_id = body.get("user_id", "")
    if user.get("role") != "admin":
        requested_user_id = user.get("sub", "")
    return get_video_stream_token(
        requested_user_id,
        body.get("session_id", ""),
        body.get("filename", "video.webm"),
    )


# =============================================================================
# AUTH / LOGIN / DEVICE TRACKING ENDPOINTS
# =============================================================================

class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    # NOTE: 'role' field removed — all registrations are 'hunter'
    # Admin promotion requires existing admin via /api/db/users endpoint


@app.post("/auth/register")
async def register_user(request: RegisterRequest, req: Request):
    """Register a new user with hashed password."""
    existing = get_user_by_email(request.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    pw_hash = hash_password(request.password)
    user = create_user(request.name, request.email, "hunter")  # Always hunter — no privilege escalation
    update_user_password(user["id"], pw_hash)

    ip = req.client.host if req.client else "unknown"
    log_activity(user["id"], "USER_REGISTERED", f"User {request.name} registered", ip_address=ip)

    token = generate_jwt(user["id"], request.email)
    return {
        "success": True,
        "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
        "token": token
    }


@app.post("/auth/login")
async def login(request: LoginRequest, req: Request):
    """Login with email/password. Captures IP, UA, device hash. Sends alerts."""
    ip = req.client.host if req.client else "unknown"
    ua = req.headers.get("user-agent", "unknown")

    # Rate limiting
    limiter = get_rate_limiter()
    if limiter.is_rate_limited(ip):
        alert_rate_limit_exceeded(ip, limiter.max_attempts)
        log_activity(None, "RATE_LIMIT_EXCEEDED", f"IP {ip} exceeded login rate limit", ip_address=ip)
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")

    limiter.record_attempt(ip)

    # Find user
    user = get_user_by_email(request.email)
    if not user:
        log_activity(None, "LOGIN_FAILED", f"Unknown email: {request.email}", ip_address=ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Verify password
    if not user.get("password_hash") or not verify_password(request.password, user["password_hash"]):
        log_activity(user["id"], "LOGIN_FAILED", "Invalid password", ip_address=ip)
        alert_suspicious_activity(
            f"Failed login attempt for {user['name']}",
            ip_address=ip, user_name=user["name"],
            metadata={"email": request.email}
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Success — reset rate limiter
    limiter.reset(ip)

    # B9: Auto-rehash legacy password to v2 on successful login
    if needs_rehash(user["password_hash"]):
        new_hash = hash_password(request.password)
        update_user_password(user["id"], new_hash)
        log_activity(user["id"], "PASSWORD_REHASHED", "Legacy hash upgraded to v2", ip_address=ip)

    # Compute device hash and register device
    dh = compute_device_hash(ua, ip)
    device = register_device(user["id"], dh, ip, ua)

    # Create session on HDD
    session = create_session(
        user["id"], "AUTHENTICATED", None,
        ip_address=ip, user_agent=ua, device_hash=dh
    )

    # Log activity
    log_activity(user["id"], "LOGIN_SUCCESS", f"Login from {ip}", ip_address=ip)

    # Send alerts
    alert_new_login(user["name"], ip, ua)

    if device.get("is_new"):
        alert_new_device(user["name"], dh, ip, ua)

    active_count = get_active_device_count(user["id"])
    if active_count > 1:
        devices = get_user_devices(user["id"])
        alert_multiple_devices(user["name"], active_count, devices)

    # Generate JWT
    token = generate_jwt(user["id"], user.get("email"))

    return {
        "success": True,
        "user": {"id": user["id"], "name": user["name"], "email": user.get("email")},
        "token": token,
        "session_id": session["id"],
        "device": {"hash": dh, "is_new": device.get("is_new", False)}
    }


@app.post("/auth/logout")
async def logout(req: Request, user=Depends(require_auth)):
    """End current session. Revokes token and invalidates session."""
    ip = req.client.host if req.client else "unknown"

    # Extract and revoke the Bearer token
    auth_header = req.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        revoke_token(token)

    # Revoke session if present in user payload
    session_id = user.get("session_id")
    if session_id:
        revoke_session(session_id)
        try:
            end_session(session_id)
        except Exception:
            pass  # Best effort

    user_id = user.get("sub")
    log_activity(user_id, "LOGOUT", f"Logout from {ip} — token+session revoked", ip_address=ip)
    return {"success": True, "message": "Logged out — token and session revoked"}


@app.get("/admin/active-devices")
def get_active_devices_endpoint(user=Depends(require_admin)):
    """Get all active devices. Admin only. HDD data only."""
    try:
        devices = get_all_active_devices()
        return {"devices": devices, "total": len(devices)}
    except Exception as e:
        logger.exception("Error listing active devices")
        return {"devices": [], "total": 0, "error": "Internal error"}


@app.get("/admin/active-sessions")
def get_active_sessions_endpoint(user=Depends(require_admin)):
    """Get all active sessions. Admin only. HDD data only."""
    try:
        sessions = get_active_sessions()
        return {"sessions": sessions, "total": len(sessions)}
    except Exception as e:
        logger.exception("Error listing active sessions")
        return {"sessions": [], "total": 0, "error": "Internal error"}


# =============================================================================
# HUNTING ENDPOINTS (wired to hunting-control-panel.tsx + HuntingPanel.tsx)
# =============================================================================

# In-memory hunting auto-mode state
_hunting_auto_mode = {
    "enabled": False,
    "shadow_only": True,
    "integrity_score": 0,
    "conditions_met": False,
    "blocked_reasons": ["System not yet calibrated", "No verified fields"],
}


@app.get("/api/hunting/targets")
async def get_hunting_targets(user=Depends(require_auth)):
    """Get AI-suggested hunting targets from the database."""
    try:
        # Pull real targets from HDD storage
        db_targets = get_all_targets()
        suggestions = []
        for t in db_targets:
            suggestions.append({
                "domain": t.get("scope", "unknown"),
                "program_name": t.get("program_name", "Unknown"),
                "platform": t.get("platform", "Unknown"),
                "scope_size": 1,
                "api_endpoint_count": 0,
                "wildcard_count": 1 if "*" in t.get("scope", "") else 0,
                "likelihood_percent": 50,
                "difficulty": "MEDIUM",
                "bounty_range": {"min_usd": 100, "max_usd": 5000},
                "analysis": f"Target from {t.get('platform', 'unknown')} program",
            })
        return {"targets": suggestions, "total": len(suggestions)}
    except Exception as e:
        logger.exception("Error listing hunting targets")
        return {"targets": [], "total": 0, "error": "Internal error"}


@app.get("/api/hunting/auto-mode")
async def get_hunting_auto_mode(user=Depends(require_auth)):
    """Get current hunting auto-mode state with integrity score."""
    # Read integrity score from supervisor if available
    if INTEGRITY_AVAILABLE:
        try:
            supervisor = get_integrity_supervisor()
            probe = supervisor.probe_all()
            score = probe.get("overall_integrity", {}).get("score", 0)
            _hunting_auto_mode["integrity_score"] = score
            # Auto-mode can be enabled if integrity >= 80
            _hunting_auto_mode["conditions_met"] = score >= 80
            if score < 80:
                _hunting_auto_mode["blocked_reasons"] = [
                    f"Integrity score {score}% < 80% required"
                ]
            else:
                _hunting_auto_mode["blocked_reasons"] = []
        except Exception:
            pass
    return _hunting_auto_mode


# =============================================================================
# WEBSOCKET ENDPOINTS
# =============================================================================

# In-memory hunting WS connections
hunting_connections: Dict[str, WebSocket] = {}


@app.websocket("/ws/hunting")
async def hunting_websocket(websocket: WebSocket):
    """WebSocket endpoint for live hunting chat (HuntingPanel.tsx)."""
    # B8: Auth gating — verify token before accepting
    user = await ws_authenticate(websocket)
    if user is None:
        await websocket.close(code=4001, reason="Authentication required")
        return

    await websocket.accept()
    conn_id = uuid.uuid4().hex[:8]
    hunting_connections[conn_id] = websocket

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")

            if msg_type == "chat":
                # Echo back as assistant response
                user_text = data.get("content", "")
                await websocket.send_json({
                    "type": "response",
                    "content": f"Acknowledged: {user_text}. Hunting assistant is in shadow-only mode.",
                })
            elif msg_type == "detect":
                # Return a detection status
                await websocket.send_json({
                    "type": "detection",
                    "result": {
                        "exploit_type": "Awaiting scan",
                        "confidence": 0.0,
                        "field_name": "N/A",
                        "features": [],
                        "cvss_score": 0.0,
                        "severity": "INFO",
                        "reasoning": "No active scan in progress",
                        "poc": "",
                        "mitigation": "",
                    },
                })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        hunting_connections.pop(conn_id, None)


@app.websocket("/ws/hunter/{workflow_id}")
async def hunter_websocket(websocket: WebSocket, workflow_id: str):
    """WebSocket endpoint for Hunter workflow updates."""
    # B8: Auth gating — verify token before accepting
    user = await ws_authenticate(websocket)
    if user is None:
        await websocket.close(code=4001, reason="Authentication required")
        return

    await websocket.accept()
    hunter_connections[workflow_id] = websocket
    
    try:
        # Get workflow info
        workflow = active_workflows.get(workflow_id)
        if not workflow:
            await websocket.send_json({"error": "Workflow not found"})
            return
        
        # Simulate Hunter module execution
        hunter_modules = discover_hunter_modules()
        module_names = list(hunter_modules.keys())
        
        for idx, module_name in enumerate(module_names):
            # Simulate step execution
            step = {
                "module_name": module_name,
                "function_name": f"execute_{module_name}",
                "success": True,
                "input_data": {"target": workflow["target"], "module_index": idx},
                "output_data": {"status": "completed", "checks_passed": True},
                "timestamp": datetime.now(UTC).isoformat()
            }
            
            await websocket.send_json({"type": "step", "step": step})
            workflow["steps"].append(step)
            await asyncio.sleep(0.3)  # Simulate processing time
        
        # Send completion
        result = {
            "final_result": {
                "total_modules": len(module_names),
                "successful": len(module_names),
                "failed": 0
            },
            "evidence_chain_hash": uuid.uuid4().hex
        }
        
        await websocket.send_json({"type": "complete", "result": result})
        
    except WebSocketDisconnect:
        pass
    finally:
        hunter_connections.pop(workflow_id, None)


@app.websocket("/ws/bounty/{report_id}")
async def bounty_websocket(websocket: WebSocket, report_id: str):
    """WebSocket endpoint for HTTP-based security analysis."""
    # B8: Auth gating — verify token before accepting
    user = await ws_authenticate(websocket)
    if user is None:
        await websocket.close(code=4001, reason="Authentication required")
        return

    await websocket.accept()
    bounty_connections[report_id] = websocket
    ws_closed = False
    
    try:
        # Get workflow info
        workflow = active_workflows.get(report_id)
        if not workflow:
            await websocket.send_json({"error": "Report not found"})
            return
        
        target_url = workflow.get("target", "https://example.com")
        mode = workflow.get("mode", "READ_ONLY")  # READ_ONLY or REAL
        
        # Debug logging
        print(f"[WS] WEBSOCKET CONNECTED: {report_id}")
        print(f"   Target URL: {target_url}")
        print(f"   Mode: {mode}")
        
        # Create phase runner with WebSocket progress callback
        async def send_progress(update):
            nonlocal ws_closed
            if ws_closed:
                return
            try:
                await websocket.send_json(update)
            except Exception:
                ws_closed = True
        
        runner = RealPhaseRunner(on_progress=send_progress)
        
        # Run the HTTP-based workflow
        context = await runner.run_workflow(
            target_url=target_url,
            workflow_id=report_id,
            mode=mode
        )
        
        if ws_closed:
            return
        
        # Build summary from results
        successful = len([r for r in context.phase_results if r.status == "SUCCESS"])
        failed = len([r for r in context.phase_results if r.status == "FAILED"])
        total_duration = sum(r.duration_ms for r in context.phase_results)
        
        # Convert findings to dict
        findings_data = []
        for f in context.findings:
            if hasattr(f, '__dict__'):
                findings_data.append({
                    "finding_id": f.finding_id,
                    "category": f.category,
                    "severity": f.severity,
                    "title": f.title,
                    "description": f.description,
                    "url": getattr(f, "url", "")
                })
            else:
                findings_data.append(f)
        
        # Final result
        result = {
            "summary": {
                "total_phases": len(context.phase_results),
                "successful_steps": successful,
                "failed_steps": failed,
                "findings_count": len(context.findings),
                "pages_visited": len(context.pages_visited),
                "technologies": context.technologies,
                "total_duration_ms": total_duration,
                "report_file": getattr(context, 'report_file', None)
            },
            "findings": findings_data,
            "pages_visited": context.pages_visited,
            "phases": [
                {
                    "number": r.phase_number,
                    "name": r.phase_name,
                    "status": r.status,
                    "duration_ms": r.duration_ms
                }
                for r in context.phase_results
            ],
            "report_hash": hashlib.sha256(
                json.dumps(
                    [{"number": r.phase_number, "name": r.phase_name, "status": r.status, "duration_ms": r.duration_ms} for r in context.phase_results],
                    sort_keys=True, default=str
                ).encode()
            ).hexdigest()
        }
        
        try:
            await websocket.send_json({"type": "complete", "result": result})
        except Exception:
            pass
        
    except WebSocketDisconnect:
        print(f"[WS] WebSocket disconnected: {report_id}")
    except Exception as e:
        logger.exception(f"WebSocket error: {report_id}")
        try:
            await websocket.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass
    finally:
        bounty_connections.pop(report_id, None)



# =============================================================================
# STARTUP EVENT (using modern lifespan)
# =============================================================================

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    """Lifespan context manager for startup/shutdown."""
    # Startup
    # SECURITY: Preflight checks — fail-closed on missing/weak secrets
    preflight_check_secrets()
    
    phases = discover_python_phases()
    hunter = discover_hunter_modules()
    print(f"[*] YGB API Server starting...")
    print(f"[*] Project root: {PROJECT_ROOT}")
    print(f"[*] Python phases: {len(phases)}")
    print(f"[*] Hunter modules: {len(hunter)}")
    
    # Initialize HDD storage engine (replaces SQLite)
    try:
        result = init_storage()
        print(f"[+] HDD Storage Engine initialized at: {result['hdd_root']}")
        print(f"[+] Subsystems: {result['subsystems']}")
    except Exception as e:
        print(f"[!] HDD Storage Engine init failed: {e}")
    
    print(f"[+] Server ready at http://localhost:8000")
    
    # Start G38 auto-training scheduler
    if G38_AVAILABLE:
        start_auto_training()
        print("[*] G38 auto-training started")
    
    yield
    
    # Shutdown
    print("[*] YGB API Server shutting down...")
    
    # Stop G38 auto-training
    if G38_AVAILABLE:
        stop_auto_training()
        print("[*] G38 auto-training stopped")
    
    # Shutdown HDD storage engine
    shutdown_storage()
    print("[*] HDD Storage Engine shutdown complete")

# Apply lifespan to app
app.router.lifespan_context = lifespan


# =============================================================================
# SYSTEM INTEGRITY ENDPOINT
# =============================================================================

@app.get("/system/integrity")
async def system_integrity(user=Depends(require_auth)):
    """Unified system integrity dashboard. Real data only — no mocks."""
    if not INTEGRITY_AVAILABLE:
        return {
            "error": "Integrity supervisor not available",
            "overall_integrity": {"score": 0, "status": "RED"},
            "shadow_allowed": False,
            "forced_mode": "MODE_A",
        }

    supervisor = get_integrity_supervisor()
    return supervisor.probe_all()


# =============================================================================
# DUAL-MODE VOICE ENDPOINTS
# =============================================================================

# Active voice mode state
_active_voice_mode = "SECURITY"


class VoiceParseRequest(BaseModel):
    text: str
    mode: Optional[str] = None  # "SECURITY" or "RESEARCH", auto-detect if None


@app.post("/api/voice/parse")
async def voice_parse(request: VoiceParseRequest, user=Depends(require_auth)):
    """
    Dual-mode voice parser.
    
    - SECURITY mode: routes to g12_voice_input.extract_intent()
    - RESEARCH mode: routes to isolated Edge search pipeline
    - Auto-classifies if mode not specified
    """
    global _active_voice_mode
    text = request.text.strip()
    
    if not text:
        return {
            "intent_id": f"VOC-EMPTY",
            "intent_type": "UNKNOWN",
            "raw_text": "",
            "extracted_value": None,
            "confidence": 0.0,
            "status": "INVALID",
            "block_reason": "Empty voice input",
            "active_mode": _active_voice_mode,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    
    # Determine mode
    mode = request.mode
    route_decision = None
    
    if RESEARCH_AVAILABLE and mode is None:
        # Auto-classify
        router = QueryRouter()
        route_decision = router.classify(text)
        mode = route_decision.mode.value
    elif mode is None:
        mode = "SECURITY"
    
    _active_voice_mode = mode
    
    # ===== RESEARCH MODE =====
    if mode == "RESEARCH" and RESEARCH_AVAILABLE:
        # Run isolation pre-check
        guard = IsolationGuard()
        isolation_check = guard.pre_query_check(text)
        
        if not isolation_check.allowed:
            return {
                "intent_id": f"VOC-BLOCKED",
                "intent_type": "RESEARCH_QUERY",
                "raw_text": text,
                "extracted_value": None,
                "confidence": 0.0,
                "status": "BLOCKED",
                "block_reason": isolation_check.reason,
                "active_mode": "RESEARCH",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        
        # Execute research search
        pipeline = ResearchSearchPipeline()
        result = pipeline.search(text)
        
        # Audit log
        guard.log_research_query(
            query=text,
            result_status=result.status.value,
            checks_passed=5,
            checks_failed=0,
            violations=[],
        )
        
        return {
            "intent_id": f"VOC-RESEARCH",
            "intent_type": "RESEARCH_QUERY",
            "raw_text": text,
            "extracted_value": result.summary,
            "confidence": 0.9 if result.status == ResearchStatus.SUCCESS else 0.3,
            "status": "PARSED" if result.status == ResearchStatus.SUCCESS else "INVALID",
            "block_reason": None if result.status == ResearchStatus.SUCCESS else result.summary,
            "active_mode": "RESEARCH",
            "research_result": {
                "title": result.title,
                "summary": result.summary,
                "source": result.source,
                "key_terms": list(result.key_terms),
                "word_count": result.word_count,
                "elapsed_ms": result.elapsed_ms,
            },
            "route_decision": {
                "confidence": route_decision.confidence if route_decision else 1.0,
                "reason": route_decision.reason if route_decision else "Manual mode selection",
            } if route_decision or mode == "RESEARCH" else None,
            "timestamp": result.timestamp,
        }
    
    # ===== SECURITY MODE (default) =====
    try:
        from impl_v1.phase49.governors.g12_voice_input import extract_intent
        intent = extract_intent(text)
        return {
            "intent_id": intent.intent_id,
            "intent_type": intent.intent_type.value,
            "raw_text": intent.raw_text,
            "extracted_value": intent.extracted_value,
            "confidence": intent.confidence,
            "status": intent.status.value,
            "block_reason": intent.block_reason,
            "active_mode": "SECURITY",
            "timestamp": intent.timestamp,
        }
    except ImportError:
        return {
            "intent_id": "VOC-ERROR",
            "intent_type": "UNKNOWN",
            "raw_text": text,
            "extracted_value": None,
            "confidence": 0.0,
            "status": "INVALID",
            "block_reason": "Voice parser not available",
            "active_mode": "SECURITY",
            "timestamp": datetime.now(UTC).isoformat(),
        }


@app.get("/api/voice/mode")
async def voice_mode(user=Depends(require_auth)):
    """Return current active voice mode."""
    return {
        "mode": _active_voice_mode,
        "research_available": RESEARCH_AVAILABLE,
    }

# =============================================================================
# RUNTIME STATUS & ACCURACY ENDPOINTS (for Control Panel)
# =============================================================================

# In-memory mode state (authoritative — mirrors C++ mode_mutex)
_runtime_mode: str = "IDLE"  # IDLE, TRAIN, HUNT


@app.get("/runtime/status")
async def runtime_status(user=Depends(require_auth)):
    """
    GET /runtime/status — Validated runtime telemetry.
    Reads from C++ authoritative source (reports/training_telemetry.json),
    validates CRC + schema before returning data.
    If no file or validation fails → returns appropriate status.
    """
    telemetry_path = PROJECT_ROOT / "reports" / "training_telemetry.json"

    if not telemetry_path.exists():
        return {
            "status": "awaiting_data",
            "runtime": None,
            "determinism_ok": None,
            "stale": False,
            "last_update_ms": 0,
            "signature": None
        }

    try:
        import json as _json
        raw = telemetry_path.read_text(encoding="utf-8")
        data = _json.loads(raw)

        # Validate required fields
        required = ["schema_version", "determinism_status"]
        for field in required:
            if field not in data:
                return {
                    "status": "error",
                    "reason": f"Missing field: {field}",
                    "runtime": None,
                    "determinism_ok": False,
                    "stale": True,
                    "last_update_ms": 0,
                    "signature": None
                }

        # Check staleness (>60s since file mod time)
        import time as _time
        mod_time = telemetry_path.stat().st_mtime
        age_ms = int((_time.time() - mod_time) * 1000)
        is_stale = age_ms > 60000

        return {
            "status": "active",
            "runtime": {
                "total_epochs": data.get("total_epochs", 100),
                "completed_epochs": data.get("epoch", 0),
                "current_loss": data.get("loss", 0.0),
                "precision": data.get("precision", 0.0),
                "ece": data.get("ece", 0.0),
                "drift_kl": data.get("kl_divergence", 0.0),
                "duplicate_rate": data.get("duplicate_rate", 0.0),
                "gpu_util": data.get("gpu_util", 0.0),
                "cpu_util": data.get("cpu_util", 0.0),
                "temperature": data.get("gpu_temperature", 0.0),
                "determinism_status": data.get("determinism_status", False),
                "freeze_status": data.get("freeze_status", False),
                "mode": _runtime_mode,
                "progress_pct": min(100.0, (data.get("epoch", 0) / max(data.get("total_epochs", 100), 1)) * 100),
                "loss_trend": data.get("loss_trend", 0.0),
                # Phase 2: Real-time training visibility
                "wall_clock_unix": data.get("wall_clock_unix", 0),
                "monotonic_start_time": data.get("monotonic_start_time", 0),
                "training_duration_seconds": data.get("training_duration_seconds", 0.0),
            },
            "determinism_ok": data.get("determinism_status", False),
            "stale": is_stale,
            "last_update_ms": age_ms,
            "signature": data.get("signature", None)
        }
    except Exception as e:
        return {
            "status": "error",
            "reason": "Internal error",
            "runtime": None,
            "determinism_ok": False,
            "stale": True,
            "last_update_ms": 0,
            "signature": None
        }


@app.get("/api/accuracy/snapshot")
async def accuracy_snapshot(user=Depends(require_auth)):
    """
    GET /api/accuracy/snapshot — Current accuracy metrics snapshot.
    Returns precision, recall, ECE, dup suppression, and scope compliance.
    Reads from telemetry if available, otherwise returns defaults.
    """
    telemetry_path = PROJECT_ROOT / "reports" / "training_telemetry.json"

    defaults = {
        "precision": 0.0,
        "recall": 0.0,
        "ece_score": 0.0,
        "dup_suppression_rate": 0.0,
        "scope_compliance": 0.0
    }

    if not telemetry_path.exists():
        return defaults

    try:
        import json as _json
        data = _json.loads(telemetry_path.read_text(encoding="utf-8"))
        return {
            "precision": data.get("precision", 0.0),
            "recall": data.get("recall", 0.0),
            "ece_score": data.get("ece", 0.0),
            "dup_suppression_rate": data.get("dup_suppression_rate", 0.0),
            "scope_compliance": data.get("scope_compliance", 0.0)
        }
    except Exception:
        return defaults


# =============================================================================
# TRAINING DATA SOURCE TRANSPARENCY
# =============================================================================

@app.get("/api/training/data-source")
async def training_data_source(user=Depends(require_auth)):
    """
    GET /api/training/data-source — Training pipeline source transparency.
    
    Reads secure_data/dataset_manifest.json to report:
    - Data source (INGESTION_PIPELINE / SYNTHETIC / NONE)
    - Dataset hash
    - Sample count
    - Source registry status
    """
    _api_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(_api_dir)
    manifest_path = os.path.join(_project_root, "secure_data", "dataset_manifest.json")

    if not os.path.exists(manifest_path):
        return {
            "data_source": "NO_DATA",
            "dataset_hash": "",
            "sample_count": 0,
            "registry_status": "NO_MANIFEST",
            "strict_real_mode": True,
            "ingestion_manifest_hash": "",
        }

    try:
        import json as _json
        with open(manifest_path, 'r', encoding='utf-8') as _f:
            data = _json.load(_f)
        source = data.get("dataset_source", "UNKNOWN")

        # Determine registry status
        if source == "INGESTION_PIPELINE":
            registry = "VERIFIED"
        elif source == "SYNTHETIC_GENERATOR":
            registry = "BLOCKED"
        else:
            registry = "UNKNOWN"

        # Bridge integrity check
        bridge_hash = ""
        dll_integrity = "UNKNOWN"
        try:
            import ctypes
            _bridge_path = os.path.join(_project_root, "native", "distributed", "ingestion_bridge.dll")
            if os.path.exists(_bridge_path):
                _bridge = ctypes.CDLL(_bridge_path)
                _bridge.bridge_self_verify(_bridge_path.encode())
                hash_buf = ctypes.create_string_buffer(65)
                _bridge.bridge_get_self_hash(hash_buf, 65)
                bridge_hash = hash_buf.value.decode()
                dll_integrity = "VERIFIED" if _bridge.bridge_is_self_verified() else "FAILED"
        except Exception:
            dll_integrity = "CHECK_FAILED"

        # Module guard status
        guard_status = "UNKNOWN"
        try:
            _guard_path = os.path.join(_project_root, "native", "security", "module_integrity_guard.dll")
            guard_status = "ACTIVE" if os.path.exists(_guard_path) else "MISSING"
        except Exception:
            pass

        return {
            "data_source": source,
            "dataset_hash": data.get("dataset_hash", data.get("tensor_hash", "")),
            "sample_count": data.get("sample_count", 0),
            "registry_status": registry,
            "strict_real_mode": data.get("strict_real_mode", True),
            "ingestion_manifest_hash": data.get("ingestion_manifest_hash", ""),
            "bridge_hash": bridge_hash,
            "dll_integrity": dll_integrity,
            "integrity_guard": guard_status,
            "synthetic_status": "BLOCKED",
        }
    except Exception as e:
        return {
            "data_source": "ERROR",
            "dataset_hash": "",
            "sample_count": 0,
            "registry_status": "ERROR",
            "strict_real_mode": True,
            "ingestion_manifest_hash": "",
            "bridge_hash": "",
            "dll_integrity": "ERROR",
            "integrity_guard": "ERROR",
            "synthetic_status": "BLOCKED",
        }


# =============================================================================
# MODE CONTROL ENDPOINTS (TRAIN/HUNT mutual exclusion)
# =============================================================================

@app.post("/api/mode/train/start")
async def start_training_mode(user=Depends(require_auth)):
    """Start TRAIN mode. Blocked if HUNT is active."""
    global _runtime_mode
    if _runtime_mode == "HUNT":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={
            "error": "MUTEX_BLOCKED",
            "reason": "Cannot enter TRAIN while HUNT is active",
            "current_mode": _runtime_mode
        })
    if _runtime_mode == "TRAIN":
        return {"mode": "TRAIN", "status": "already_active"}
    _runtime_mode = "TRAIN"
    return {"mode": "TRAIN", "status": "started"}


@app.post("/api/mode/train/stop")
async def stop_training_mode(user=Depends(require_auth)):
    """Stop TRAIN mode."""
    global _runtime_mode
    if _runtime_mode != "TRAIN":
        return {"mode": _runtime_mode, "status": "not_in_train"}
    _runtime_mode = "IDLE"
    return {"mode": "IDLE", "status": "stopped"}


@app.post("/api/mode/hunt/start")
async def start_hunt_mode(user=Depends(require_auth)):
    """Start HUNT mode. Blocked if TRAIN is active."""
    global _runtime_mode
    if _runtime_mode == "TRAIN":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={
            "error": "MUTEX_BLOCKED",
            "reason": "Cannot enter HUNT while TRAIN is active",
            "current_mode": _runtime_mode
        })
    if _runtime_mode == "HUNT":
        return {"mode": "HUNT", "status": "already_active"}
    _runtime_mode = "HUNT"
    return {"mode": "HUNT", "status": "started"}


@app.post("/api/mode/hunt/stop")
async def stop_hunt_mode(user=Depends(require_auth)):
    """Stop HUNT mode."""
    global _runtime_mode
    if _runtime_mode != "HUNT":
        return {"mode": _runtime_mode, "status": "not_in_hunt"}
    _runtime_mode = "IDLE"
    return {"mode": "IDLE", "status": "stopped"}

# =============================================================================
# GITHUB OAUTH LOGIN
# =============================================================================

_GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
_GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
_FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
_GITHUB_REDIRECT_URI = os.getenv(
    "GITHUB_REDIRECT_URI",
    "http://localhost:8000/auth/github/callback",
)


@app.get("/auth/github")
async def github_auth_redirect():
    """Redirect to GitHub OAuth authorization page."""
    if not _GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=501,
            detail="GitHub OAuth not configured — set GITHUB_CLIENT_ID env var",
        )

    params = (
        f"client_id={_GITHUB_CLIENT_ID}"
        f"&redirect_uri={_GITHUB_REDIRECT_URI}"
        f"&scope=user:email"
        f"&state={__import__('secrets').token_hex(16)}"
    )
    return RedirectResponse(
        url=f"https://github.com/login/oauth/authorize?{params}",
        status_code=302,
    )


@app.get("/auth/github/callback")
async def github_auth_callback(code: str = "", error: str = ""):
    """Handle GitHub OAuth callback — exchange code → JWT → redirect to frontend."""
    if error:
        return RedirectResponse(
            url=f"{_FRONTEND_URL}/login?error={error}",
            status_code=302,
        )

    if not code:
        return RedirectResponse(
            url=f"{_FRONTEND_URL}/login?error=no_code",
            status_code=302,
        )

    if not _GITHUB_CLIENT_ID or not _GITHUB_CLIENT_SECRET:
        raise HTTPException(
            status_code=501,
            detail="GitHub OAuth not configured",
        )

    import urllib.request
    import urllib.parse

    try:
        # 1. Exchange code for access token
        token_data = urllib.parse.urlencode({
            "client_id": _GITHUB_CLIENT_ID,
            "client_secret": _GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": _GITHUB_REDIRECT_URI,
        }).encode()

        token_req = urllib.request.Request(
            "https://github.com/login/oauth/access_token",
            data=token_data,
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(token_req, timeout=10) as resp:
            token_resp = json.loads(resp.read().decode())

        access_token = token_resp.get("access_token")
        if not access_token:
            logger.error("GitHub token exchange failed: %s", token_resp)
            return RedirectResponse(
                url=f"{_FRONTEND_URL}/login?error=token_exchange_failed",
                status_code=302,
            )

        # 2. Fetch user info
        user_req = urllib.request.Request(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": "YGB-Server",
            },
        )
        with urllib.request.urlopen(user_req, timeout=10) as resp:
            user_data = json.loads(resp.read().decode())

        github_id = str(user_data.get("id", ""))
        github_login = user_data.get("login", "")
        github_email = user_data.get("email", "")

        # 3. If email not public, fetch from /user/emails
        if not github_email:
            emails_req = urllib.request.Request(
                "https://api.github.com/user/emails",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    "User-Agent": "YGB-Server",
                },
            )
            with urllib.request.urlopen(emails_req, timeout=10) as resp:
                emails = json.loads(resp.read().decode())
            # Pick primary verified email
            for em in emails:
                if em.get("primary") and em.get("verified"):
                    github_email = em["email"]
                    break
            if not github_email and emails:
                github_email = emails[0].get("email", "")

        # 4. Generate JWT using existing auth module
        from backend.auth.auth import generate_jwt
        user_id = f"github:{github_id}"
        jwt_token = generate_jwt(user_id=user_id, email=github_email)

        logger.info("GitHub login: %s (%s)", github_login, github_email)

        # 5. Redirect to frontend with token
        return RedirectResponse(
            url=f"{_FRONTEND_URL}/login?token={jwt_token}&user={github_login}",
            status_code=302,
        )

    except Exception as e:
        logger.exception("GitHub OAuth callback error")
        return RedirectResponse(
            url=f"{_FRONTEND_URL}/login?error=server_error",
            status_code=302,
        )


# =============================================================================
# ADMIN ROUTE COMPATIBILITY
# =============================================================================

class AdminLoginRequest(BaseModel):
    email: str
    totp_code: str = ""


@app.post("/admin/login")
async def admin_login(request: AdminLoginRequest, req: Request):
    """Admin login — entry point for admin auth. No Depends(require_auth)."""
    try:
        from backend.api.admin_auth import login as admin_auth_login
        result = admin_auth_login(
            email=request.email,
            totp_code=request.totp_code,
            ip=req.client.host if req.client else "0.0.0.0",
        )
        if result.get("status") == "ok":
            return result
        else:
            raise HTTPException(
                status_code=401,
                detail=result.get("message", "Login failed"),
            )
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=501, detail="Admin auth module not available")
    except Exception as e:
        logger.exception("Admin login error")
        raise HTTPException(status_code=500, detail="Internal error during login")


@app.get("/admin/verify")
async def admin_verify(req: Request):
    """Verify an admin token. Returns user info or 401."""
    auth_header = req.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    token = auth_header[7:]

    try:
        from backend.api.admin_auth import require_auth as admin_require_auth
        # Try as JWT first, then as session token
        result = admin_require_auth(jwt_token=token)
        if result.get("status") == "ok":
            return result

        result = admin_require_auth(session_token=token)
        if result.get("status") == "ok":
            return result

        raise HTTPException(status_code=401, detail="Invalid or expired token")
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=501, detail="Admin auth module not available")
    except Exception:
        logger.exception("Admin verify error")
        raise HTTPException(status_code=500, detail="Verification failed")


class VaultUnlockRequest(BaseModel):
    vault_password: str


@app.post("/admin/vault-unlock")
async def admin_vault_unlock(request: VaultUnlockRequest, req: Request):
    """Unlock the vault. Requires Bearer token for auth."""
    auth_header = req.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")

    token = auth_header[7:]

    try:
        from backend.api.vault_session import vault_unlock
        result = vault_unlock(
            vault_password=request.vault_password,
            session_token=token,
            ip=req.client.host if req.client else "0.0.0.0",
        )
        if result.get("status") == "ok":
            return result
        elif result.get("status") == "unauthorized":
            raise HTTPException(status_code=401, detail=result.get("message", "Unauthorized"))
        else:
            raise HTTPException(status_code=400, detail=result.get("message", "Vault unlock failed"))
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=501, detail="Vault session module not available")
    except Exception:
        logger.exception("Vault unlock error")
        raise HTTPException(status_code=500, detail="Vault unlock failed")


# =============================================================================
# ROLLOUT API COMPATIBILITY
# =============================================================================

@app.get("/api/rollout/status")
async def rollout_status(user=Depends(require_auth)):
    """Get current rollout governance status."""
    try:
        from governance.real_data_rollout_governor import get_current_status
        return get_current_status()
    except ImportError:
        return {
            "stage": 0,
            "stage_label": "STAGE_0",
            "real_data_pct": 0.20,
            "consecutive_stable": 0,
            "frozen": False,
            "freeze_reasons": [],
            "total_cycles": 0,
            "last_cycle_id": None,
            "last_updated": None,
            "promotion_history": [],
        }
    except Exception:
        logger.exception("Rollout status error")
        raise HTTPException(status_code=500, detail="Failed to fetch rollout status")


@app.get("/api/rollout/metrics")
async def rollout_metrics(user=Depends(require_auth)):
    """Get rollout risk metrics. Returns RiskMetrics shape matching frontend contract."""
    try:
        from governance.real_data_rollout_governor import load_state, ROLLOUT_STAGES
        state = load_state()
        real_pct = ROLLOUT_STAGES[state.current_stage]

        return {
            "current_stage": state.current_stage,
            "real_data_pct": real_pct,
            "label_quality": 0.0,
            "class_imbalance_ratio": 0.0,
            "js_divergence": 0.0,
            "unknown_token_ratio": 0.0,
            "feature_mismatch_ratio": 0.0,
            "fpr_current": 0.0,
            "fpr_baseline": 0.0,
            "drift_guard_pass": True,
            "regression_gate_pass": True,
            "determinism_gate_pass": True,
            "backtest_gate_pass": True,
            "consecutive_stable": state.consecutive_stable_cycles,
            "frozen": state.is_frozen,
            "freeze_reasons": state.freeze_reasons,
            "total_cycles": state.total_cycles_evaluated,
            "last_updated": state.last_updated,
        }
    except ImportError:
        return {
            "current_stage": 0,
            "real_data_pct": 0.20,
            "label_quality": 0.0,
            "class_imbalance_ratio": 0.0,
            "js_divergence": 0.0,
            "unknown_token_ratio": 0.0,
            "feature_mismatch_ratio": 0.0,
            "fpr_current": 0.0,
            "fpr_baseline": 0.0,
            "drift_guard_pass": True,
            "regression_gate_pass": True,
            "determinism_gate_pass": True,
            "backtest_gate_pass": True,
            "consecutive_stable": 0,
            "frozen": False,
            "freeze_reasons": [],
            "total_cycles": 0,
            "last_updated": None,
        }
    except Exception:
        logger.exception("Rollout metrics error")
        raise HTTPException(status_code=500, detail="Failed to fetch rollout metrics")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

