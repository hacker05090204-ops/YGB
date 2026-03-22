"""
Voice Gateway — WebSocket + REST endpoints for the voice pipeline.

Endpoints:
  - WS   /ws/voice/stream    — real-time audio streaming + transcription
  - POST /api/voice/transcribe — one-shot audio transcription
  - POST /api/voice/intent    — parse intent from text
  - POST /api/voice/execute   — execute confirmed intent
  - POST /api/voice/respond   — TTS response

All endpoints require bearer auth.
Rate-limited per user/device.
Full audit logging.
"""

import asyncio
import json
import logging
import time as _time
import uuid
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.auth.auth_guard import (
    require_admin,
    require_auth,
    ws_authenticate,
    get_allowed_origins,
    is_allowed_origin,
)

logger = logging.getLogger(__name__)

voice_gw_router = APIRouter(tags=["voice-gateway"])
VOICE_WS_ALLOWED_ORIGINS = frozenset({
    "http://localhost:3000",
    "https://ygb-nas.tail7521c4.ts.net",
})


# =============================================================================
# REQUEST MODELS
# =============================================================================

class TranscribeRequest(BaseModel):
    """One-shot transcription request with base64-encoded audio."""
    audio_b64: str
    sample_rate: int = 16000
    device_id: str = "browser"


class IntentRequest(BaseModel):
    """Parse intent from text."""
    text: str
    device_id: str = "browser"
    confidence: float = 0.8
    host_session_id: Optional[str] = None


class ExecuteRequest(BaseModel):
    """Execute a confirmed intent."""
    intent_id: str
    confirmer_id: Optional[str] = None


class RespondRequest(BaseModel):
    """Generate TTS response."""
    text: str
    response_type: str = "SUCCESS"


class STTSampleRequest(BaseModel):
    """Browser-captured WAV sample paired with transcript for local STT training."""
    audio_wav_b64: str
    transcript: str
    device_id: str = "browser"
    language: str = "en-US"
    provider: str = "BROWSER_WEBSPEECH"
    session_id: str = ""


class STTTrainRequest(BaseModel):
    """Admin-triggered local STT training request."""
    epochs: int = 3
    batch_size: int = 4


# =============================================================================
# SHARED STATE
# =============================================================================

def _get_orchestrator():
    from impl_v1.training.voice.voice_intent_orchestrator import VoiceIntentOrchestrator
    if not hasattr(_get_orchestrator, "_inst"):
        _get_orchestrator._inst = VoiceIntentOrchestrator()
    return _get_orchestrator._inst


def _get_policy():
    from impl_v1.training.voice.voice_policy_engine import VoicePolicyEngine
    if not hasattr(_get_policy, "_inst"):
        _get_policy._inst = VoicePolicyEngine()
    return _get_policy._inst


def _get_audit():
    from impl_v1.training.voice.voice_security import VoiceAuditLog
    if not hasattr(_get_audit, "_inst"):
        _get_audit._inst = VoiceAuditLog()
    return _get_audit._inst


def _get_rate_limiter():
    from impl_v1.training.voice.voice_security import VoiceRateLimiter
    if not hasattr(_get_rate_limiter, "_inst"):
        _get_rate_limiter._inst = VoiceRateLimiter()
    return _get_rate_limiter._inst


def _get_stt_chain():
    from impl_v1.training.voice.stt_adapter import get_stt_chain
    return get_stt_chain()


def _get_tts_engine():
    from impl_v1.training.voice.tts_streaming import TTSEngine
    if not hasattr(_get_tts_engine, "_inst"):
        _get_tts_engine._inst = TTSEngine()
    return _get_tts_engine._inst


def _voice_ws_origins() -> set[str]:
    return set(get_allowed_origins()) | set(VOICE_WS_ALLOWED_ORIGINS)


def _voice_ws_origin_is_allowed(origin: str) -> bool:
    normalized = (origin or "").strip().rstrip("/")
    return normalized in _voice_ws_origins() or is_allowed_origin(origin)


def _select_bearer_subprotocol(ws: WebSocket) -> Optional[str]:
    protocols = ws.headers.get("sec-websocket-protocol", "")
    for proto in protocols.split(","):
        candidate = proto.strip()
        if candidate.startswith("bearer."):
            return candidate
    return None


async def _accept_authenticated_voice_ws(ws: WebSocket) -> dict:
    origin = ws.headers.get("origin", "")
    if origin and not _voice_ws_origin_is_allowed(origin):
        logger.warning("[VOICE_GW] WebSocket origin rejected: %s", origin)
        await ws.close(code=4403, reason="Origin not allowed")
        return {}

    user = await ws_authenticate(ws)
    if user is None:
        await ws.close(code=4401, reason="Authentication required")
        return {}

    subprotocol = _select_bearer_subprotocol(ws)
    if subprotocol:
        await ws.accept(subprotocol=subprotocol)
    else:
        await ws.accept()
    return user


# =============================================================================
# REST ENDPOINTS
# =============================================================================

