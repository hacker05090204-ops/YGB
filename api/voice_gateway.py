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

import json
import logging
import uuid
from datetime import datetime, UTC
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.auth.auth_guard import require_auth, ws_authenticate

logger = logging.getLogger(__name__)

voice_gw_router = APIRouter(tags=["voice-gateway"])


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


class ExecuteRequest(BaseModel):
    """Execute a confirmed intent."""
    intent_id: str
    confirmer_id: str


class RespondRequest(BaseModel):
    """Generate TTS response."""
    text: str
    response_type: str = "SUCCESS"


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


# =============================================================================
# REST ENDPOINTS
# =============================================================================

@voice_gw_router.post("/api/voice/transcribe")
async def transcribe_audio(req: TranscribeRequest, user=Depends(require_auth)):
    """One-shot audio transcription. Auth required."""
    import base64

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
    user_id = user.get("sub", "unknown") if isinstance(user, dict) else "unknown"

    # Rate limit
    rl = _get_rate_limiter()
    allowed, reason = rl.is_allowed(user_id, req.device_id)
    if not allowed:
        raise HTTPException(status_code=429, detail=reason)

    orch = _get_orchestrator()
    intent = orch.process_transcript(
        text=req.text, user_id=user_id,
        device_id=req.device_id, confidence=req.confidence,
    )

    # Policy check
    policy = _get_policy()
    decision = policy.evaluate(intent.command_type, intent.args)

    # Audit
    audit = _get_audit()
    audit.log(
        user_id=user_id, device_id=req.device_id,
        transcript=req.text, intent=intent.command_type,
        action="PENDING", policy=decision.verdict.value,
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
    }


@voice_gw_router.post("/api/voice/execute")
async def execute_intent(req: ExecuteRequest, user=Depends(require_auth)):
    """Execute a confirmed intent. Auth required."""
    orch = _get_orchestrator()
    success = orch.confirm_intent(req.intent_id, req.confirmer_id)
    if not success:
        raise HTTPException(status_code=404, detail="Intent not found or not confirmable")
    return {"executed": True, "intent_id": req.intent_id}


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
    }


# =============================================================================
# WEBSOCKET VOICE STREAM
# =============================================================================

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
    # Authenticate
    user = await ws_authenticate(ws)
    if user is None:
        return  # ws_authenticate closes the connection on failure

    await ws.accept()
    user_id = user.get("sub", "ws_user") if isinstance(user, dict) else "ws_user"

    logger.info(f"[VOICE_GW] WebSocket connected: user={user_id}")
    chain = _get_stt_chain()
    audit = _get_audit()
    rl = _get_rate_limiter()

    try:
        while True:
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
            await ws.close(code=1011, reason=str(e))
        except Exception:
            pass
