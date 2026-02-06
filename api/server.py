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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import database module
from database import (
    init_database, close_pool,
    create_user, get_user, get_all_users, update_user_stats,
    create_target, get_all_targets, get_target,
    create_bounty, get_user_bounties, get_all_bounties, update_bounty_status,
    create_session, get_user_sessions, update_session_progress,
    log_activity, get_recent_activity, get_admin_stats
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
    mode: str  # MOCK, READ_ONLY, AUTONOMOUS_FIND, REAL
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
# IN-MEMORY STATE (for demo purposes)
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
    
    # Return demo state if no specific ID
    return {
        "dashboard_id": "DASH-DEMO",
        "state": "IDLE",
        "panels": ["USER", "ACTIVITY", "REPORT"]
    }


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
    """Discover potential bug bounty targets."""
    # Mock target data based on G14
    mock_targets = [
        {
            "candidate_id": f"TGT-{uuid.uuid4().hex[:16].upper()}",
            "program_name": "Example Corp",
            "source": "HACKERONE_PUBLIC",
            "scope_summary": "*.example.com",
            "payout_tier": "HIGH",
            "report_density": "LOW",
            "is_public": True,
            "requires_invite": False,
            "discovered_at": datetime.now(UTC).isoformat()
        },
        {
            "candidate_id": f"TGT-{uuid.uuid4().hex[:16].upper()}",
            "program_name": "Test Inc",
            "source": "BUGCROWD_PUBLIC",
            "scope_summary": "api.test.io",
            "payout_tier": "MEDIUM",
            "report_density": "MEDIUM",
            "is_public": True,
            "requires_invite": False,
            "discovered_at": datetime.now(UTC).isoformat()
        },
        {
            "candidate_id": f"TGT-{uuid.uuid4().hex[:16].upper()}",
            "program_name": "Secure Ltd",
            "source": "SECURITY_TXT",
            "scope_summary": "security.secure.io",
            "payout_tier": "HIGH",
            "report_density": "LOW",
            "is_public": True,
            "requires_invite": False,
            "discovered_at": datetime.now(UTC).isoformat()
        }
    ]
    
    # Filter based on request
    filtered = [t for t in mock_targets if t["is_public"] or not request.public_only]
    
    return {
        "result_id": f"DIS-{uuid.uuid4().hex[:16].upper()}",
        "candidates": filtered,
        "total_found": len(mock_targets),
        "filtered_count": len(mock_targets) - len(filtered),
        "timestamp": datetime.now(UTC).isoformat()
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
        blocked = ["TARGET_ANALYSIS", "CVE_CORRELATION", "PASSIVE_DISCOVERY", 
                   "DRAFT_REPORT", "EXPLOIT", "SUBMISSION", "STATE_CHANGE", "BROWSER_ACTION"]
    
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
            "epoch": status["epoch"],  # Current session epoch (real)
            "total_epochs": status.get("total_epochs", 0),  # Target epochs for this session
            "total_completed": status.get("total_completed", 0),  # Total ever completed
            "progress": status.get("progress", 0),  # REAL progress from backend
            "idle_seconds": status["idle_seconds"],
            "power_connected": status["power_connected"],
            "scan_active": status["scan_active"],
            "gpu_available": status["gpu_available"],
            "events_count": status["events_count"],
            "last_event": status["last_event"],
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
    trainer.abort_training()
    
    return {
        "success": True,
        "state": trainer.state.value,
        "message": "Training abort requested",
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


# DATABASE API ENDPOINTS
# =============================================================================

@app.get("/api/db/users")
async def list_users():
    """Get all users from database."""
    try:
        users = await get_all_users()
        # Convert UUID to string for JSON serialization
        for user in users:
            user['id'] = str(user['id'])
            if user.get('created_at'):
                user['created_at'] = user['created_at'].isoformat()
            if user.get('last_active'):
                user['last_active'] = user['last_active'].isoformat()
        return {"users": users, "total": len(users)}
    except Exception as e:
        return {"users": [], "total": 0, "error": str(e)}


@app.post("/api/db/users")
async def add_user(request: CreateUserRequest):
    """Create a new user."""
    try:
        user = await create_user(request.name, request.email, request.role)
        user['id'] = str(user['id'])
        if user.get('created_at'):
            user['created_at'] = user['created_at'].isoformat()
        await log_activity(str(user['id']), "USER_CREATED", f"User {request.name} created")
        return {"success": True, "user": user}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/db/users/{user_id}")
async def get_single_user(user_id: str):
    """Get a specific user by ID."""
    try:
        user = await get_user(user_id)
        if user:
            user['id'] = str(user['id'])
            if user.get('created_at'):
                user['created_at'] = user['created_at'].isoformat()
            if user.get('last_active'):
                user['last_active'] = user['last_active'].isoformat()
            return {"success": True, "user": user}
        return {"success": False, "error": "User not found"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/db/users/{user_id}/bounties")
async def get_user_bounties_endpoint(user_id: str):
    """Get all bounties for a specific user."""
    try:
        bounties = await get_user_bounties(user_id)
        for b in bounties:
            b['id'] = str(b['id'])
            if b.get('submitted_at'):
                b['submitted_at'] = b['submitted_at'].isoformat()
        return {"bounties": bounties, "total": len(bounties)}
    except Exception as e:
        return {"bounties": [], "total": 0, "error": str(e)}


@app.get("/api/db/targets")
async def list_targets():
    """Get all targets from database."""
    try:
        targets = await get_all_targets()
        for t in targets:
            t['id'] = str(t['id'])
            if t.get('created_at'):
                t['created_at'] = t['created_at'].isoformat()
        return {"targets": targets, "total": len(targets)}
    except Exception as e:
        return {"targets": [], "total": 0, "error": str(e)}


@app.post("/api/db/targets")
async def add_target(request: CreateTargetRequest):
    """Create a new target."""
    try:
        target = await create_target(
            request.program_name, 
            request.scope, 
            request.link, 
            request.platform, 
            request.payout_tier
        )
        target['id'] = str(target['id'])
        if target.get('created_at'):
            target['created_at'] = target['created_at'].isoformat()
        await log_activity(None, "TARGET_CREATED", f"Target {request.program_name} created")
        return {"success": True, "target": target}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/db/bounties")
async def list_bounties():
    """Get all bounties with user and target info."""
    try:
        bounties = await get_all_bounties()
        for b in bounties:
            b['id'] = str(b['id'])
            if b.get('submitted_at'):
                b['submitted_at'] = b['submitted_at'].isoformat()
        return {"bounties": bounties, "total": len(bounties)}
    except Exception as e:
        return {"bounties": [], "total": 0, "error": str(e)}


@app.post("/api/db/bounties")
async def add_bounty(request: CreateBountyRequest):
    """Create a new bounty submission."""
    try:
        bounty = await create_bounty(
            request.user_id,
            request.target_id,
            request.title,
            request.description,
            request.severity
        )
        bounty['id'] = str(bounty['id'])
        bounty['user_id'] = str(bounty['user_id'])
        if bounty.get('target_id'):
            bounty['target_id'] = str(bounty['target_id'])
        if bounty.get('submitted_at'):
            bounty['submitted_at'] = bounty['submitted_at'].isoformat()
        await log_activity(request.user_id, "BOUNTY_SUBMITTED", f"Bounty: {request.title}")
        return {"success": True, "bounty": bounty}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/db/bounties")
async def update_bounty(request: UpdateBountyRequest):
    """Update bounty status and reward."""
    try:
        await update_bounty_status(request.bounty_id, request.status, request.reward)
        await log_activity(None, "BOUNTY_UPDATED", f"Bounty {request.bounty_id} -> {request.status}")
        return {"success": True, "bounty_id": request.bounty_id, "status": request.status}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/db/sessions")
async def add_session(request: CreateSessionRequest):
    """Create a new session."""
    try:
        session = await create_session(request.user_id, request.mode, request.target_scope)
        session['id'] = str(session['id'])
        session['user_id'] = str(session['user_id'])
        if session.get('started_at'):
            session['started_at'] = session['started_at'].isoformat()
        await log_activity(request.user_id, "SESSION_STARTED", f"Mode: {request.mode}")
        return {"success": True, "session": session}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/db/activity")
async def list_activity(limit: int = 50):
    """Get recent activity log."""
    try:
        activities = await get_recent_activity(limit)
        for a in activities:
            a['id'] = str(a['id'])
            if a.get('created_at'):
                a['created_at'] = a['created_at'].isoformat()
        return {"activities": activities, "total": len(activities)}
    except Exception as e:
        return {"activities": [], "total": 0, "error": str(e)}


@app.get("/api/db/admin/stats")
async def get_admin_statistics():
    """Get admin dashboard statistics."""
    try:
        stats = await get_admin_stats()
        return {"success": True, "stats": stats}
    except Exception as e:
        return {"success": False, "stats": None, "error": str(e)}


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
    
    # Initialize database
    try:
        await init_database()
        print(f"[+] Database connected")
    except Exception as e:
        print(f"[!] Database connection failed: {e}")
    
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
    
    await close_pool()

# Apply lifespan to app
app.router.lifespan_context = lifespan


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

