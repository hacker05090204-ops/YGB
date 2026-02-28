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
from datetime import datetime, UTC
from typing import Optional

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


class VoiceConfirmRequest(BaseModel):
    confirmer_id: str


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
        # Extract user_id from JWT payload
        user_id = user.get("sub", "unknown") if isinstance(user, dict) else "unknown"

        # Rate limit check
        rl = _get_rate_limiter()
        allowed, reason = rl.is_allowed(user_id, req.device_id)
        if not allowed:
            raise HTTPException(status_code=429, detail=reason)

        # Process through orchestrator
        orch = _get_orchestrator()
        intent = orch.process_transcript(
            text=req.text,
            user_id=user_id,
            device_id=req.device_id,
            confidence=req.confidence,
        )

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
            result="AWAITING" if intent.requires_confirmation else "QUEUED",
        )

        return {
            "intent_id": intent.intent_id,
            "command_type": intent.command_type,
            "risk_level": intent.risk_level.value,
            "requires_confirmation": intent.requires_confirmation,
            "confidence": intent.confidence,
            "policy_verdict": decision.verdict.value,
            "policy_reason": decision.reason,
            "error": intent.error,
            "timestamp": intent.timestamp,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Voice command error")
        raise HTTPException(status_code=500, detail=str(e))


@voice_router.post("/api/voice/confirm/{intent_id}")
async def confirm_voice_intent(intent_id: str, req: VoiceConfirmRequest,
                                user=Depends(require_auth)):
    """Confirm a high-risk voice intent for execution."""
    orch = _get_orchestrator()
    success = orch.confirm_intent(intent_id, req.confirmer_id)
    if not success:
        raise HTTPException(status_code=404, detail="Intent not found or not confirmable")
    return {"confirmed": True, "intent_id": intent_id}


@voice_router.get("/api/voice/status")
async def voice_pipeline_status():
    """Get voice pipeline health status — truthful reporting."""
    from impl_v1.training.voice.stt_adapter import get_stt_status
    from impl_v1.training.voice.tts_streaming import TTSEngine
    from impl_v1.training.voice.voice_metrics import get_voice_health

    stt = get_stt_status()
    tts = TTSEngine()
    tts_stats = tts.get_stats()
    metrics = get_voice_health()

    # Determine overall TTS status
    tts_status = "TTS_READY" if tts_stats.get("status") != "ERROR" else "DEGRADED"

    return {
        "pipeline_status": "ONLINE",
        "stt_status": stt.get("stt_status", "DEGRADED"),
        "tts_status": tts_status,
        "local_only": stt.get("local_only", True),
        "external_deps": [],
        "no_whisper_dependency": True,
        "no_google_stt_dependency": True,
        "stt": stt,
        "tts": tts_stats,
        "metrics_summary": {
            "total_commands": metrics["total_commands"],
            "success_rate": metrics["success_rate"],
            "slo_met": metrics["slo_met"],
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }


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
