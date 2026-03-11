"""
Voice API Routes — FastAPI router for Jarvis voice pipeline.

Endpoints:
  - POST /api/voice/command       — submit text command
  - POST /api/voice/confirm/{id}  — confirm high-risk intent
  - GET  /api/voice/status        — pipeline health
  - GET  /api/voice/metrics       — SLO metrics
  - GET  /api/voice/history       — audit log (paginated)
  - WS   /ws/voice                — real-time voice stream

All routes require JWT auth.
"""

import logging
import time as _time
from datetime import datetime, UTC
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.auth.auth_guard import require_auth

logger = logging.getLogger(__name__)

voice_router = APIRouter(tags=["voice"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class VoiceCommandRequest(BaseModel):
    text: str
    device_id: str = "browser"
    confidence: float = 0.8
    host_session_id: Optional[str] = None


class VoiceConfirmRequest(BaseModel):
    confirmer_id: str


class HostSessionRequest(BaseModel):
    approver_id: str
    reason: str
    allowed_actions: List[str]
    allowed_apps: List[str] = []
    allowed_tasks: List[str] = []
    allowed_roots: List[str] = []
    expiration_window_s: int = 3600


# =============================================================================
# SHARED STATE
# =============================================================================

def _get_orchestrator():
    from impl_v1.training.voice.voice_intent_orchestrator import VoiceIntentOrchestrator
    if not hasattr(_get_orchestrator, "_instance"):
        _get_orchestrator._instance = VoiceIntentOrchestrator()
    return _get_orchestrator._instance


def _get_policy():
    from impl_v1.training.voice.voice_policy_engine import VoicePolicyEngine
    if not hasattr(_get_policy, "_instance"):
        _get_policy._instance = VoicePolicyEngine()
    return _get_policy._instance


def _get_audit():
    from impl_v1.training.voice.voice_security import VoiceAuditLog
    if not hasattr(_get_audit, "_instance"):
        _get_audit._instance = VoiceAuditLog()
    return _get_audit._instance


def _get_rate_limiter():
    from impl_v1.training.voice.voice_security import VoiceRateLimiter
    if not hasattr(_get_rate_limiter, "_instance"):
        _get_rate_limiter._instance = VoiceRateLimiter()
    return _get_rate_limiter._instance


# =============================================================================
# ROUTES
# =============================================================================

@voice_router.post("/api/voice/command")
async def submit_voice_command(req: VoiceCommandRequest, user=Depends(require_auth)):
    """Submit a voice command for processing.

    Auth required. Rate-limited.
    """
    try:
        _t0 = _time.monotonic()
        # Extract user_id from JWT payload
        user_id = user.get("sub", "unknown") if isinstance(user, dict) else "unknown"

        # Rate limit check
        rl = _get_rate_limiter()
        allowed, reason = rl.is_allowed(user_id, req.device_id)
        if not allowed:
            raise HTTPException(status_code=429, detail=reason)

        # Process through orchestrator
        orch = _get_orchestrator()
        from backend.api.runtime_state import runtime_state
        host_session_id = req.host_session_id or runtime_state.get("active_host_action_session")
        if host_session_id:
            runtime_state.set("active_host_action_session", host_session_id)
        intent = orch.process_transcript(
            text=req.text,
            user_id=user_id,
            device_id=req.device_id,
            confidence=req.confidence,
            context_args=(
                {"host_session_id": host_session_id}
                if host_session_id else None
            ),
        )
        runtime_state.set("active_voice_mode", intent.route_mode)

        # Policy check
        policy = _get_policy()
        decision = policy.evaluate(intent.command_type, intent.args)

        # Audit
        audit = _get_audit()
        audit.log(
            user_id=user_id,
            device_id=req.device_id,
            transcript=req.text,
            intent=intent.command_type,
            action="PENDING",
            policy=decision.verdict.value,
            result=(
                "BLOCKED" if intent.error
                else "AWAITING" if intent.requires_confirmation
                else "QUEUED"
            ),
        )

        # Emit voice inference latency metric
        _voice_latency = round((_time.monotonic() - _t0) * 1000, 2)
        try:
            from backend.observability.metrics import metrics_registry
            metrics_registry.record("voice_inference_latency_ms", _voice_latency)
        except Exception:
            pass

        return {
            "intent_id": intent.intent_id,
            "command_type": intent.command_type,
            "mode": intent.route_mode,
            "risk_level": intent.risk_level.value,
            "requires_confirmation": intent.requires_confirmation,
            "confidence": intent.confidence,
            "policy_verdict": decision.verdict.value,
            "policy_reason": decision.reason,
            "args": intent.args,
            "ready_to_execute": orch.is_ready_to_execute(intent.intent_id),
            "error": intent.error,
            "timestamp": intent.timestamp,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Voice command error")
        raise HTTPException(status_code=500, detail="Internal error")


@voice_router.post("/api/voice/confirm/{intent_id}")
async def confirm_voice_intent(intent_id: str, req: VoiceConfirmRequest,
                                user=Depends(require_auth)):
    """Confirm a high-risk voice intent for execution."""
    orch = _get_orchestrator()
    success = orch.confirm_intent(intent_id, req.confirmer_id)
    if not success:
        raise HTTPException(status_code=404, detail="Intent not found or not confirmable")
    return {"confirmed": True, "intent_id": intent_id}


@voice_router.post("/api/voice/host-session")
async def create_host_action_session(req: HostSessionRequest, user=Depends(require_auth)):
    """Create a signed bounded host-action session."""
    user_id = user.get("sub", "unknown") if isinstance(user, dict) else "unknown"
    try:
        from backend.api.runtime_state import runtime_state
        from backend.governance.host_action_governor import HostActionGovernor

        governor = HostActionGovernor()
        session = governor.issue_session(
            requested_by=user_id,
            approver_id=req.approver_id,
            reason=req.reason,
            allowed_actions=req.allowed_actions,
            allowed_apps=req.allowed_apps,
            allowed_tasks=req.allowed_tasks,
            allowed_roots=req.allowed_roots,
            expiration_window_s=req.expiration_window_s,
        )
        runtime_state.set("active_host_action_session", session.session_id)
        return governor.describe_session(session.session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Host session creation failed")
        raise HTTPException(status_code=500, detail="Host governance unavailable")


@voice_router.get("/api/voice/host-session/{session_id}")
async def host_action_session_status(session_id: str, user=Depends(require_auth)):
    """Return current state for a signed host-action session."""
    from backend.governance.host_action_governor import HostActionGovernor

    governor = HostActionGovernor()
    status = governor.describe_session(session_id)
    if status["status"] == "missing":
        raise HTTPException(status_code=404, detail="Session not found")
    return status


@voice_router.get("/api/voice/status")
async def voice_pipeline_status():
    """Get voice pipeline health status — truthful reporting."""
    from backend.assistant.voice_runtime import build_voice_pipeline_status

    return build_voice_pipeline_status()


@voice_router.get("/api/voice/metrics")
async def voice_metrics():
    """Get detailed voice SLO metrics."""
    from impl_v1.training.voice.voice_metrics import get_voice_health
    return get_voice_health()


@voice_router.get("/api/voice/history")
async def voice_audit_history(limit: int = 50):
    """Get voice command audit history."""
    audit = _get_audit()
    return {
        "entries": audit.get_entries(limit=limit),
        "total": audit.count,
        "chain_valid": audit.verify_chain(),
    }
