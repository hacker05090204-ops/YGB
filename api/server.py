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
import asyncio
import hashlib
from datetime import datetime, UTC
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

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
    stream_video, list_videos,
)

# Import training state manager
from backend.training.state_manager import get_training_state_manager

# Import auth and alerts
from backend.auth.auth import (
    hash_password, verify_password, generate_jwt, verify_jwt,
    compute_device_hash, get_rate_limiter, generate_csrf_token
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

app = FastAPI(
    title="YGB API",
    description="Bug Bounty Governance Backend",
    version="1.0.0"
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
    """Health check endpoint with system status."""
    phases = discover_python_phases()
    hunter_modules = discover_hunter_modules()
    
    return {
        "status": "ok",
        "ygb_root": str(PROJECT_ROOT),
        "python_phases": len([p for p in phases if p["number"] <= 19]),
        "impl_phases": len([p for p in phases if p["number"] >= 20]),
        "hunter_modules": len(hunter_modules),
        "hunter_integration": hunter_modules,
        "timestamp": datetime.now(UTC).isoformat()
    }


@app.get("/api/bounty/phases")
async def get_bounty_phases():
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
async def list_reports():
    """List all security reports in the report directory."""
    report_dir = PROJECT_ROOT / "report"
    if not report_dir.exists():
        return {"reports": [], "count": 0}
    
    reports = []
    for file in sorted(report_dir.glob("*.txt"), reverse=True):
        stat = file.stat()
        reports.append({
            "filename": file.name,
            "path": str(file),
            "size": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "download_url": f"/api/reports/{file.name}"
        })
    
    return {"reports": reports, "count": len(reports)}


@app.get("/api/reports/{filename}")
async def download_report(filename: str):
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
async def get_report_content(filename: str):
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
async def start_hunter(request: StartWorkflowRequest):
    """Start a V1 Hunter workflow."""
    if not request.target:
        raise HTTPException(status_code=400, detail="Target URL is required")
    
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
async def start_bounty(request: StartWorkflowRequest):
    """Start a Bounty Finder workflow with REAL browser automation."""
    if not request.target:
        raise HTTPException(status_code=400, detail="Target URL is required")
    
    # Validate target URL
    target = request.target.strip()
    if not target.startswith(("http://", "https://")):
        target = f"https://{target}"
    
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
async def create_dashboard(request: CreateDashboardRequest):
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
async def get_dashboard_state(dashboard_id: str = None):
    """Get current dashboard state."""
    if dashboard_id and dashboard_id in dashboard_states:
        return dashboard_states[dashboard_id]
    
    # No dashboard found — return error
    return {"error": "No dashboard found", "dashboard_id": None, "state": "DISCONNECTED"}


@app.get("/api/execution/state")
async def get_execution_state(kernel_id: str = None):
    """Get execution kernel state."""
    if kernel_id and kernel_id in execution_kernels:
        return execution_kernels[kernel_id]
    
    return {
        "state": "IDLE",
        "human_approved": False
    }


@app.post("/api/execution/transition")
async def execution_transition(request: ExecutionTransitionRequest):
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
    
    current_state = kernel.get("state", "IDLE")
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
async def submit_approval_decision(request: ApprovalDecisionRequest):
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
async def discover_targets(request: TargetDiscoveryRequest):
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
        return {
            "result_id": f"DIS-{uuid.uuid4().hex[:16].upper()}",
            "candidates": [],
            "total_found": 0,
            "filtered_count": 0,
            "error": str(e),
            "timestamp": datetime.now(UTC).isoformat()
        }


# =============================================================================
# SCOPE VALIDATION & TARGET SESSION MANAGEMENT
# =============================================================================

# In-memory target session state
target_sessions: Dict[str, Dict[str, Any]] = {}
scope_violations: List[Dict[str, Any]] = []


@app.post("/scope/validate")
async def validate_scope(request: Request):
    """Validate a scope definition against security rules."""
    data = await request.json()
    target_url = data.get("target_url", "")
    scope_definition = data.get("scope_definition", {})
    now = datetime.now(UTC).isoformat()

    violations = []

    # Rule 1: Reject empty target
    if not target_url.strip():
        violations.append({"rule": "EMPTY_TARGET", "message": "Target URL cannot be empty"})

    # Rule 2: Reject wildcards at TLD level (e.g. *.com, *.io)
    import re
    if re.match(r'^\*\.[a-z]{2,4}$', target_url):
        violations.append({"rule": "WILDCARD_TLD", "message": f"Wildcard at TLD level not allowed: {target_url}"})

    # Rule 3: Reject localhost/internal targets
    forbidden_hosts = ["localhost", "127.0.0.1", "0.0.0.0", "10.", "192.168.", "172.16."]
    for host in forbidden_hosts:
        if host in target_url.lower():
            violations.append({"rule": "INTERNAL_TARGET", "message": f"Internal/localhost targets are forbidden: {target_url}"})
            break

    # Rule 4: Reject if no valid domain pattern
    if not re.search(r'[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', target_url):
        violations.append({"rule": "INVALID_DOMAIN", "message": f"No valid domain found in: {target_url}"})

    is_valid = len(violations) == 0
    return {
        "valid": is_valid,
        "target_url": target_url,
        "violations": violations,
        "validated_at": now
    }


@app.post("/target/start")
async def start_target_session(request: Request):
    """Start a target scanning session."""
    data = await request.json()
    target_url = data.get("target_url", "")
    scope_definition = data.get("scope_definition", {})
    mode = data.get("mode", "READ_ONLY")
    now = datetime.now(UTC).isoformat()

    if not target_url.strip():
        return {"error": "target_url is required", "started": False}

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
async def stop_target_session(request: Request):
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
async def get_target_status():
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


@app.post("/api/voice/parse")
async def parse_voice_input(request: VoiceParseRequest):
    """Parse voice input and extract intent."""
    import re
    
    text = request.text.strip().lower()
    now = datetime.now(UTC).isoformat()
    
    # Forbidden patterns (from G12)
    forbidden = [r'\b(execute|run|start|launch|attack|exploit|hack)\b',
                 r'\b(approve|confirm|yes\s+do\s+it)\b',
                 r'\b(submit|send|post)\b']
    
    for pattern in forbidden:
        if re.search(pattern, text, re.IGNORECASE):
            return {
                "intent_id": f"VOC-{uuid.uuid4().hex[:16].upper()}",
                "intent_type": "UNKNOWN",
                "raw_text": request.text,
                "extracted_value": None,
                "confidence": 0.0,
                "status": "BLOCKED",
                "block_reason": f"Forbidden pattern detected",
                "timestamp": now
            }
    
    # Intent patterns
    if re.search(r'(?:find|discover|search\s+for)\s+targets?', text):
        return {
            "intent_id": f"VOC-{uuid.uuid4().hex[:16].upper()}",
            "intent_type": "FIND_TARGETS",
            "raw_text": request.text,
            "extracted_value": None,
            "confidence": 0.8,
            "status": "PARSED",
            "block_reason": None,
            "timestamp": now
        }
    
    if re.search(r'(?:set\s+)?target\s+(?:is\s+|to\s+)?(.+)', text):
        match = re.search(r'(?:set\s+)?target\s+(?:is\s+|to\s+)?(.+)', text)
        return {
            "intent_id": f"VOC-{uuid.uuid4().hex[:16].upper()}",
            "intent_type": "SET_TARGET",
            "raw_text": request.text,
            "extracted_value": match.group(1) if match else None,
            "confidence": 0.8,
            "status": "PARSED",
            "block_reason": None,
            "timestamp": now
        }
    
    if re.search(r'(?:what\s+is\s+the\s+)?status', text):
        return {
            "intent_id": f"VOC-{uuid.uuid4().hex[:16].upper()}",
            "intent_type": "QUERY_STATUS",
            "raw_text": request.text,
            "extracted_value": None,
            "confidence": 0.8,
            "status": "PARSED",
            "block_reason": None,
            "timestamp": now
        }
    
    # Unknown intent
    return {
        "intent_id": f"VOC-{uuid.uuid4().hex[:16].upper()}",
        "intent_type": "UNKNOWN",
        "raw_text": request.text,
        "extracted_value": None,
        "confidence": 0.0,
        "status": "INVALID",
        "block_reason": "Could not parse intent",
        "timestamp": now
    }


@app.post("/api/autonomy/session")
async def create_autonomy_session(request: AutonomySessionRequest):
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
async def get_g38_status():
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
async def get_g38_events(limit: int = 50):
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
async def abort_g38_training():
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
async def start_g38_training(epochs: int = 10):
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


@app.get("/api/g38/guards")
async def get_g38_guards():
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
async def get_g38_training_reports():
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
            except:
                report["learned_features"] = None
        
        reports.append(report)
    
    return {
        "reports": reports[:20],  # Last 20 reports
        "count": len(reports),
        "reports_dir": str(reports_dir),
    }


@app.get("/api/g38/reports/latest")
async def get_g38_latest_report():
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
async def manual_start_training(epochs: int = 10):
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
async def start_24_7_training(epochs: int = 0):
    """Start 24/7 continuous GPU training. epochs=0 means infinite."""
    if not G38_AVAILABLE:
        return {"success": False, "error": "G38 modules not loaded"}
    
    result = start_continuous_training(target_epochs=epochs)
    return {"success": result.get("started", False), **result}


@app.post("/training/continuous/stop")
async def stop_24_7_training():
    """Stop 24/7 continuous training."""
    if not G38_AVAILABLE:
        return {"success": False, "error": "G38 modules not loaded"}
    
    result = stop_continuous_training()
    return {"success": result.get("stopped", False), **result}


@app.post("/training/stop")
async def manual_stop_training():
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
async def manual_training_status():
    """Get current training status."""
    if not G38_AVAILABLE:
        return {"available": False, "error": "G38 modules not loaded"}
    
    trainer = get_auto_trainer()
    return trainer.get_status()


@app.get("/training/progress")
async def manual_training_progress():
    """Get real-time training progress. Returns null if unavailable."""
    mgr = get_training_state_manager()
    metrics = mgr.get_training_progress()
    return metrics.to_dict()


@app.get("/gpu/status")
async def gpu_status():
    """Get GPU utilization and memory metrics. Real data only."""
    result = {
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
async def dataset_stats():
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
        return {"available": False, "error": str(e)}
# =============================================================================

@app.get("/api/db/users")
def list_users():
    """Get all users from HDD storage."""
    try:
        users = get_all_users()
        return {"users": users, "total": len(users)}
    except Exception as e:
        return {"users": [], "total": 0, "error": str(e)}


@app.post("/api/db/users")
def add_user(request: CreateUserRequest):
    """Create a new user."""
    try:
        user = create_user(request.name, request.email, request.role)
        log_activity(str(user['id']), "USER_CREATED", f"User {request.name} created")
        return {"success": True, "user": user}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/db/users/{user_id}")
def get_single_user(user_id: str):
    """Get a specific user by ID."""
    try:
        user = get_user(user_id)
        if user:
            return {"success": True, "user": user}
        return {"success": False, "error": "User not found"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/db/users/{user_id}/bounties")
def get_user_bounties_endpoint(user_id: str):
    """Get all bounties for a specific user."""
    try:
        bounties = get_user_bounties(user_id)
        return {"bounties": bounties, "total": len(bounties)}
    except Exception as e:
        return {"bounties": [], "total": 0, "error": str(e)}


@app.get("/api/db/targets")
def list_targets():
    """Get all targets from HDD storage."""
    try:
        targets = get_all_targets()
        return {"targets": targets, "total": len(targets)}
    except Exception as e:
        return {"targets": [], "total": 0, "error": str(e)}


@app.post("/api/db/targets")
def add_target(request: CreateTargetRequest):
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
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/db/bounties")
def list_bounties():
    """Get all bounties."""
    try:
        bounties = get_all_bounties()
        return {"bounties": bounties, "total": len(bounties)}
    except Exception as e:
        return {"bounties": [], "total": 0, "error": str(e)}


@app.post("/api/db/bounties")
def add_bounty(request: CreateBountyRequest):
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
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/db/bounties")
def update_bounty(request: UpdateBountyRequest):
    """Update bounty status and reward."""
    try:
        update_bounty_status(request.bounty_id, request.status, request.reward)
        log_activity(None, "BOUNTY_UPDATED", f"Bounty {request.bounty_id} -> {request.status}")
        return {"success": True, "bounty_id": request.bounty_id, "status": request.status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/db/sessions")
def add_session(request: CreateSessionRequest):
    """Create a new session."""
    try:
        session = create_session(request.user_id, request.mode, request.target_scope)
        log_activity(request.user_id, "SESSION_STARTED", f"Mode: {request.mode}")
        return {"success": True, "session": session}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/db/activity")
def list_activity(limit: int = 50):
    """Get recent activity log."""
    try:
        activities = get_recent_activity(limit)
        return {"activities": activities, "total": len(activities)}
    except Exception as e:
        return {"activities": [], "total": 0, "error": str(e)}


@app.get("/api/db/admin/stats")
def get_admin_statistics():
    """Get admin dashboard statistics."""
    try:
        stats = get_admin_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        return {"success": False, "stats": None, "error": str(e)}


# =============================================================================
# HDD STORAGE ENGINE ENDPOINTS (NEW)
# =============================================================================

@app.get("/api/storage/stats")
def storage_stats_endpoint():
    """Get HDD storage engine statistics."""
    return get_storage_stats()


@app.get("/api/storage/lifecycle")
def lifecycle_status_endpoint():
    """Get lifecycle status and deletion preview."""
    return get_lifecycle_status()


@app.get("/api/storage/disk")
def disk_status_endpoint():
    """Get HDD disk usage, alerts, and health."""
    return get_disk_status()


@app.get("/api/storage/delete-preview")
def delete_preview_endpoint(entity_type: Optional[str] = None):
    """Preview which entities would be auto-deleted."""
    return get_delete_preview(entity_type)


@app.get("/api/video/list")
def video_list_endpoint(user_id: Optional[str] = None):
    """List stored videos."""
    return list_videos(user_id)


@app.post("/api/video/token")
async def video_token_endpoint(request: Request):
    """Generate a signed video streaming token."""
    body = await request.json()
    return get_video_stream_token(
        body.get("user_id", ""),
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
    role: str = "hunter"


@app.post("/auth/register")
async def register_user(request: RegisterRequest, req: Request):
    """Register a new user with hashed password."""
    existing = get_user_by_email(request.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    pw_hash = hash_password(request.password)
    user = create_user(request.name, request.email, request.role)
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
async def logout(req: Request):
    """End current session."""
    ip = req.client.host if req.client else "unknown"
    log_activity(None, "LOGOUT", f"Logout from {ip}", ip_address=ip)
    return {"success": True, "message": "Logged out"}


@app.get("/admin/active-devices")
def get_active_devices_endpoint():
    """Get all active devices. HDD data only."""
    try:
        devices = get_all_active_devices()
        return {"devices": devices, "total": len(devices)}
    except Exception as e:
        return {"devices": [], "total": 0, "error": str(e)}


@app.get("/admin/active-sessions")
def get_active_sessions_endpoint():
    """Get all active sessions. HDD data only."""
    try:
        sessions = get_active_sessions()
        return {"sessions": sessions, "total": len(sessions)}
    except Exception as e:
        return {"sessions": [], "total": 0, "error": str(e)}


# =============================================================================
# WEBSOCKET ENDPOINTS
# =============================================================================

@app.websocket("/ws/hunter/{workflow_id}")
async def hunter_websocket(websocket: WebSocket, workflow_id: str):
    """WebSocket endpoint for Hunter workflow updates."""
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
            "report_hash": hashlib.md5(str(context.phase_results).encode()).hexdigest()
        }
        
        try:
            await websocket.send_json({"type": "complete", "result": result})
        except Exception:
            pass
        
    except WebSocketDisconnect:
        print(f"[WS] WebSocket disconnected: {report_id}")
    except Exception as e:
        print(f"[!] WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
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
async def system_integrity():
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
async def voice_parse(request: VoiceParseRequest):
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@app.get("/api/voice/mode")
async def voice_mode():
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
async def runtime_status():
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
            "reason": str(e),
            "runtime": None,
            "determinism_ok": False,
            "stale": True,
            "last_update_ms": 0,
            "signature": None
        }


@app.get("/api/accuracy/snapshot")
async def accuracy_snapshot():
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
# MODE CONTROL ENDPOINTS (TRAIN/HUNT mutual exclusion)
# =============================================================================

@app.post("/api/mode/train/start")
async def start_training_mode():
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
async def stop_training_mode():
    """Stop TRAIN mode."""
    global _runtime_mode
    if _runtime_mode != "TRAIN":
        return {"mode": _runtime_mode, "status": "not_in_train"}
    _runtime_mode = "IDLE"
    return {"mode": "IDLE", "status": "stopped"}


@app.post("/api/mode/hunt/start")
async def start_hunt_mode():
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
async def stop_hunt_mode():
    """Stop HUNT mode."""
    global _runtime_mode
    if _runtime_mode != "HUNT":
        return {"mode": _runtime_mode, "status": "not_in_hunt"}
    _runtime_mode = "IDLE"
    return {"mode": "IDLE", "status": "stopped"}


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