@voice_gw_router.post("/api/voice/transcribe")
async def transcribe_audio(req: TranscribeRequest, user=Depends(require_auth)):
    """One-shot audio transcription. Auth required."""
    import base64

    _t0 = _time.monotonic()
    user_id = user.get("sub", "unknown") if isinstance(user, dict) else "unknown"

    # Rate limit
    rl = _get_rate_limiter()
    allowed, reason = rl.is_allowed(user_id, req.device_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    try:
        audio_bytes = base64.b64decode(req.audio_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 audio data")

    chain = _get_stt_chain()
    result = chain.transcribe(audio_bytes)

    # Emit voice inference latency metric
    _voice_latency = round((_time.monotonic() - _t0) * 1000, 2)
    try:
        from backend.observability.metrics import metrics_registry
        metrics_registry.record("voice_inference_latency_ms", _voice_latency)
    except Exception:
        logger.debug("Metrics recording unavailable", exc_info=True)

    audit = _get_audit()
    audit.log(
        user_id=user_id, device_id=req.device_id,
        transcript=result.text if result else "",
        intent="TRANSCRIBE", action="STT",
        policy="ALLOWED", result="OK" if result else "FAILED",
    )

    if result:
        return {
            "transcript_id": result.transcript_id,
            "text": result.text,
            "confidence": result.confidence,
            "provider": result.provider.value,
            "latency_ms": result.latency_ms,
        }
    else:
        return {
            "text": "",
            "confidence": 0.0,
            "provider": "NONE",
            "error": "All STT providers failed",
        }


@voice_gw_router.post("/api/voice/intent")
async def parse_intent(req: IntentRequest, user=Depends(require_auth)):
    """Parse text into structured intent. Auth required."""
    _t0 = _time.monotonic()
    user_id = user.get("sub", "unknown") if isinstance(user, dict) else "unknown"

    # Rate limit
    rl = _get_rate_limiter()
    allowed, reason = rl.is_allowed(user_id, req.device_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    orch = _get_orchestrator()
    from backend.api.runtime_state import runtime_state
    host_session_id = req.host_session_id or runtime_state.get("active_host_action_session")
    if host_session_id:
        runtime_state.set("active_host_action_session", host_session_id)
    intent = orch.process_transcript(
        text=req.text, user_id=user_id,
        device_id=req.device_id, confidence=req.confidence,
        context_args=(
            {"host_session_id": host_session_id}
            if host_session_id else None
        ),
    )
    runtime_state.set("active_voice_mode", intent.route_mode)

    # Policy check
    policy = _get_policy()
    decision = policy.evaluate(intent.command_type, intent.args)

    # Emit voice inference latency metric
    _voice_latency = round((_time.monotonic() - _t0) * 1000, 2)
    try:
        from backend.observability.metrics import metrics_registry
        metrics_registry.record("voice_inference_latency_ms", _voice_latency)
    except Exception:
        logger.debug("Metrics recording unavailable", exc_info=True)

    # Audit
    audit = _get_audit()
    audit.log(
        user_id=user_id, device_id=req.device_id,
        transcript=req.text, intent=intent.command_type,
        action="PENDING", policy=decision.verdict.value,
        result=(
            "BLOCKED" if intent.error
            else "AWAITING" if intent.requires_confirmation
            else "QUEUED"
        ),
    )

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
    }


@voice_gw_router.post("/api/voice/execute")
async def execute_intent(req: ExecuteRequest, user=Depends(require_auth)):
    """Execute a confirmed intent. Auth required."""
    user_id = user.get("sub", "unknown") if isinstance(user, dict) else "unknown"
    orch = _get_orchestrator()
    from backend.assistant.voice_runtime import execute_orchestrated_intent

    result = execute_orchestrated_intent(
        orch,
        req.intent_id,
        req.confirmer_id,
        policy=_get_policy(),
        audit=_get_audit(),
        user_id=user_id,
        device_id="browser",
    )
    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("message", "Intent not found"))
    if result.get("status") == "blocked":
        raise HTTPException(status_code=409, detail=result)
    return result


@voice_gw_router.post("/api/voice/respond")
async def tts_respond(req: RespondRequest, user=Depends(require_auth)):
    """Generate TTS response. Auth required."""
    from impl_v1.training.voice.tts_streaming import ResponseType

    tts = _get_tts_engine()
    resp_type = getattr(ResponseType, req.response_type, ResponseType.SUCCESS)
    result = tts.speak(req.text, resp_type)

    return {
        "response_id": result.response_id,
        "text": result.text,
        "status": result.status.value,
        "provider": result.provider.value,
        "latency_ms": result.latency_ms,
        "audio_url": result.audio_url,
    }


@voice_gw_router.post("/api/voice/stt/sample")
async def upload_stt_sample(req: STTSampleRequest, user=Depends(require_auth)):
    """Store a real browser-captured STT sample for offline training."""
    import base64

    user_id = user.get("sub", "unknown") if isinstance(user, dict) else "unknown"
    try:
        audio_bytes = base64.b64decode(req.audio_wav_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 WAV payload")

    from backend.training.stt_dataset_collector import save_sample

    result = save_sample(
        audio_bytes=audio_bytes,
        transcript=req.transcript,
        user_id=user_id,
        device_id=req.device_id,
        language=req.language,
        provider=req.provider,
        session_id=req.session_id,
    )
    audit = _get_audit()
    audit.log(
        user_id=user_id,
        device_id=req.device_id,
        transcript=req.transcript[:120],
        intent="STT_SAMPLE_UPLOAD",
        action="DATASET_APPEND",
        policy="ALLOWED",
        result="ACCEPTED" if result.get("accepted") else "REJECTED",
    )
    return result


@voice_gw_router.get("/api/voice/stt/status")
async def stt_dataset_status(user=Depends(require_auth)):
    """Truthful offline STT readiness, quality, and model status."""
    from backend.training.stt_dataset_collector import get_dataset_status
    from impl_v1.training.voice.stt_model import get_local_stt_service

    return {
        "dataset": get_dataset_status(),
        "model": get_local_stt_service().get_status(),
    }


@voice_gw_router.post("/api/voice/stt/train")
async def train_local_stt(req: STTTrainRequest, user=Depends(require_admin)):
    """Admin-only local STT training trigger."""
    from backend.training.stt_dataset_collector import train_local_stt_model

    result = await asyncio.to_thread(
        train_local_stt_model,
        epochs=max(1, min(req.epochs, 20)),
        batch_size=max(1, min(req.batch_size, 16)),
    )
    return result


# =============================================================================
# WEBSOCKET VOICE STREAM
# =============================================================================

@voice_gw_router.websocket("/ws/voice")
@voice_gw_router.websocket("/ws/voice/stream")
async def voice_stream(ws: WebSocket):
    """
    Real-time voice streaming via WebSocket.

    Auth: Bearer token via subprotocol.
    Protocol:
      - Client sends binary audio chunks (PCM 16-bit, 16kHz)
      - Server responds with JSON transcription results
      - Client can send JSON control messages: {"type": "stop"}, {"type": "interrupt"}
    """
    # Authenticate — ws_authenticate returns None on failure but does NOT
    # close the socket.  We must close explicitly to prevent dangling connections.
    user = await _accept_authenticated_voice_ws(ws)
    if not user:
        return
    user_id = user.get("sub", "ws_user") if isinstance(user, dict) else "ws_user"

    logger.info(f"[VOICE_GW] WebSocket connected: user={user_id}")
    chain = _get_stt_chain()
    audit = _get_audit()
    rl = _get_rate_limiter()

    import time as _time

    WS_SESSION_TIMEOUT = 14400  # 4 hours max session
    _ws_start = _time.monotonic()

    try:
        while True:
            if _time.monotonic() - _ws_start > WS_SESSION_TIMEOUT:
                logger.info("[VOICE_GW] Session timeout (%ds)", WS_SESSION_TIMEOUT)
                await ws.close(code=1000, reason="Session timeout")
                break
            data = await ws.receive()

            if "bytes" in data and data["bytes"]:
                # Audio chunk — transcribe
                allowed, reason = rl.is_allowed(user_id, "websocket")
                if not allowed:
                    await ws.send_json({"type": "error", "error": reason})
                    continue

                audio_bytes = data["bytes"]
                result = chain.transcribe(audio_bytes)

                if result:
                    audit.log(
                        user_id=user_id, device_id="websocket",
                        transcript=result.text, intent="STREAM_STT",
                        action="TRANSCRIBE", policy="ALLOWED",
                        result="OK",
                    )
                    await ws.send_json({
                        "type": "transcript",
                        "transcript_id": result.transcript_id,
                        "text": result.text,
                        "confidence": result.confidence,
                        "provider": result.provider.value,
                        "is_partial": result.is_partial,
                        "latency_ms": result.latency_ms,
                    })
                else:
                    await ws.send_json({
                        "type": "transcript",
                        "text": "",
                        "confidence": 0.0,
                        "error": "STT failed",
                    })

            elif "text" in data and data["text"]:
                # Control message
                try:
                    msg = json.loads(data["text"])
                    msg_type = msg.get("type", "")

                    if msg_type == "stop":
                        await ws.send_json({"type": "stopped"})
                        break

                    elif msg_type == "interrupt":
                        tts = _get_tts_engine()
                        tts.interrupt()
                        await ws.send_json({"type": "interrupted"})

                    elif msg_type == "browser_transcript":
                        # Browser WebSpeech relay
                        text = msg.get("text", "")
                        confidence = msg.get("confidence", 0.7)
                        result = chain.submit_browser_transcript(text, confidence)
                        await ws.send_json({
                            "type": "transcript",
                            "transcript_id": result.transcript_id,
                            "text": result.text,
                            "confidence": result.confidence,
                            "provider": result.provider.value,
                        })

                    else:
                        await ws.send_json({"type": "error", "error": f"Unknown message type: {msg_type}"})

                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "error": "Invalid JSON"})

    except WebSocketDisconnect:
        logger.info(f"[VOICE_GW] WebSocket disconnected: user={user_id}")
    except Exception as e:
        logger.error(f"[VOICE_GW] WebSocket error: {e}")
        try:
            await ws.close(code=1011, reason="Internal server error")
        except Exception:
            pass
